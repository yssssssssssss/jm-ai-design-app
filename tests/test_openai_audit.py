import json

from PIL import Image

from app.openai_audit import (
    AuditModelError,
    audit_image_with_chat,
    audit_image,
    audit_json_schema,
    build_audit_prompt,
    compact_audit_spec,
    image_data_url,
    parse_audit_json,
    prepare_audit_image,
    remap_audit_coordinates,
)


def _valid_payload():
    return {
        "screen_context": "首页",
        "overall_conclusion": "整体基本符合",
        "major_issues": [],
        "passes": [],
        "issues": [],
        "sample_points": [],
        "regions": [],
        "distances": [],
        "checklist": [],
        "cannot_verify": [],
    }


def test_build_audit_prompt_includes_spec_rules():
    prompt = build_audit_prompt("SPEC TEXT")

    assert "JM AI" in prompt
    assert "SPEC TEXT" in prompt
    assert "JSON" in prompt
    assert "bbox" in prompt
    assert "暂时不要审核字体相关问题" in prompt


def test_build_audit_prompt_includes_declared_screen_size_context():
    prompt = build_audit_prompt(
        "SPEC TEXT",
        declared_screen_size=(1440, 900),
        actual_image_size=(2880, 1800),
    )

    assert "尺寸上下文" in prompt
    assert "上传图片实际像素尺寸：2880px × 1800px" in prompt
    assert "用户声明的稿件基准尺寸：1440px × 900px" in prompt
    assert "间距、组件大小、字号比例、布局密度" in prompt


def test_build_audit_prompt_includes_compressed_image_coordinate_context():
    prompt = build_audit_prompt(
        "SPEC TEXT",
        actual_image_size=(3200, 1800),
        audit_image_size=(1600, 900),
    )

    assert "上传图片实际像素尺寸：3200px × 1800px" in prompt
    assert "模型当前看到的压缩审核图尺寸：1600px × 900px" in prompt
    assert "必须使用当前可见审核图坐标" in prompt


def test_compact_audit_spec_removes_typography_section():
    spec = """# Spec

## Audit Categories

- Color and gradients
- Typography
- Spacing

## Color

Use purple.

## Typography

### Font Family

Use system fonts.

## Spacing

Use scale.

## AI Buttons

Use allowed families.
"""

    compact = compact_audit_spec(spec)

    assert "## Color" in compact
    assert "## Spacing" in compact
    assert "## AI Buttons" in compact
    assert "Typography" not in compact
    assert "Font Family" not in compact


def test_parse_audit_json_accepts_minimal_valid_payload():
    result = parse_audit_json(json.dumps(_valid_payload(), ensure_ascii=False))

    assert result["screen_context"] == "首页"
    assert result["issues"] == []


def test_parse_audit_json_rejects_missing_required_key():
    try:
        parse_audit_json('{"screen_context":"x"}')
    except AuditModelError as exc:
        assert "overall_conclusion" in str(exc)
    else:
        raise AssertionError("missing keys should fail")


def test_parse_audit_json_rejects_non_object_payload():
    try:
        parse_audit_json("[]")
    except AuditModelError as exc:
        assert "对象" in str(exc)
    else:
        raise AssertionError("non-object JSON should fail")


def test_image_data_url_uses_media_type_and_base64(tmp_path):
    path = tmp_path / "screen.jpg"
    Image.new("RGB", (2, 2), color=(107, 54, 250)).save(path)

    url = image_data_url(path)

    assert url.startswith("data:image/jpeg;base64,")
    assert len(url.split(",", 1)[1]) > 0


def test_prepare_audit_image_downsamples_large_image(tmp_path):
    image_path = tmp_path / "large.png"
    Image.effect_noise((600, 300), 80).convert("RGB").save(image_path)

    prepared = prepare_audit_image(image_path, max_side=120)

    assert prepared.original_size == (600, 300)
    assert prepared.audit_size == (120, 60)
    assert prepared.data_url.startswith("data:image/jpeg;base64,")


def test_remap_audit_coordinates_scales_model_coordinates_to_original():
    audit = _valid_payload()
    audit["issues"] = [
        {
            "id": "i1",
            "category": "spacing",
            "severity": "中",
            "location": "card",
            "current_observation": "gap",
            "spec_expectation": "scale",
            "recommendation": "fix",
            "confidence": 0.8,
            "bbox": [5, 3, 10, 4],
        }
    ]
    audit["sample_points"] = [{"label": "center", "x": 12, "y": 7}]
    audit["regions"] = [
        {
            "id": "r1",
            "title": "card",
            "bbox": [2, 1, 8, 3],
            "role_hint": "component",
            "measure_kind": "component",
        }
    ]

    mapped = remap_audit_coordinates(audit, source_size=(50, 25), target_size=(100, 50))

    assert mapped["issues"][0]["bbox"] == [10, 6, 20, 8]
    assert mapped["sample_points"][0] == {"label": "center", "x": 24, "y": 14}
    assert mapped["regions"][0]["bbox"] == [4, 2, 16, 6]
    assert audit["issues"][0]["bbox"] == [5, 3, 10, 4]


