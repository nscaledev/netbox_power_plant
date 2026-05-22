from io import BytesIO
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase as DjangoTestCase
from django.urls import reverse
from utilities.testing import TestCase

from dcim.models import Site

from netbox_power_plant.choices import (
    PhysicalSpaceKindChoices,
    PlantSourceTypeChoices,
    SpatialAnchorChoices,
    SpatialConfidenceChoices,
    SpatialPlacementKindChoices,
)
from netbox_power_plant.models import (
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.cad_calibration import CoordinateBounds, DwgGeometryExtraction
from netbox_power_plant.services.cad_uploads import (
    CAD_UPLOAD_ROOT,
    MAX_CAD_UPLOAD_PACKAGE_BYTES,
    store_cad_upload_package,
)
from netbox_power_plant.services.madison_cad_approval import approve_madison_cad_underlay
from netbox_power_plant.services.madison_cad_materialization import (
    ingest_madison_cad_underlay,
    materialize_madison_cad_underlay,
)
from netbox_power_plant.services.madison_cad_underlay import build_madison_cad_calibration_report
from netbox_power_plant.services.madison_review import build_madison_underlay_review_summary


class MadisonCadMaterializationTestCase(DjangoTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="GS001", slug="gs001")

    def test_dry_run_rolls_back_persisted_cad_underlay(self):
        report = _build_fake_report()

        summary = materialize_madison_cad_underlay(self.site, report=report)

        self.assertTrue(summary.dry_run)
        self.assertEqual(summary.sheet_count, 3)
        self.assertEqual(summary.layer_count, 3)
        self.assertEqual(summary.current_building_placement.x, Decimal("100.000"))
        self.assertEqual(PlantSourceDocument.objects.count(), 0)
        self.assertEqual(PlantSourceSheet.objects.count(), 0)
        self.assertEqual(PlantSourceLayer.objects.count(), 0)
        self.assertEqual(SpatialFrame.objects.count(), 0)
        self.assertEqual(PhysicalSpace.objects.count(), 0)
        self.assertEqual(SpatialPlacement.objects.count(), 0)
        self.assertEqual(PlantProvenance.objects.count(), 0)

    def test_apply_materializes_cad_sources_site_frame_and_current_building_idempotently(self):
        report = _build_fake_report()

        first_summary = materialize_madison_cad_underlay(self.site, report=report, apply=True)

        self.assertFalse(first_summary.dry_run)
        self.assertGreater(first_summary.created_count, 0)
        self.assertEqual(PlantSourceDocument.objects.count(), 1)
        self.assertEqual(PlantSourceSheet.objects.count(), 3)
        self.assertEqual(PlantSourceLayer.objects.count(), 3)
        self.assertEqual(SpatialFrame.objects.count(), 1)
        self.assertEqual(PhysicalSpace.objects.count(), 2)
        self.assertEqual(SpatialPlacement.objects.count(), 1)
        self.assertEqual(PlantProvenance.objects.count(), 4)

        document = PlantSourceDocument.objects.get()
        self.assertEqual(document.source_type, PlantSourceTypeChoices.TYPE_CAD_EXPORT)
        self.assertEqual(document.metadata["coordinate_plane_bounds"]["width"], "2400.000")
        self.assertEqual(document.metadata["current_building"]["origin_in_site_grid"]["x"], "100.000")

        sheet = PlantSourceSheet.objects.get(sheet_number="E3-1A")
        self.assertEqual(sheet.metadata["sheet"]["pcp"]["units"], "_I")
        self.assertEqual(sheet.metadata["sheet"]["dwg_extraction"]["bounds"]["width"], "1200.000")

        self.assertEqual(first_summary.site_frame.units, "ft")
        self.assertEqual(first_summary.site_frame.width, Decimal("200.000"))
        self.assertEqual(first_summary.site_frame.height, Decimal("100.000"))
        self.assertEqual(first_summary.site_space.space_kind, PhysicalSpaceKindChoices.KIND_CAMPUS)
        self.assertEqual(first_summary.current_building_space.space_kind, PhysicalSpaceKindChoices.KIND_BUILDING)
        self.assertEqual(first_summary.current_building_space.boundary_geometry["x"], "100.000")
        self.assertEqual(first_summary.current_building_space.boundary_geometry["width"], "100.000")
        self.assertEqual(first_summary.current_building_placement.anchor, SpatialAnchorChoices.ANCHOR_LOWER_LEFT)
        self.assertEqual(
            first_summary.current_building_placement.placement_kind,
            SpatialPlacementKindChoices.KIND_INFERRED,
        )
        self.assertEqual(first_summary.current_building_placement.assigned_object, first_summary.current_building_space)

        provenance = PlantProvenance.objects.get(
            assigned_object_type=ContentType.objects.get_for_model(SpatialFrame, for_concrete_model=False),
            assigned_object_id=first_summary.site_frame.pk,
        )
        self.assertEqual(provenance.source_document, document)

        second_summary = materialize_madison_cad_underlay(self.site, report=report, apply=True)

        self.assertEqual(second_summary.created_count, 0)
        self.assertEqual(second_summary.updated_count, 0)
        self.assertEqual(PlantSourceDocument.objects.count(), 1)
        self.assertEqual(PlantSourceSheet.objects.count(), 3)
        self.assertEqual(PlantSourceLayer.objects.count(), 3)
        self.assertEqual(SpatialFrame.objects.count(), 1)
        self.assertEqual(PhysicalSpace.objects.count(), 2)
        self.assertEqual(SpatialPlacement.objects.count(), 1)
        self.assertEqual(PlantProvenance.objects.count(), 4)

    def test_direct_cad_ingest_creates_site_and_materializes_underlay(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch_sheet(root, "E3-1A", "First Floor Power Plan - Area A")
            _touch_sheet(root, "E3-1B", "First Floor Power Plan - Area B")
            _touch_sheet(root, "E3-10", "Enlarged Electrical Plans")

            with patch(
                "netbox_power_plant.services.madison_cad_underlay.read_dwg_geometry_bounds",
                side_effect=_fake_extraction,
            ), patch(
                "netbox_power_plant.services.madison_cad_underlay._read_dwg_line_segments",
                side_effect=_fake_line_segments,
            ):
                summary = ingest_madison_cad_underlay(
                    site_slug="gs002",
                    site_name="Madison, NC",
                    cad_dir=root,
                    source_units="inch",
                    apply=True,
                )

        self.assertTrue(summary.site_created)
        self.assertEqual(summary.site.slug, "gs002")
        self.assertEqual(summary.materialization.sheet_count, 3)
        self.assertEqual(summary.materialization.layer_count, 3)
        self.assertTrue(Site.objects.filter(slug="gs002", name="Madison, NC").exists())
        self.assertEqual(PlantSourceDocument.objects.count(), 1)
        self.assertEqual(PlantSourceSheet.objects.count(), 3)
        self.assertEqual(PlantSourceLayer.objects.count(), 3)
        self.assertEqual(SpatialFrame.objects.count(), 1)
        self.assertEqual(PhysicalSpace.objects.count(), 2)
        self.assertEqual(SpatialPlacement.objects.count(), 1)

    def test_direct_cad_ingest_dry_run_does_not_create_site(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch_sheet(root, "E3-1A", "First Floor Power Plan - Area A")
            _touch_sheet(root, "E3-1B", "First Floor Power Plan - Area B")
            _touch_sheet(root, "E3-10", "Enlarged Electrical Plans")

            with patch(
                "netbox_power_plant.services.madison_cad_underlay.read_dwg_geometry_bounds",
                side_effect=_fake_extraction,
            ), patch(
                "netbox_power_plant.services.madison_cad_underlay._read_dwg_line_segments",
                side_effect=_fake_line_segments,
            ):
                summary = ingest_madison_cad_underlay(
                    site_slug="gs003",
                    site_name="Madison Dry Run",
                    cad_dir=root,
                    source_units="inch",
                    apply=False,
                )

        self.assertTrue(summary.materialization.dry_run)
        self.assertFalse(Site.objects.filter(slug="gs003").exists())
        self.assertEqual(PlantSourceDocument.objects.count(), 0)

    def test_uploaded_zip_package_is_persisted_for_ingest(self):
        with TemporaryDirectory() as media_root:
            with self.settings(MEDIA_ROOT=media_root):
                package = store_cad_upload_package(
                    site_slug="gs001",
                    uploaded_files=[_uploaded_cad_zip()],
                )

                self.assertTrue(package.root.exists())
                self.assertEqual(package.dwg_count, 3)
                self.assertTrue((package.root / "upload_manifest.json").exists())
                self.assertTrue((package.root / "Enovum MAD1-Sheet - E3-1A - First Floor Power Plan - Area A.dwg").exists())

    def test_uploaded_package_rejects_large_declared_request_before_storage(self):
        with TemporaryDirectory() as media_root:
            with self.settings(MEDIA_ROOT=media_root):
                with self.assertRaisesRegex(ValueError, "request size limit"):
                    store_cad_upload_package(
                        site_slug="gs001",
                        uploaded_files=[_declared_large_upload()],
                    )

                self.assertFalse((Path(media_root) / CAD_UPLOAD_ROOT).exists())

    def test_rejected_uploaded_package_cleans_up_partial_storage(self):
        with TemporaryDirectory() as media_root:
            with self.settings(MEDIA_ROOT=media_root):
                with self.assertRaisesRegex(ValueError, "duplicate filename"):
                    store_cad_upload_package(
                        site_slug="gs001",
                        uploaded_files=[
                            SimpleUploadedFile("duplicate.dwg", b"dwg"),
                            SimpleUploadedFile("duplicate.dwg", b"dwg"),
                        ],
                    )

                package_parent = Path(media_root) / CAD_UPLOAD_ROOT / "gs001"
                self.assertEqual(list(package_parent.iterdir()), [])

    def test_review_summary_exposes_materialized_cad_underlay(self):
        report = _build_fake_report()
        materialize_madison_cad_underlay(self.site, report=report, apply=True)

        summary = build_madison_underlay_review_summary("gs001")

        self.assertIsNotNone(summary.cad_underlay)
        self.assertTrue(summary.cad_underlay.materialized)
        self.assertEqual(summary.cad_underlay.site_frame.width, Decimal("200.000"))
        self.assertEqual(summary.cad_underlay.current_building_placement.x, Decimal("100.000"))
        self.assertIn("Source units are set to 'inch'", summary.cad_underlay.warnings[0])

    def test_approval_promotes_underlay_and_seeds_decomposition_spaces(self):
        report = _build_fake_report()
        materialize_madison_cad_underlay(self.site, report=report, apply=True)

        result = approve_madison_cad_underlay(
            self.site,
            overrides=None,
            reviewer="operator",
        )

        self.assertEqual(result.site_frame.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertEqual(result.site_space.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertEqual(
            result.current_building_space.confidence,
            SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
        )
        self.assertEqual(
            result.current_building_placement.confidence,
            SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
        )
        self.assertEqual(result.current_building_placement.placement_kind, SpatialPlacementKindChoices.KIND_PHYSICAL)
        self.assertEqual(result.source_document.metadata["review_state"], "approved")
        self.assertEqual(result.source_document.metadata["approved_by"], "operator")
        self.assertEqual(len(result.decomposition_spaces), 5)
        self.assertEqual(PhysicalSpace.objects.count(), 7)
        self.assertEqual(PlantProvenance.objects.filter(is_authoritative=True).count(), 9)
        self.assertTrue(
            PhysicalSpace.objects.filter(
                site=self.site,
                space_kind=PhysicalSpaceKindChoices.KIND_FLOOR,
                confidence=SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
            ).exists()
        )
        self.assertEqual(
            PhysicalSpace.objects.filter(
                site=self.site,
                space_kind=PhysicalSpaceKindChoices.KIND_DATA_HALL,
                confidence=SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL,
            ).count(),
            2,
        )

    def test_approval_applies_operator_dimension_overrides(self):
        report = _build_fake_report()
        materialize_madison_cad_underlay(self.site, report=report, apply=True)

        form_data = {
            "source_units": "inch",
            "site_width": "210.000",
            "site_height": "110.000",
            "building_origin_x": "105.000",
            "building_origin_y": "2.000",
            "building_width": "90.000",
            "building_height": "80.000",
            "notes": "Adjusted after CAD operator review.",
        }
        from netbox_power_plant.forms import MadisonCadUnderlayApprovalForm

        form = MadisonCadUnderlayApprovalForm({**form_data, "confirm": "on"})
        self.assertTrue(form.is_valid(), form.errors)

        result = approve_madison_cad_underlay(self.site, overrides=form.to_overrides(), reviewer="operator")

        self.assertEqual(result.site_frame.width, Decimal("210.000"))
        self.assertEqual(result.site_frame.height, Decimal("110.000"))
        self.assertEqual(result.current_building_placement.x, Decimal("105.000"))
        self.assertEqual(result.current_building_placement.y, Decimal("2.000"))
        self.assertEqual(result.current_building_placement.width, Decimal("90.000"))
        self.assertEqual(result.current_building_placement.depth, Decimal("80.000"))
        self.assertEqual(result.current_building_space.boundary_geometry["x"], "105.000")
        self.assertEqual(result.source_document.metadata["approval_notes"], "Adjusted after CAD operator review.")


class MadisonCadUnderlayReviewViewTestCase(TestCase):
    user_permissions = (
        "dcim.add_site",
        "dcim.view_site",
        "netbox_power_plant.view_physicalspace",
        "netbox_power_plant.view_plantsourcedocument",
        "netbox_power_plant.view_spatialframe",
        "netbox_power_plant.view_spatialplacement",
        "netbox_power_plant.add_plantsourcedocument",
        "netbox_power_plant.add_spatialframe",
        "netbox_power_plant.change_spatialframe",
    )

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="GS001", slug="gs001")

    def test_review_page_renders_materialized_cad_underlay(self):
        report = _build_fake_report()
        materialize_madison_cad_underlay(self.site, report=report, apply=True)

        response = self.client.get(reverse("plugins:netbox_power_plant:madison_underlay_review"))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "CAD Site Underlay")
        self.assertContains(response, "GS001 Madison CAD Site Coordinate Plane")
        self.assertContains(response, "GS001 Madison Current Building Footprint")
        self.assertContains(response, "Origin 100.000, 0.000")
        self.assertContains(response, "Refresh CAD Package")
        self.assertContains(response, "Approve CAD Underlay")

    def test_review_page_file_picker_accepts_zip_archives_and_cad_files(self):
        response = self.client.get(reverse("plugins:netbox_power_plant:madison_underlay_review"))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'type="file"')
        self.assertContains(response, 'name="cad_package"')
        self.assertContains(response, 'accept=".zip,.dwg,.pcp,.ctb,.stb,.dxf"')
        self.assertContains(response, "multiple")
        self.assertContains(response, "Upload a ZIP archive of the CAD folder")

    def test_review_page_ingests_cad_package(self):
        with TemporaryDirectory() as media_root:
            with patch(
                "netbox_power_plant.services.madison_cad_underlay.read_dwg_geometry_bounds",
                side_effect=_fake_extraction,
            ), patch(
                "netbox_power_plant.services.madison_cad_underlay._read_dwg_line_segments",
                side_effect=_fake_line_segments,
            ), self.settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse("plugins:netbox_power_plant:madison_underlay_review"),
                    {
                        "action": "ingest_cad_underlay",
                        "site_slug": "gs002",
                        "site_name": "Madison, NC",
                        "source_units": "inch",
                        "confirm": "on",
                        "cad_package": _uploaded_cad_zip(),
                    },
                    follow=True,
                )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "CAD Site Underlay")
        self.assertContains(response, "Madison, NC Madison CAD Site Coordinate Plane")
        self.assertContains(response, "Origin 100.000, 0.000")
        self.assertTrue(Site.objects.filter(slug="gs002", name="Madison, NC").exists())

    def test_review_page_approves_cad_underlay_with_overrides(self):
        report = _build_fake_report()
        materialize_madison_cad_underlay(self.site, report=report, apply=True)

        response = self.client.post(
            reverse("plugins:netbox_power_plant:madison_underlay_review"),
            {
                "action": "approve_cad_underlay",
                "site": "gs001",
                "source_units": "inch",
                "site_width": "210.000",
                "site_height": "110.000",
                "building_origin_x": "105.000",
                "building_origin_y": "2.000",
                "building_width": "90.000",
                "building_height": "80.000",
                "confirm": "on",
            },
            follow=True,
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "Approved")
        placement = SpatialPlacement.objects.get(slug="gs001-madison-current-building-placement")
        self.assertEqual(placement.x, Decimal("105.000"))
        self.assertTrue(PhysicalSpace.objects.filter(name="GS001 Madison First Floor").exists())


