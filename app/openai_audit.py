from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Protocol

from PIL import Image


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


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def build_audit_prompt(
    spec_text: str,
    declared_screen_size: tuple[int, int] | None = None,
    actual_image_size: tuple[int, int] | None = None,
) -> str:
    size_context = ""
    if actual_image_size or declared_screen_size:
        lines = ["\n\n尺寸上下文:"]
        if actual_image_size:
            lines.append(
                f"- 上传图片实际像素尺寸：{actual_image_size[0]}px × {actual_image_size[1]}px。"
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


def audit_image(
    client: _OpenAIClient,
    model: str,
    image_path: Path,
    spec_text: str,
    reasoning_effort: str | None = None,
    declared_screen_size: tuple[int, int] | None = None,
) -> dict[str, Any]:
    actual_image_size = _image_size(image_path)
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
                            actual_image_size=actual_image_size,
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": image_data_url(image_path),
                        "detail": "high",
                    },
                ],
            }
        ],
        "text": {"format": audit_json_schema()},
    }
    if reasoning_effort:
        request["reasoning"] = {"effort": reasoning_effort}

    response = client.responses.create(**request)
    return parse_audit_json(response.output_text)


def audit_image_with_chat(
    client: _OpenAIClient,
    model: str,
    image_path: Path,
    spec_text: str,
    reasoning_effort: str | None = None,
    declared_screen_size: tuple[int, int] | None = None,
) -> dict[str, Any]:
    actual_image_size = _image_size(image_path)
    prompt = (
        build_audit_prompt(
            spec_text,
            declared_screen_size=declared_screen_size,
            actual_image_size=actual_image_size,
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
                    {"type": "image_url", "image_url": {"url": image_data_url(image_path)}},
                ],
            }
        ],
        "response_format": {"type": "json_object"},
    }
    if reasoning_effort:
        request["reasoning"] = {"effort": reasoning_effort}

    response = client.chat.completions.create(**request)
    return parse_audit_json(response.choices[0].message.content)
