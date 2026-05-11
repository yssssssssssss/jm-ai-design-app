import json

from PIL import Image

from app.openai_audit import (
    AuditModelError,
    audit_image_with_chat,
    audit_image,
    audit_json_schema,
    build_audit_prompt,
    image_data_url,
    parse_audit_json,
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
