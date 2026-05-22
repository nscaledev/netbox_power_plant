from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify


CAD_UPLOAD_ROOT = "netbox_power_plant/cad_uploads"
SUPPORTED_DIRECT_UPLOAD_SUFFIXES = {
    ".dwg",
    ".pcp",
    ".ctb",
    ".stb",
    ".dxf",
}
SUPPORTED_ARCHIVE_SUFFIXES = {".zip"}
SUPPORTED_UPLOAD_SUFFIXES = SUPPORTED_DIRECT_UPLOAD_SUFFIXES | SUPPORTED_ARCHIVE_SUFFIXES
MAX_CAD_UPLOAD_FILES = 500
MAX_CAD_UPLOAD_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_CAD_UPLOAD_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class StoredCadUploadPackage:
    root: Path
    uploaded_filenames: tuple[str, ...]
    stored_filenames: tuple[str, ...]
    ignored_filenames: tuple[str, ...] = ()

    @property
    def dwg_count(self):
        return len([name for name in self.stored_filenames if Path(name).suffix.lower() == ".dwg"])


def store_cad_upload_package(*, site_slug, uploaded_files) -> StoredCadUploadPackage:
    """
    Persist uploaded CAD files into a durable package directory under MEDIA_ROOT.

    Browsers cannot portably upload directories, so this accepts either a ZIP
    archive of the CAD package or a flat multi-file upload. Files are flattened
    into one package directory because the Madison CAD discovery code matches
    DWG/PCP pairs by filename stem.
    """
    files = tuple(uploaded_files or ())
    if not files:
        raise ValueError("Upload a CAD ZIP archive or one or more CAD source files.")

    _validate_declared_upload_size(files)

    package_root = _new_package_root(site_slug)
    package_root.mkdir(parents=True, exist_ok=False)
    stored = []
    ignored = []
    uploaded = []
    total_bytes = 0

    try:
        for uploaded_file in files:
            upload_name = _safe_basename(uploaded_file.name)
            uploaded.append(upload_name)
            suffix = Path(upload_name).suffix.lower()
            if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
                ignored.append(upload_name)
                continue
            if suffix in SUPPORTED_ARCHIVE_SUFFIXES:
                extracted, skipped, extracted_bytes = _extract_cad_archive(uploaded_file, package_root, existing=stored)
                stored.extend(extracted)
                ignored.extend(skipped)
                total_bytes += extracted_bytes
            else:
                total_bytes += _save_uploaded_file(uploaded_file, package_root / upload_name)
                stored.append(upload_name)

            if len(stored) > MAX_CAD_UPLOAD_FILES:
                raise ValueError(f"CAD package contains more than {MAX_CAD_UPLOAD_FILES} supported files.")
            if total_bytes > MAX_CAD_UPLOAD_EXTRACTED_BYTES:
                raise ValueError(
                    f"CAD package exceeds the supported extracted size limit "
                    f"of {_format_byte_limit(MAX_CAD_UPLOAD_EXTRACTED_BYTES)}."
                )

        if not any(Path(name).suffix.lower() == ".dwg" for name in stored):
            raise ValueError("CAD package must include at least one DWG file.")

        _write_manifest(
            package_root,
            uploaded_filenames=uploaded,
            stored_filenames=stored,
            ignored_filenames=ignored,
        )
        return StoredCadUploadPackage(
            root=package_root,
            uploaded_filenames=tuple(uploaded),
            stored_filenames=tuple(stored),
            ignored_filenames=tuple(ignored),
        )
    except Exception:
        shutil.rmtree(package_root, ignore_errors=True)
        raise


def _new_package_root(site_slug):
    media_root = Path(settings.MEDIA_ROOT)
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    site_part = slugify(str(site_slug)) or "site"
    return media_root / CAD_UPLOAD_ROOT / site_part / f"{timestamp}-{uuid4().hex[:12]}"


def _validate_declared_upload_size(uploaded_files):
    total_size = 0
    for uploaded_file in uploaded_files:
        total_size += int(getattr(uploaded_file, "size", 0) or 0)
        if total_size > MAX_CAD_UPLOAD_PACKAGE_BYTES:
            raise ValueError(
                f"CAD upload exceeds the supported request size limit "
                f"of {_format_byte_limit(MAX_CAD_UPLOAD_PACKAGE_BYTES)}."
            )


def _extract_cad_archive(uploaded_file, package_root, *, existing):
    try:
        archive = ZipFile(uploaded_file)
    except BadZipFile as exc:
        raise ValueError(f"Uploaded archive is not a valid ZIP file: {uploaded_file.name}") from exc

    extracted = []
    ignored = []
    total_bytes = 0
    existing_names = set(existing)
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            member_name = _safe_basename(info.filename)
            if _is_ignored_archive_member(info.filename, member_name):
                ignored.append(info.filename)
                continue
            suffix = Path(member_name).suffix.lower()
            if suffix not in SUPPORTED_DIRECT_UPLOAD_SUFFIXES:
                ignored.append(info.filename)
                continue
            if member_name in existing_names or member_name in extracted:
                raise ValueError(f"CAD package contains duplicate filename: {member_name}")
            target = package_root / member_name
            with archive.open(info) as source, target.open("wb") as destination:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_CAD_UPLOAD_EXTRACTED_BYTES:
                        raise ValueError(
                            f"CAD package exceeds the supported extracted size limit "
                            f"of {_format_byte_limit(MAX_CAD_UPLOAD_EXTRACTED_BYTES)}."
                        )
                    destination.write(chunk)
            extracted.append(member_name)

    return extracted, ignored, total_bytes


def _save_uploaded_file(uploaded_file, target):
    if target.exists():
        raise ValueError(f"CAD package contains duplicate filename: {target.name}")
    total = 0
    with target.open("wb") as handle:
        for chunk in uploaded_file.chunks():
            total += len(chunk)
            if total > MAX_CAD_UPLOAD_EXTRACTED_BYTES:
                raise ValueError(
                    f"CAD package exceeds the supported extracted size limit "
                    f"of {_format_byte_limit(MAX_CAD_UPLOAD_EXTRACTED_BYTES)}."
                )
            handle.write(chunk)
    return total


def _write_manifest(package_root, *, uploaded_filenames, stored_filenames, ignored_filenames):
    manifest = {
        "schema": "netbox_power_plant.cad_upload_package.v1",
        "stored_at": timezone.now().isoformat(),
        "package_root": str(package_root),
        "uploaded_filenames": list(uploaded_filenames),
        "stored_filenames": list(stored_filenames),
        "ignored_filenames": list(ignored_filenames),
    }
    (package_root / "upload_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_basename(value):
    normalized = str(value).replace("\\", "/")
    name = Path(normalized).name
    if not name:
        raise ValueError("Uploaded CAD package contains a file with an empty name.")
    return name


def _is_ignored_archive_member(raw_name, basename):
    raw_parts = Path(str(raw_name)).parts
    if any(part == "__MACOSX" for part in raw_parts):
        return True
    return basename.startswith(".")


def _format_byte_limit(value):
    gibibytes = value / (1024 * 1024 * 1024)
    if gibibytes >= 1:
        return f"{gibibytes:g} GiB"
    mebibytes = value / (1024 * 1024)
    return f"{mebibytes:g} MiB"
