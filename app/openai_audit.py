from __future__ import annotations

import base64
import copy
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from PIL import Image


AUDIT_IMAGE_MAX_SIDE = 1600
DEGRADED_AUDIT_IMAGE_MAX_SIDE = 1200
AUDIT_IMAGE_JPEG_QUALITY = 85
REQUIRED_KEYS = {
    "screen_context",
    "overall_conclusion",
    "major_issues",
    "passes",
    "issues",
    "sample_points",
    "regions",
    "distances",
    "checklist",
    "cannot_verify",
}
ARRAY_KEYS = REQUIRED_KEYS - {"screen_context", "overall_conclusion"}


class AuditModelError(Exception):
    pass


@dataclass(frozen=True)
class AuditImageInput:
    data_url: str
    original_size: tuple[int, int]
    audit_size: tuple[int, int]


class _ResponsesClient(Protocol):
    def create(self, **kwargs: Any) -> Any:
        ...


class _ChatCompletionsClient(Protocol):
    def create(self, **kwargs: Any) -> Any:
        ...


class _ChatClient(Protocol):
    completions: _ChatCompletionsClient


class _OpenAIClient(Protocol):
    responses: _ResponsesClient
    chat: _ChatClient


def _strict_object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def _nullable_string() -> dict[str, Any]:
    return {"anyOf": [{"type": "string"}, {"type": "null"}]}


def _nullable_bbox() -> dict[str, Any]:
    return {
        "anyOf": [
            {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
            },
            {"type": "null"},
        ]
    }


def compact_audit_spec(spec_text: str) -> str:
    """Remove sections that the runtime prompt explicitly excludes."""
    compact_lines: list[str] = []
    skipping_section = False

    for line in spec_text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            skipping_section = heading == "typography"
            if skipping_section:
                continue

        if skipping_section:
            continue

        lowered = line.lower()
        if lowered.strip() == "- typography":
            continue
        if "font family" in lowered or "font weight" in lowered:
            continue

        compact_lines.append(line)

    compact_text = "\n".join(compact_lines).strip()
    while "\n\n\n" in compact_text:
        compact_text = compact_text.replace("\n\n\n", "\n\n")
    return compact_text


def build_audit_prompt(
    spec_text: str,
    declared_screen_size: tuple[int, int] | None = None,
    actual_image_size: tuple[int, int] | None = None,
    audit_image_size: tuple[int, int] | None = None,
) -> str:
    size_context = ""
    if actual_image_size or audit_image_size or declared_screen_size:
        lines = ["\n\n尺寸上下文:"]
        if actual_image_size:
            lines.append(
                f"- 上传图片实际像素尺寸：{actual_image_size[0]}px × {actual_image_size[1]}px。"
            )
        if audit_image_size and audit_image_size != actual_image_size:
            lines.append(
                f"- 模型当前看到的压缩审核图尺寸：{audit_image_size[0]}px × {audit_image_size[1]}px。"
            )
            lines.append(
                "- 坐标输出要求：bbox、sample_points、regions 必须使用当前可见审核图坐标；系统会映射回原图。"
            )
        if declared_screen_size:
            lines.append(
                f"- 用户声明的稿件基准尺寸：{declared_screen_size[0]}px × {declared_screen_size[1]}px。"
            )
            lines.append(
                "- 请将用户声明尺寸作为判断间距、组件大小、字号比例、布局密度的前置上下文。"
            )
        lines.append(
            "- 如果实际图片像素尺寸与用户声明尺寸不一致，请说明差异，不要编造无法确认的测量结论。"
        )
        size_context = "\n".join(lines)

    return (
        "你是 JM AI 设计规范审核助手。必须根据下面的 JM AI 规范审核图片。"
        "输出必须是 JSON，字段必须完整。证据和推断要分开，无法确认的项目放入 cannot_verify。"
        "问题 bbox 使用 [x, y, w, h] 截图像素坐标；无法可靠定位时 bbox 为 null。"
        "不要编造测量数据；只有能从截图判断或后续工具可测量的内容才写入证据请求。"
        "regions 字段用于请求测量区域，distances 字段用于请求间距测量。"
        "暂时不要审核字体相关问题，包括字体族、字号、字重、行高、typography、font；"
        "不要在 issues、checklist、passes、cannot_verify、regions 中输出字体相关条目。"
        f"{size_context}"
        "\n\nJM AI SPEC:\n"
        f"{spec_text}"
    )


