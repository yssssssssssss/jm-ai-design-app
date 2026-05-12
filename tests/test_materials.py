from app.materials import match_material, material_url


def test_match_material_prefers_button_spec_for_button_color_issue():
    material = match_material(
        {
            "category": "Color / AI Buttons",
            "location": "顶部主操作",
            "current_observation": "按钮使用绿色",
            "recommendation": "改为 ai/ai-normal #6B36FA 的主要按钮样式",
        }
    )

    assert material is not None
    assert material["id"] == "button.primary.filled"
    assert material_url(material) == "/materials/crops/button-primary-filled.png"


def test_match_material_uses_spacing_spec_for_gap_issue():
    material = match_material(
        {
            "category": "Spacing",
            "current_observation": "卡片之间 gap 为 18px",
            "recommendation": "间距应按 4px 栅格，优先使用 16px 或 20px",
        }
    )

    assert material is not None
    assert material["component"] == "spacing"


def test_match_material_uses_new_color_token_detail_materials():
    cases = [
        ("color.ai.main.solid", "使用主纯色 ai/ai-normal #6B36FA"),
        ("color.ai.light.solid", "使用 light 纯色 ai/ai-light-normal #F3F0FF"),
        ("color.ai.main.gradient", "使用主渐变色 Gradient/ai/ai-normal"),
        ("color.ai.light.gradient", "使用 light 渐变色 Gradient/ai/ai-light-normal"),
    ]

    for expected_id, recommendation in cases:
        material = match_material(
            {
                "category": "Color",
                "current_observation": "颜色不符合 JM AI token",
                "recommendation": recommendation,
            }
        )

        assert material is not None
        assert material["id"] == expected_id
        assert material_url(material).startswith("/materials/crops/color-ai-")


def test_match_material_returns_none_for_unknown_issue():
    material = match_material(
        {
            "category": "Unknown",
            "current_observation": "业务文案需要确认",
            "recommendation": "请产品确认",
        }
    )

    assert material is None
