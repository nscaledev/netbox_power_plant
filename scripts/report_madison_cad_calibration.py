#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from netbox_power_plant.services.madison_cad_underlay import (
    build_madison_cad_calibration_report,
    write_madison_cad_calibration_artifacts,
)


def main():
    parser = argparse.ArgumentParser(description="Build Madison CAD calibration manifest and Markdown report.")
    parser.add_argument("--cad-dir", required=True, help="Directory containing the Madison DWG/PCP files.")
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Directory for madison_cad_calibration_manifest.json and madison_cad_calibration_report.md.",
    )
    parser.add_argument(
        "--source-units",
        default="inch",
        help="CAD model unit assumption used for physical grid sizing. Use an empty string to block grid sizing.",
    )
    args = parser.parse_args()

    source_units = args.source_units.strip() or None
    report = build_madison_cad_calibration_report(args.cad_dir, source_units=source_units)
    out_dir = Path(args.out_dir)
    write_madison_cad_calibration_artifacts(
        report,
        manifest_path=out_dir / "madison_cad_calibration_manifest.json",
        markdown_path=out_dir / "madison_cad_calibration_report.md",
    )
    print(out_dir / "madison_cad_calibration_manifest.json")
    print(out_dir / "madison_cad_calibration_report.md")


if __name__ == "__main__":
    main()