def audit_json_schema() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "jm_ai_image_audit",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(REQUIRED_KEYS),
            "properties": {
                "screen_context": {"type": "string"},
                "overall_conclusion": {"type": "string"},
                "major_issues": {"type": "array", "items": {"type": "string"}},
                "passes": {"type": "array", "items": {"type": "string"}},
                "issues": {
                    "type": "array",
                    "items": _strict_object_schema(
                        {
                            "id": {"type": "string"},
                            "category": {"type": "string"},
                            "severity": {"type": "string", "enum": ["高", "中", "低"]},
                            "location": {"type": "string"},
                            "current_observation": {"type": "string"},
                            "spec_expectation": {"type": "string"},
                            "recommendation": {"type": "string"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                            "bbox": _nullable_bbox(),
                        }
                    ),
                },
                "sample_points": {
                    "type": "array",
                    "items": _strict_object_schema(
                        {
                            "label": {"type": "string"},
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                        }
                    ),
                },
                "regions": {
                    "type": "array",
                    "items": _strict_object_schema(
                        {
                            "id": {"type": "string"},
                            "title": _nullable_string(),
                            "bbox": _nullable_bbox(),
                            "role_hint": _nullable_string(),
                            "measure_kind": {
                                "type": "string",
                                "enum": [
                                    "component",
                                    "spacing",
                                    "gap",
                                    "padding",
                                    "text",
                                    "typography",
                                ],
                            },
                        }
                    ),
                },
                "distances": {
                    "type": "array",
                    "items": _strict_object_schema(
                        {
                            "id": {"type": "string"},
                            "title": _nullable_string(),
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "axis": {"type": "string", "enum": ["x", "y"]},
                        }
                    ),
                },
                "checklist": {
                    "type": "array",
                    "items": _strict_object_schema(
                        {
                            "item": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["通过", "不通过", "无法确认"],
                            },
                            "evidence": _nullable_string(),
                        }
                    ),
                },
                "cannot_verify": {
                    "type": "array",
                    "items": _strict_object_schema(
                        {
                            "item": {"type": "string"},
                            "reason": {"type": "string"},
                        }
                    ),
                },
            },
        },
    }


def parse_audit_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AuditModelError("模型返回的 JSON 无法解析") from exc

    if not isinstance(data, dict):
        raise AuditModelError("模型返回的 JSON 必须是对象")

    missing = REQUIRED_KEYS - set(data)
    if missing:
        raise AuditModelError(f"模型返回缺少字段: {', '.join(sorted(missing))}")

    for key in ARRAY_KEYS:
        if not isinstance(data[key], list):
            raise AuditModelError(f"模型返回字段必须是数组: {key}")

    return data


def image_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    media_type = "image/png"
    if suffix in {".jpg", ".jpeg"}:
        media_type = "image/jpeg"
    elif suffix == ".webp":
        media_type = "image/webp"

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _data_url_from_bytes(payload: bytes, media_type: str) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _resized_dimensions(size: tuple[int, int], max_side: int) -> tuple[int, int]:
    width, height = size
    if max_side <= 0 or max(width, height) <= max_side:
        return size

    scale = max_side / max(width, height)
    return (max(1, round(width * scale)), max(1, round(height * scale)))


def _rgb_image(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, "#FFFFFF")
        background.paste(image, mask=image.getchannel("A"))
        return background
    return image.convert("RGB")