def _build_fake_report():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _touch_sheet(root, "E3-1A", "First Floor Power Plan - Area A")
        _touch_sheet(root, "E3-1B", "First Floor Power Plan - Area B")
        _touch_sheet(root, "E3-10", "Enlarged Electrical Plans")

        with patch(
            "netbox_power_plant.services.madison_cad_underlay.read_dwg_geometry_bounds",
            side_effect=_fake_extraction,
        ), patch(
            "netbox_power_plant.services.madison_cad_underlay._read_dwg_line_segments",
            side_effect=_fake_line_segments,
        ):
            return build_madison_cad_calibration_report(
                root,
                sheet_numbers=("E3-1A", "E3-1B", "E3-10"),
                site_grid_sheet_numbers=("E3-1A", "E3-1B"),
                source_units="inch",
            )


def _touch_sheet(root, sheet, title):
    stem = f"Enovum MAD1-Sheet - {sheet} - {title}"
    (root / f"{stem}.dwg").write_text("dwg", encoding="utf-8")
    (root / f"{stem}.pcp").write_text("UNITS = _I\nSCALE = 1=1\n", encoding="utf-8")


def _uploaded_cad_zip():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for sheet, title in (
            ("E3-1A", "First Floor Power Plan - Area A"),
            ("E3-1B", "First Floor Power Plan - Area B"),
            ("E3-10", "Enlarged Electrical Plans"),
        ):
            stem = f"Enovum MAD1-Sheet - {sheet} - {title}"
            archive.writestr(f"2026.04.02_Enovum MAD1_Electical CAD/{stem}.dwg", "dwg")
            archive.writestr(f"2026.04.02_Enovum MAD1_Electical CAD/{stem}.pcp", "UNITS = _I\nSCALE = 1=1\n")
    buffer.seek(0)
    return SimpleUploadedFile("madison-cad-package.zip", buffer.getvalue(), content_type="application/zip")