def test_audit_json_schema_requires_core_fields():
    schema = audit_json_schema()

    assert schema["type"] == "json_schema"
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert set(_valid_payload()).issubset(set(schema["schema"]["required"]))


def test_audit_json_schema_has_strict_nested_objects():
    schema = audit_json_schema()["schema"]["properties"]

    for key in ["regions", "distances", "checklist", "cannot_verify"]:
        item_schema = schema[key]["items"]
        assert item_schema["type"] == "object"
        assert item_schema["additionalProperties"] is False
        assert item_schema["required"] == list(item_schema["properties"])


def test_audit_image_calls_responses_api_with_schema_and_data_url(tmp_path):
    image_path = tmp_path / "screen.png"
    Image.new("RGB", (2, 2), color=(107, 54, 250)).save(image_path)
    payload = _valid_payload()

    class FakeResponses:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs

            class Response:
                output_text = json.dumps(payload, ensure_ascii=False)

            return Response()

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    client = FakeClient()

    result = audit_image(client, "test-model", image_path, "SPEC")

    assert result == payload
    assert client.responses.kwargs["model"] == "test-model"
    content = client.responses.kwargs["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert "SPEC" in content[0]["text"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert content[1]["detail"] == "high"
    assert client.responses.kwargs["text"]["format"]["type"] == "json_schema"
    assert "reasoning" not in client.responses.kwargs


def test_audit_image_passes_reasoning_effort_when_configured(tmp_path):
    image_path = tmp_path / "screen.png"
    Image.new("RGB", (2, 2), color=(107, 54, 250)).save(image_path)
    payload = _valid_payload()

    class FakeResponses:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs

            class Response:
                output_text = json.dumps(payload, ensure_ascii=False)

            return Response()

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    client = FakeClient()

    audit_image(client, "test-model", image_path, "SPEC", reasoning_effort="xhigh")

    assert client.responses.kwargs["reasoning"] == {"effort": "xhigh"}


def test_audit_image_passes_declared_and_actual_size_to_prompt(tmp_path):
    image_path = tmp_path / "screen.png"
    Image.new("RGB", (32, 18), color=(107, 54, 250)).save(image_path)
    payload = _valid_payload()

    class FakeResponses:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs

            class Response:
                output_text = json.dumps(payload, ensure_ascii=False)

            return Response()

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    client = FakeClient()

    audit_image(
        client,
        "test-model",
        image_path,
        "SPEC",
        declared_screen_size=(1440, 900),
    )

    prompt = client.responses.kwargs["input"][0]["content"][0]["text"]
    assert "上传图片实际像素尺寸：32px × 18px" in prompt
    assert "用户声明的稿件基准尺寸：1440px × 900px" in prompt


def test_audit_image_downsamples_and_remaps_coordinates(tmp_path):
    image_path = tmp_path / "screen.png"
    Image.new("RGB", (100, 50), color=(107, 54, 250)).save(image_path)
    payload = _valid_payload()
    payload["issues"] = [
        {
            "id": "i1",
            "category": "spacing",
            "severity": "中",
            "location": "card",
            "current_observation": "gap",
            "spec_expectation": "scale",
            "recommendation": "fix",
            "confidence": 0.8,
            "bbox": [5, 3, 10, 4],
        }
    ]
    payload["sample_points"] = [{"label": "center", "x": 12, "y": 7}]
    payload["regions"] = [
        {
            "id": "r1",
            "title": "card",
            "bbox": [2, 1, 8, 3],
            "role_hint": "component",
            "measure_kind": "component",
        }
    ]

    class FakeResponses:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs

            class Response:
                output_text = json.dumps(payload, ensure_ascii=False)

            return Response()

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    client = FakeClient()

    result = audit_image(
        client,
        "test-model",
        image_path,
        "SPEC",
        max_image_side=50,
        image_detail="low",
    )

    prompt = client.responses.kwargs["input"][0]["content"][0]["text"]
    image_content = client.responses.kwargs["input"][0]["content"][1]

    assert "模型当前看到的压缩审核图尺寸：50px × 25px" in prompt
    assert image_content["image_url"].startswith("data:image/jpeg;base64,")
    assert image_content["detail"] == "low"
    assert result["issues"][0]["bbox"] == [10, 6, 20, 8]
    assert result["sample_points"][0] == {"label": "center", "x": 24, "y": 14}
    assert result["regions"][0]["bbox"] == [4, 2, 16, 6]


def test_audit_image_with_chat_calls_chat_completions_with_image(tmp_path):
    image_path = tmp_path / "screen.png"
    Image.new("RGB", (2, 2), color=(107, 54, 250)).save(image_path)
    payload = _valid_payload()

    class FakeCompletions:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs

            class Message:
                content = json.dumps(payload, ensure_ascii=False)

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    client = FakeClient()

    result = audit_image_with_chat(client, "jd-model", image_path, "SPEC")

    assert result == payload
    kwargs = client.chat.completions.kwargs
    assert kwargs["model"] == "jd-model"
    assert kwargs["response_format"] == {"type": "json_object"}
    content = kwargs["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert "SPEC" in content[0]["text"]
    assert "必须只输出一个 JSON 对象" in content[0]["text"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
