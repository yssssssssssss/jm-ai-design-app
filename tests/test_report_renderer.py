from app.report_renderer import render_report_html


def _audit_payload():
    return {
        "screen_context": "首页",
        "overall_conclusion": "基本符合",
        "major_issues": ["中：按钮颜色偏差"],
        "passes": ["字号层级清晰"],
        "issues": [
            {
                "id": "color-01",
                "severity": "中",
                "category": "色彩",
                "location": "主按钮",
                "current_observation": "偏蓝",
                "spec_expectation": "应使用 #6B36FA",
                "recommendation": "改为 JM AI 主色",
                "confidence": 0.9,
                "bbox": [1, 2, 3, 4],
            }
        ],
        "checklist": [{"item": "AI 主色", "status": "不通过", "evidence": "偏蓝"}],
        "cannot_verify": [],
    }


def test_render_report_html_escapes_user_text_and_includes_image_sections():
    html = render_report_html(
        task={"title": "<script>alert(1)</script>", "summary": "部分图片存在问题"},
        image_results=[
            {
                "filename": "image-001.png",
                "audit": _audit_payload(),
                "artifacts": {
                    "annotated": "artifacts/image-001/annotated.png",
                    "tokens": "artifacts/image-001/tokens.json",
                },
            }
        ],
    )

    assert "<script>" not in html
    assert "JM AI 设计规范审核报告" in html
    assert "image-001.png" in html
    assert "审核综述" in html
    assert "AI 主色" in html
    assert "artifacts/image-001/annotated.png" in html
    assert "素材资料" in html
    assert "data:image/svg+xml" in html


def test_render_report_html_includes_declared_screen_size_when_present():
    html = render_report_html(
        task={
            "title": "审核",
            "summary": "完成",
            "screen_width_px": 1440,
            "screen_height_px": 900,
        },
        image_results=[],
    )

    assert "稿件基准尺寸：1440 × 900 px" in html


def test_render_report_html_builds_protected_artifact_urls_when_task_id_is_known():
    html = render_report_html(
        task={"title": "审核", "summary": "完成"},
        image_results=[
            {
                "filename": "image-001.png",
                "audit": _audit_payload(),
                "artifacts": {
                    "annotated": "uploads/42/artifacts/image-001/annotated.png",
                    "measurements": "uploads/42/artifacts/image-001/measurements.json",
                },
            }
        ],
        task_id=42,
    )

    assert "/artifacts/42/artifacts/image-001/annotated.png" in html
    assert "/artifacts/42/artifacts/image-001/measurements.json" in html


def test_render_report_html_handles_empty_results():
    html = render_report_html(
        task={"title": "空任务", "summary": ""},
        image_results=[
            {
                "filename": "image-001.png",
                "audit": {
                    "screen_context": "首页",
                    "overall_conclusion": "未发现明确问题",
                    "major_issues": [],
                    "passes": [],
                    "issues": [],
                    "checklist": [],
                    "cannot_verify": [],
                },
                "artifacts": {},
            }
        ],
    )

    assert "未发现明确问题" in html
    assert "本图没有可生成的标注截图" in html


def test_pending_section_is_collapsed_by_default():
    payload = _audit_payload()
    payload["cannot_verify"] = [{"item": "图标素材", "reason": "缺少原始资源"}]

    html = render_report_html(
        task={"title": "审核", "summary": "完成"},
        image_results=[
            {
                "filename": "image-001.png",
                "audit": payload,
                "artifacts": {},
            }
        ],
    )

    assert '<details class="pending-details">' in html
    assert "<summary>待确认</summary>" in html
    assert '<details class="pending-details" open>' not in html


def test_core_conclusion_shows_compliance_status_before_summary_analysis():
    html = render_report_html(
        task={"title": "审核", "summary": "完成"},
        image_results=[
            {
                "filename": "image-001.png",
                "audit": {
                    "screen_context": "订单页",
                    "overall_conclusion": "不符合 JM AI strict mode，主按钮颜色偏差明显",
                    "major_issues": ["中：主按钮颜色 off-token"],
                    "passes": [],
                    "issues": [
                        {
                            "id": "color-01",
                            "severity": "中",
                            "category": "色彩",
                            "location": "主按钮",
                            "current_observation": "绿色按钮",
                            "spec_expectation": "应使用 JM AI 紫色",
                            "recommendation": "改为 #6B36FA",
                            "confidence": 0.91,
                            "bbox": [1, 2, 3, 4],
                        }
                    ],
                    "checklist": [],
                    "cannot_verify": [],
                },
                "artifacts": {},
            }
        ],
    )

    core_html = html.split("核心结论", 1)[1].split("审核综述", 1)[0]
    assert "整体结论：不合规" in core_html
    assert "总结分析：不符合 JM AI strict mode，主按钮颜色偏差明显" in core_html
    assert core_html.index("整体结论：不合规") < core_html.index("总结分析：")