def _declared_large_upload():
    class DeclaredLargeUpload:
        name = "too-large.dwg"
        size = MAX_CAD_UPLOAD_PACKAGE_BYTES + 1

        def chunks(self):
            raise AssertionError("Oversized upload should be rejected before streaming.")

    return DeclaredLargeUpload()


def _fake_extraction(path):
    sheet = _sheet_from_path(path)
    bounds = {
        "E3-1A": CoordinateBounds.from_values(0, 0, 1200, 1200),
        "E3-1B": CoordinateBounds.from_values(1200, 0, 2400, 1200),
        "E3-10": CoordinateBounds.from_values(5000, 5000, 7000, 5500),
    }[sheet]
    return DwgGeometryExtraction(
        path=str(path),
        decode_version="AC1032",
        entity_count=10,
        point_count=20,
        discarded_point_count=1,
        entity_type_counts={"LINE": 10},
        bounds=bounds,
    )


def _fake_line_segments(path):
    return (
        (Decimal("0"), Decimal("0"), Decimal("100"), Decimal("0"), Decimal("100")),
        (Decimal("1200"), Decimal("0"), Decimal("2400"), Decimal("0"), Decimal("1200")),
        (Decimal("1200"), Decimal("1200"), Decimal("2400"), Decimal("1200"), Decimal("1200")),
        (Decimal("1200"), Decimal("0"), Decimal("1200"), Decimal("1200"), Decimal("1200")),
        (Decimal("2400"), Decimal("0"), Decimal("2400"), Decimal("1200"), Decimal("1200")),
    )


def _sheet_from_path(path):
    name = Path(path).name
    return name.split(" - ")[1]