def prepare_audit_image(
    path: Path,
    max_side: int = AUDIT_IMAGE_MAX_SIDE,
    jpeg_quality: int = AUDIT_IMAGE_JPEG_QUALITY,
) -> AuditImageInput:
    with Image.open(path) as image:
        original_size = image.size
        audit_size = _resized_dimensions(original_size, max_side)

        if audit_size == original_size:
            return AuditImageInput(
                data_url=image_data_url(path),
                original_size=original_size,
                audit_size=audit_size,
            )

        resized = _rgb_image(image).resize(audit_size, Image.Resampling.LANCZOS)
        buffer = BytesIO()
        resized.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)

    return AuditImageInput(
        data_url=_data_url_from_bytes(buffer.getvalue(), "image/jpeg"),
        original_size=original_size,
        audit_size=audit_size,
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _scale_pixel(value: int | float, factor: float) -> int:
    return int(round(value * factor))


def _scale_bbox(
    bbox: Any,
    scale_x: float,
    scale_y: float,
) -> Any:
    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or not all(_is_number(value) for value in bbox)
    ):
        return bbox
    x, y, width, height = bbox
    return [
        _scale_pixel(x, scale_x),
        _scale_pixel(y, scale_y),
        _scale_pixel(width, scale_x),
        _scale_pixel(height, scale_y),
    ]


def remap_audit_coordinates(
    audit: dict[str, Any],
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> dict[str, Any]:
    if source_size == target_size:
        return audit

    source_width, source_height = source_size
    target_width, target_height = target_size
    if source_width <= 0 or source_height <= 0:
        return audit

    scale_x = target_width / source_width
    scale_y = target_height / source_height
    mapped = copy.deepcopy(audit)

    for issue in mapped.get("issues", []):
        if isinstance(issue, dict):
            issue["bbox"] = _scale_bbox(issue.get("bbox"), scale_x, scale_y)

    for point in mapped.get("sample_points", []):
        if (
            isinstance(point, dict)
            and _is_number(point.get("x"))
            and _is_number(point.get("y"))
        ):
            point["x"] = _scale_pixel(point["x"], scale_x)
            point["y"] = _scale_pixel(point["y"], scale_y)

    for region in mapped.get("regions", []):
        if isinstance(region, dict):
            region["bbox"] = _scale_bbox(region.get("bbox"), scale_x, scale_y)

    return mapped


def audit_image(
    client: _OpenAIClient,
    model: str,
    image_path: Path,
    spec_text: str,
    reasoning_effort: str | None = None,
    declared_screen_size: tuple[int, int] | None = None,
    max_image_side: int = AUDIT_IMAGE_MAX_SIDE,
    image_detail: str = "high",
) -> dict[str, Any]:
    audit_input = prepare_audit_image(image_path, max_side=max_image_side)
    request: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": build_audit_prompt(
                            spec_text,
                            declared_screen_size=declared_screen_size,
                            actual_image_size=audit_input.original_size,
                            audit_image_size=audit_input.audit_size,
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": audit_input.data_url,
                        "detail": image_detail,
                    },
                ],
            }
        ],
        "text": {"format": audit_json_schema()},
    }
    if reasoning_effort:
        request["reasoning"] = {"effort": reasoning_effort}

    response = client.responses.create(**request)
    audit = parse_audit_json(response.output_text)
    return remap_audit_coordinates(
        audit,
        source_size=audit_input.audit_size,
        target_size=audit_input.original_size,
    )


def audit_image_with_chat(
    client: _OpenAIClient,
    model: str,
    image_path: Path,
    spec_text: str,
    reasoning_effort: str | None = None,
    declared_screen_size: tuple[int, int] | None = None,
    max_image_side: int = AUDIT_IMAGE_MAX_SIDE,
    image_detail: str = "high",
) -> dict[str, Any]:
    _ = image_detail
    audit_input = prepare_audit_image(image_path, max_side=max_image_side)
    prompt = (
        build_audit_prompt(
            spec_text,
            declared_screen_size=declared_screen_size,
            actual_image_size=audit_input.original_size,
            audit_image_size=audit_input.audit_size,
        )
        + "\n\n必须只输出一个 JSON 对象，不要输出 Markdown，不要包裹代码块。"
    )
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": audit_input.data_url}},
                ],
            }
        ],
        "response_format": {"type": "json_object"},
    }
    if reasoning_effort:
        request["reasoning"] = {"effort": reasoning_effort}

    response = client.chat.completions.create(**request)
    audit = parse_audit_json(response.choices[0].message.content)
    return remap_audit_coordinates(
        audit,
        source_size=audit_input.audit_size,
        target_size=audit_input.original_size,
    )
