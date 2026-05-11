#!/usr/bin/env python3
"""Extract color-token evidence from a UI screenshot for JM AI audits.

This script does not decide compliance. It reports image size, optional design
scale, prominent saturated colors, nearest JM AI tokens, and sampled points.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image


JM_TOKENS = {
    "Dark": "#000A1C",
    "White": "#FFFFFF",
    "Assist light purple": "#8F55FD",
    "Primary deep purple": "#6B36FA",
    "Assist standard blue": "#3544EB",
    "Assist deep blue": "#052474",
    "ai/ai-normal": "#6B36FA",
    "ai/ai-hover": "#9975FC",
    "ai/ai-click": "#4B26AF",
    "ai/ai-disable": "#BEAAF3",
    "ai/ai-border": "#EBE5FA",
    "ai/ai-background": "#EDEEFF",
    "ai/ai-light-normal": "#F3F0FF",
    "ai/ai-light-hover": "#F7F5FF",
    "ai/ai-light-click": "#EFEBFE",
    "ai/ai-light-disable": "#F4F2FA",
    "ai/ai-light-border": "#F0EBFC",
    "ai/ai-light-background": "#F4F5FF",
}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


TOKEN_RGB = {name: hex_to_rgb(value) for name, value in JM_TOKENS.items()}


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def nearest_token(rgb: tuple[int, int, int]) -> dict[str, Any]:
    name, token_rgb = min(TOKEN_RGB.items(), key=lambda item: color_distance(rgb, item[1]))
    return {
        "name": name,
        "hex": rgb_to_hex(token_rgb),
        "distance": round(color_distance(rgb, token_rgb), 2),
        "is_close": color_distance(rgb, token_rgb) <= 12,
    }


def parse_size(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    normalized = value.lower().replace(" ", "")
    if "x" not in normalized:
        raise argparse.ArgumentTypeError("size must be WIDTHxHEIGHT")
    left, right = normalized.split("x", 1)
    return int(left), int(right)


def parse_point(value: str) -> tuple[str, int, int]:
    parts = value.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("sample must be label:x:y")
    return parts[0], int(parts[1]), int(parts[2])


def quantize_rgb(rgb: tuple[int, int, int], bucket: int) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(channel / bucket) * bucket)) for channel in rgb)  # type: ignore[return-value]


def is_neutral(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    if max(rgb) - min(rgb) <= 14:
        return True
    if r > 238 and g > 238 and b > 238:
        return True
    if r < 32 and g < 32 and b < 32:
        return True
    return False


def is_saturated(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return max(rgb) - min(rgb) >= 38 and max(rgb) >= 120


def accent_family(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    if r > 180 and g < 120 and b < 110:
        return "red/orange"
    if b > 170 and r > 90 and g < 160:
        return "purple"
    if b > 170 and r < 110:
        return "blue"
    if g > 150 and r < 150:
        return "green/cyan"
    return "other"


def dominant_accents(image: Image.Image, bucket: int, max_colors: int) -> list[dict[str, Any]]:
    thumb = image.copy()
    thumb.thumbnail((900, 900))
    pixels = list(thumb.convert("RGB").getdata())
    counter: Counter[tuple[int, int, int]] = Counter()
    for rgb in pixels:
        if is_neutral(rgb) or not is_saturated(rgb):
            continue
        counter[quantize_rgb(rgb, bucket)] += 1

    total = max(1, len(pixels))
    results = []
    for rgb, count in counter.most_common(max_colors):
        token = nearest_token(rgb)
        results.append(
            {
                "hex": rgb_to_hex(rgb),
                "count": count,
                "coverage": round(count / total, 5),
                "family": accent_family(rgb),
                "nearest_jm_token": token,
                "off_token_candidate": not token["is_close"],
            }
        )
    return results


def sample_points(image: Image.Image, points: list[tuple[str, int, int]]) -> list[dict[str, Any]]:
    width, height = image.size
    output = []
    for label, x, y in points:
        if x < 0 or y < 0 or x >= width or y >= height:
            output.append({"label": label, "x": x, "y": y, "error": "outside image"})
            continue
        rgb = image.getpixel((x, y))[:3]
        token = nearest_token(rgb)
        output.append(
            {
                "label": label,
                "x": x,
                "y": y,
                "hex": rgb_to_hex(rgb),
                "family": accent_family(rgb) if not is_neutral(rgb) else "neutral",
                "nearest_jm_token": token,
                "off_token_candidate": not token["is_close"],
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--design-size", type=parse_size, help="Design canvas size, e.g. 1508x815")
    parser.add_argument("--bucket", type=int, default=8, help="RGB quantization bucket")
    parser.add_argument("--max-colors", type=int, default=24)
    parser.add_argument("--sample", action="append", default=[], type=parse_point, help="Point sample label:x:y")
    parser.add_argument("--output", type=Path, help="Write JSON to path instead of stdout")
    args = parser.parse_args()

    image = Image.open(args.image).convert("RGB")
    width, height = image.size
    design_size = args.design_size
    scale = None
    if design_size:
        scale = {
            "x": round(width / design_size[0], 4),
            "y": round(height / design_size[1], 4),
            "uniform": abs((width / design_size[0]) - (height / design_size[1])) <= 0.02,
        }

    result = {
        "image": str(args.image),
        "image_size_px": {"width": width, "height": height},
        "design_size": {"width": design_size[0], "height": design_size[1]} if design_size else None,
        "scale": scale,
        "jm_tokens": JM_TOKENS,
        "dominant_accent_colors": dominant_accents(image, args.bucket, args.max_colors),
        "samples": sample_points(image, args.sample),
        "notes": [
            "This is evidence only; final compliance decisions must consider component role and scope.",
            "off_token_candidate means RGB distance from nearest JM AI token is greater than 12.",
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