def test_report_replaces_major_issues_with_audit_overview():
    html = render_report_html(
        task={"title": "审核", "summary": "完成"},
        image_results=[
            {
                "filename": "image-001.png",
                "audit": _audit_payload(),
                "artifacts": {},
            }
        ],
    )

    assert "主要问题" not in html
    assert "研发/验收 Checklist" not in html
    assert "审核综述" in html
    assert html.index("审核综述") < html.index("问题截图")
    overview_html = html.split("审核综述", 1)[1].split("问题截图", 1)[0]
    assert "按钮颜色偏差" not in overview_html
    assert '<table class="checklist-table">' in overview_html
    assert "AI 主色" in overview_html


def test_report_includes_back_link_to_history_when_task_id_is_known():
    html = render_report_html(
        task={"title": "审核", "summary": "完成"},
        image_results=[],
        task_id=42,
    )

    assert '<a class="back-link" href="/tasks">返回</a>' in html
    assert "返回任务详情" not in html
    assert 'href="/tasks/42"' not in html


def test_render_report_html_matches_skill_report_structure():
    html = render_report_html(
        task={"title": "JoyHR 审核", "summary": "不符合 JM AI strict mode"},
        image_results=[
            {
                "filename": "image-001.png",
                "audit": {
                    "screen_context": "培训中心",
                    "overall_conclusion": "不符合 JM AI strict mode",
                    "major_issues": ["中：CTA 颜色 off-token"],
                    "passes": ["标题层级清晰"],
                    "issues": [
                        {
                            "id": "color-01",
                            "severity": "中",
                            "category": "色彩",
                            "location": "主 CTA",
                            "current_observation": "绿色按钮",
                            "spec_expectation": "应使用 JM AI 紫色",
                            "recommendation": "改为 #6B36FA",
                            "confidence": 0.91,
                            "bbox": [1, 2, 3, 4],
                        },
                        {
                            "id": "tag-01",
                            "severity": "中",
                            "category": "标签/按钮",
                            "location": "顶部功能胶囊",
                            "current_observation": "功能胶囊不符合 JM AI tag/button",
                            "spec_expectation": "应使用规范胶囊样式",
                            "recommendation": "改为 JM AI tag/button 样式",
                            "confidence": 0.88,
                            "bbox": [4, 5, 6, 7],
                        }
                    ],
                    "checklist": [
                        {"item": "字号层级", "status": "通过", "evidence": "清晰"},
                        {"item": "AI 主色", "status": "不通过", "evidence": "绿色 off-token"},
                        {"item": "字体族", "status": "无法确认", "evidence": "截图无法确认"},
                    ],
                    "cannot_verify": [{"item": "字体族", "reason": "截图无法确认"}],
                },
                "artifacts": {
                    "annotated": "artifacts/image-001/annotated.png",
                    "issue_crops": [
                        "artifacts/image-001/issue-color-01.png",
                        "artifacts/image-001/issue-tag-01.png",
                    ],
                },
            }
        ],
    )

    assert "核心结论" in html
    assert "整体结论：" in html
    assert "主要问题" not in html
    assert "研发/验收 Checklist" not in html
    assert "审核综述" in html
    assert "问题截图" in html
    assert "全图标注" in html
    assert "issue-color-01.png" in html
    assert "<figcaption>全图标注</figcaption><img" in html
    assert "编号 01｜修改建议：改为 #6B36FA" in html
    assert "编号 02｜修改建议：改为 JM AI tag/button 样式" in html
    assert html.index("全图标注") < html.index("issue-color-01.png")
    assert "<th>优先级</th>" not in html
    assert "<th>编号</th>" in html
    assert "<th>规范要求</th>" not in html
    assert "<th>素材资料</th>" in html
    assert '<span class="issue-number">01</span>' in html
    assert '<span class="issue-number">02</span>' in html
    assert "data:image/svg+xml" in html
    assert "material-preview" in html
    assert '<table class="issues-table">' in html
    assert ".issues-table th:nth-child(1), .issues-table td:nth-child(1) { width: 7%; }" in html
    assert ".issues-table th:nth-child(2), .issues-table td:nth-child(2) { width: 9%; }" in html
    assert ".issues-table th:nth-child(6), .issues-table td:nth-child(6) { width: 18%; }" in html
    assert "置信度" not in html
    assert "待确认" in html
    assert "无法确认项" not in html
    checklist_html = html.split("审核综述", 1)[1].split("问题截图", 1)[0]
    assert "无法确认" not in checklist_html
    assert "字体族" not in checklist_html
    assert "字号层级" not in html
    assert "字体族" not in html
    assert '<table class="checklist-table">' in html
    assert '<span class="status-fail">不通过</span>' in html
    assert ".checklist-table th:nth-child(2), .checklist-table td:nth-child(2) { width: 16%; }" in html
    assert ".screenshots { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }" in html
    assert ".screenshot-card:not(.wide) { aspect-ratio: 1 / 1;" in html
    assert "AI 主色" in html
