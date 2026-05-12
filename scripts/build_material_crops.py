from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
MATERIALS_PATH = ROOT / "assets" / "spec-materials" / "materials.json"


def _validate_bbox(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("bbox must be [left, top, right, bottom]")
    left, top, right, bottom = [int(item) for item in value]
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise ValueError(f"invalid bbox: {value}")
    return left, top, right, bottom


def build_crops(materials_path: Path = MATERIALS_PATH) -> int:
    materials = json.loads(materials_path.read_text(encoding="utf-8"))
    if not isinstance(materials, list):
        raise ValueError("materials.json must contain a list")

    count = 0
    for material in materials:
        source_image = material.get("source_image")
        crop_path = material.get("crop_path")
        if not source_image or not crop_path:
            continue

        source = ROOT / str(source_image)
        target = materials_path.parent / str(crop_path)
        bbox = _validate_bbox(material.get("bbox"))

        with Image.open(source) as image:
            left, top, right, bottom = bbox
            if right > image.width or bottom > image.height:
                raise ValueError(
                    f"{material.get('id', crop_path)} bbox {bbox} exceeds {source} {image.size}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            image.crop(bbox).save(target)
            count += 1
    return count


if __name__ == "__main__":
    print(f"built {build_crops()} material crops")
