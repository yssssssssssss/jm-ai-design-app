from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"


class EvidenceToolError(Exception):
    pass


def _sample_label(value: Any) -> str:
    label = re.sub(r"[^0-9A-Za-z_-]+", "-", str(value)).strip("-")
    return label or "sample"


def _run(args: list[str]) -> None:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "evidence tool failed"
        raise EvidenceToolError(message)


def _valid_bbox(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and value[2] > 0
        and value[3] > 0
    )


def build_issues_json(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for issue in issues:
        bbox = issue.get("bbox")
        if not _valid_bbox(bbox):
            continue
        output.append(
            {
                "id": str(issue.get("id") or "issue"),
                "title": str(
                    issue.get("title")
                    or issue.get("current_observation")
                    or issue.get("id")
                    or "问题"
                ),
                "severity": str(issue.get("severity") or "中"),
                "category": str(issue.get("category") or "其他"),
                "bbox": bbox,
            }
        )
    return output


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_regions_json(
    path: Path,
    regions: list[dict[str, Any]],
    distances: list[dict[str, Any]],
) -> None:
    write_json(path, {"regions": regions, "distances": distances})


def run_color_analysis(
    image_path: Path,
    output_path: Path,
    sample_points: list[dict[str, Any]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        sys.executable,
        str(SCRIPTS_DIR / "analyze_image_tokens.py"),
        str(image_path),
        "--output",
        str(output_path),
    ]
    for point in sample_points:
        args.extend(["--sample", f"{_sample_label(point['label'])}:{point['x']}:{point['y']}"])
    _run(args)


def run_measurements(
    image_path: Path,
    regions_path: Path,
    output_path: Path,
    crop_dir: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "measure_regions.py"),
            str(image_path),
            str(regions_path),
            "--output",
            str(output_path),
            "--crop-dir",
            str(crop_dir),
        ]
    )


def run_annotations(image_path: Path, issues_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "annotate_issues.py"),
            str(image_path),
            str(issues_path),
            str(output_dir),
        ]
    )
