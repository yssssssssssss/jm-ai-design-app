#!/usr/bin/env python3
"""Measure UI regions and distances for JM AI design audits.

Input JSON can be either an array of regions or an object with:
{
  "regions": [{"id": "logo", "bbox": [x, y, w, h]}],
  "distances": [{"id": "gap", "from": "a", "to": "b", "axis": "x"}]
}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image


SPACING_TOKENS = [0, 2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 56]
TYPE_TOKENS = [
    {"role": "Display", "font_size": 32, "line_height": 48, "weight": "Bold"},
    {"role": "Display", "font_size": 24, "line_height": 36, "weight": "Bold"},
    {"role": "H1", "font_size": 18, "line_height": 28, "weight": "Bold"},
    {"role": "H2", "font_size": 16, "line_height": 24, "weight": "Bold"},
    {"role": "H3", "font_size": 14, "line_height": 22, "weight": "Bold"},
    {"role": "Body", "font_size": 14, "line_height": 22, "weight": "Regular"},
    {"role": "Helper", "font_size": 12, "line_height": 18, "weight": "Regular"},
]


def parse_size(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    normalized = value.lower().replace(" ", "")
    if "x" not in normalized:
        raise argparse.ArgumentTypeError("size must be WIDTHxHEIGHT")
    left, right = normalized.split("x", 1)
    return int(left), int(right)


def valid_bbox(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(v, (int, float)) for v in value)
        and value[2] > 0
        and value[3] > 0
    )


def nearest_spacing(value: float) -> dict[str, Any]:
    token = min(SPACING_TOKENS, key=lambda item: abs(item - value))
    delta = round(value - token, 2)
    return {
        "token": token,
        "delta": delta,
        "passes_with_1px_tolerance": abs(delta) <= 1,
    }


def nearest_type_by_height(height: float) -> dict[str, Any]:
    token = min(TYPE_TOKENS, key=lambda item: abs(item["line_height"] - height))
    return {
        "role": token["role"],
        "font_size": token["font_size"],
        "line_height": token["line_height"],
        "weight": token["weight"],
        "delta_from_line_height": round(height - token["line_height"], 2),
    }


def load_input(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data, []
    if isinstance(data, dict):
        regions = data.get("regions", [])
        distances = data.get("distances", [])
        if not isinstance(regions, list) or not isinstance(distances, list):
            raise ValueError("regions and distances must be arrays")
        return regions, distances
    raise ValueError("regions file must be a JSON array or object")


def to_design(value: float, scale: float | None) -> float:
    return value / scale if scale else value


def clamp_box(bbox: list[float], width: int, height: int, pad: int = 0) -> tuple[int, int, int, int]:
    x, y, w, h = bbox
    # Keep crops valid even when the requested bbox is partially or fully outside the image.
    left = max(0, min(width - 1, int(round(x)) - pad))
    top = max(0, min(height - 1, int(round(y)) - pad))
    right = min(width, max(left + 1, int(round(x + w)) + pad))
    bottom = min(height, max(top + 1, int(round(y + h)) + pad))
    return left, top, right, bottom


def measure_region(region: dict[str, Any], scale_x: float | None, scale_y: float | None) -> dict[str, Any]:
    x, y, w, h = [float(v) for v in region["bbox"]]
    design_w = to_design(w, scale_x)
    design_h = to_design(h, scale_y)
    role_hint = region.get("role_hint")
    measure_kind = str(region.get("measure_kind") or "component")
    result = {
        "id": str(region.get("id", "")),
        "title": region.get("title"),
        "role_hint": role_hint,
        "measure_kind": measure_kind,
        "bbox_px": [round(x, 2), round(y, 2), round(w, 2), round(h, 2)],
        "bbox_design_px": [
            round(to_design(x, scale_x), 2),
            round(to_design(y, scale_y), 2),
            round(design_w, 2),
            round(design_h, 2),
        ],
        "center_px": [round(x + w / 2, 2), round(y + h / 2, 2)],
    }
    if measure_kind in {"spacing", "gap", "padding"} or design_w <= 64:
        result["nearest_width_spacing"] = nearest_spacing(design_w)
    if measure_kind in {"spacing", "gap", "padding"} or design_h <= 64:
        result["nearest_height_spacing"] = nearest_spacing(design_h)
    if role_hint in {"text", "typography", "label", "heading"}:
        result["nearest_type_by_bbox_height"] = nearest_type_by_height(design_h)
        if design_h > 64:
            result["warning"] = "Text bbox appears too tall; use a tighter text-only bbox for typography inference."
    return result


def gap_between(a: list[float], b: list[float], axis: str) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if axis == "x":
        if ax <= bx:
            return bx - (ax + aw)
        return ax - (bx + bw)
    if ay <= by:
        return by - (ay + ah)
    return ay - (by + bh)


def measure_distance(
    distance: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    scale_x: float | None,
    scale_y: float | None,
) -> dict[str, Any]:
    from_id = str(distance["from"])
    to_id = str(distance["to"])
    axis = str(distance.get("axis", "x"))
    if axis not in {"x", "y"}:
        raise ValueError(f"invalid axis for distance {distance.get('id')}: {axis}")
    raw = gap_between(by_id[from_id]["bbox"], by_id[to_id]["bbox"], axis)
    scale = scale_x if axis == "x" else scale_y
    design = to_design(raw, scale)
    return {
        "id": str(distance.get("id", f"{from_id}-{to_id}-{axis}")),
        "from": from_id,
        "to": to_id,
        "axis": axis,
        "gap_px": round(raw, 2),
        "gap_design_px": round(design, 2),
        "nearest_spacing": nearest_spacing(design),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("regions", type=Path)
    parser.add_argument("--design-size", type=parse_size, help="Design canvas size, e.g. 1508x815")
    parser.add_argument("--output", type=Path, help="Write JSON to path instead of stdout")
    parser.add_argument("--crop-dir", type=Path, help="Optionally write crops for regions")
    parser.add_argument("--crop-pad", type=int, default=12)
    args = parser.parse_args()

    image = Image.open(args.image).convert("RGB")
    width, height = image.size
    design_size = args.design_size
    scale_x = width / design_size[0] if design_size else None
    scale_y = height / design_size[1] if design_size else None

    regions, distances = load_input(args.regions)
    valid_regions = [item for item in regions if isinstance(item, dict) and valid_bbox(item.get("bbox"))]
    by_id = {str(item.get("id")): item for item in valid_regions}

    measured_regions = [measure_region(item, scale_x, scale_y) for item in valid_regions]
    measured_distances = [
        measure_distance(item, by_id, scale_x, scale_y)
        for item in distances
        if isinstance(item, dict) and str(item.get("from")) in by_id and str(item.get("to")) in by_id
    ]

    if args.crop_dir:
        args.crop_dir.mkdir(parents=True, exist_ok=True)
        for item in valid_regions:
            region_id = str(item.get("id"))
            crop = image.crop(clamp_box(item["bbox"], width, height, args.crop_pad))
            crop.save(args.crop_dir / f"region-{region_id}.png")

    result = {
        "image": str(args.image),
        "image_size_px": {"width": width, "height": height},
        "design_size": {"width": design_size[0], "height": design_size[1]} if design_size else None,
        "scale": {
            "x": round(scale_x, 4) if scale_x else None,
            "y": round(scale_y, 4) if scale_y else None,
            "uniform": abs(scale_x - scale_y) <= 0.02 if scale_x and scale_y else None,
        },
        "spacing_tokens": SPACING_TOKENS,
        "type_tokens": TYPE_TOKENS,
        "regions": measured_regions,
        "distances": measured_distances,
        "notes": [
            "Text bbox height is not exact font size; use nearest_type_by_bbox_height as evidence only.",
            "Pass/fail requires component role and visual context.",
        ],
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
