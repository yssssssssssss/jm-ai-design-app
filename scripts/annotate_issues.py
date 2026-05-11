#!/usr/bin/env python3
"""Generate annotated screenshots and issue crops for JM AI design audits."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


COLORS = {
    "高": (217, 45, 32),
    "中": (181, 71, 8),
    "低": (107, 114, 128),
}


def load_issues(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("issues.json must be a JSON array")
    return [item for item in data if isinstance(item, dict) and valid_bbox(item.get("bbox"))]


def valid_bbox(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(v, (int, float)) for v in value)
        and value[2] > 0
        and value[3] > 0
    )


def clamp_bbox(bbox: list[float], width: int, height: int, pad: int = 24) -> tuple[int, int, int, int]:
    x, y, w, h = bbox
    left = max(0, int(round(x)) - pad)
    top = max(0, int(round(y)) - pad)
    right = min(width, int(round(x + w)) + pad)
    bottom = min(height, int(round(y + h)) + pad)
    return left, top, right, bottom


def draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: tuple[int, int, int]) -> None:
    font = ImageFont.load_default()
    left, top = xy
    bbox = draw.textbbox((left, top), text, font=font)
    pad_x, pad_y = 6, 4
    bg = (max(color[0] - 20, 0), max(color[1] - 20, 0), max(color[2] - 20, 0))
    draw.rounded_rectangle(
        (bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y),
        radius=5,
        fill=bg,
    )
    draw.text((left, top), text, fill=(255, 255, 255), font=font)


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: annotate_issues.py <input-image> <issues.json> <output-dir>", file=sys.stderr)
        return 2

    image_path = Path(sys.argv[1])
    issues_path = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    output_dir.mkdir(parents=True, exist_ok=True)

    image = Image.open(image_path).convert("RGB")
    issues = load_issues(issues_path)
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)

    width, height = image.size

    for index, issue in enumerate(issues, start=1):
        issue_id = str(issue.get("id") or f"issue-{index}")
        severity = str(issue.get("severity") or "中")
        color = COLORS.get(severity, COLORS["中"])
        x, y, w, h = [int(round(v)) for v in issue["bbox"]]
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))

        for offset in range(3):
            draw.rectangle((x - offset, y - offset, x + w + offset, y + h + offset), outline=color)
        draw_label(draw, (x, max(0, y - 22)), f"{index}. {issue_id}", color)

        crop_box = clamp_bbox([x, y, w, h], width, height)
        crop = image.crop(crop_box)
        crop.save(output_dir / f"issue-{issue_id}.png")

    annotated.save(output_dir / "annotated.png")
    print(f"wrote {output_dir / 'annotated.png'}")
    print(f"wrote {len(issues)} issue crop(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
