from __future__ import annotations

import re
from html import escape
from typing import Any
from urllib.parse import quote

from app.evidence_tools import filter_font_related_audit


def _text(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _list(items: list[Any], empty: str = "无") -> str:
    if not items:
        return f'<p class="meta">{_text(empty)}</p>'
    return "<ul>" + "".join(f"<li>{_text(item)}</li>" for item in items) + "</ul>"


def _category_slug(category: Any) -> str:
    value = str(category or "").strip().lower()
    if any(token in value for token in ["色", "color", "colour"]):
        return "color"
    if any(token in value for token in ["标签", "胶囊", "按钮", "button", "tag"]):
        return "tag"
    if any(token in value for token in ["品牌", "视觉", "icon", "图标", "brand"]):
        return "brand"
    if any(token in value for token in ["间距", "留白", "spacing", "padding", "gap"]):
        return "spacing"
    if any(token in value for token in ["字体", "字号", "文本", "typography", "font", "text"]):
        return "type"
    return "issue"


def _issue_label(issue: dict[str, Any], fallback_index: int) -> str:
    issue_id = str(issue.get("id") or "").strip()
    if not issue_id:
        issue_id = f"{_category_slug(issue.get('category'))}-{fallback_index:02d}"

    summary = (
        issue.get("title")
        or issue.get("current_observation")
        or issue.get("recommendation")
        or issue.get("location")
        or "问题细节"
    )
    return f"{issue_id}：{summary}"


def _issues_by_id(issues: list[dict[str, Any]]) -> dict[str, tuple[int, dict[str, Any]]]:
    indexed: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, issue in enumerate(issues, start=1):
        issue_id = str(issue.get("id") or "").strip()
        if issue_id:
            indexed[issue_id] = (index, issue)
    return indexed


def _issue_numbers(issues: list[dict[str, Any]]) -> dict[str, str]:
    numbers: dict[str, str] = {}
    for index, issue in enumerate(issues, start=1):
        issue_id = str(issue.get("id") or "").strip()
        if issue_id:
            numbers[issue_id] = _issue_number(index)
    return numbers


def _issue_number(index: int) -> str:
    return f"{index:02d}"


def _crop_issue_id(path: str) -> str | None:
    filename = path.rsplit("/", 1)[-1]
    if not filename.startswith("issue-") or "." not in filename:
        return None
    return filename[len("issue-") :].rsplit(".", 1)[0] or None


def _svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;charset=utf-8," + quote(svg)


def _issue_text(issue: dict[str, Any]) -> str:
    return " ".join(
        str(issue.get(key) or "")
        for key in [
            "category",
            "location",
            "current_observation",
            "spec_expectation",
            "recommendation",
        ]
    ).lower()


def _hex_color_from_issue(issue: dict[str, Any]) -> str:
    text = _issue_text(issue)
    match = re.search(r"#[0-9a-fA-F]{6}\b", text)
    return match.group(0).upper() if match else "#6B36FA"


def _material_svg(issue: dict[str, Any]) -> tuple[str, str]:
    text = _issue_text(issue)
    color = _hex_color_from_issue(issue)
    if any(token in text for token in ["按钮", "button"]):
        title = "AI 按钮样式"
        body = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="220" height="96" viewBox="0 0 220 96">
          <rect width="220" height="96" rx="10" fill="#F8F7FF"/>
          <rect x="34" y="31" width="152" height="34" rx="8" fill="{color}"/>
          <text x="110" y="53" fill="#FFFFFF" font-size="14" font-family="Arial, sans-serif" text-anchor="middle" font-weight="700">AI 按钮</text>
          <text x="110" y="84" fill="#6B36FA" font-size="11" font-family="Arial, sans-serif" text-anchor="middle">{color}</text>
        </svg>
        """
    elif any(token in text for token in ["标签", "胶囊", "tag", "pill"]):
        title = "AI 标签样式"
        body = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="220" height="96" viewBox="0 0 220 96">
          <rect width="220" height="96" rx="10" fill="#F8F7FF"/>
          <rect x="50" y="31" width="120" height="32" rx="16" fill="#F3F0FF" stroke="{color}" stroke-width="1.5"/>
          <circle cx="70" cy="47" r="5" fill="{color}"/>
          <text x="116" y="52" fill="{color}" font-size="13" font-family="Arial, sans-serif" text-anchor="middle" font-weight="700">AI 标签</text>
          <text x="110" y="84" fill="#6B36FA" font-size="11" font-family="Arial, sans-serif" text-anchor="middle">{color}</text>
        </svg>
        """
    elif any(token in text for token in ["间距", "留白", "spacing", "padding", "gap"]):
        title = "间距规范示意"
        body = """
        <svg xmlns="http://www.w3.org/2000/svg" width="220" height="96" viewBox="0 0 220 96">
          <rect width="220" height="96" rx="10" fill="#F8F7FF"/>
          <rect x="34" y="25" width="44" height="40" rx="8" fill="#EDEEFF" stroke="#6B36FA"/>
          <rect x="142" y="25" width="44" height="40" rx="8" fill="#EDEEFF" stroke="#6B36FA"/>
          <line x1="84" y1="45" x2="136" y2="45" stroke="#6B36FA" stroke-width="2"/>
          <path d="M84 40v10M136 40v10" stroke="#6B36FA" stroke-width="2"/>
          <text x="110" y="38" fill="#6B36FA" font-size="12" font-family="Arial, sans-serif" text-anchor="middle" font-weight="700">8 / 12 / 16 / 24 px</text>
          <text x="110" y="84" fill="#6B7280" font-size="11" font-family="Arial, sans-serif" text-anchor="middle">间距按 4px 栅格对齐</text>
        </svg>
        """
    else:
        title = "JM AI 色彩素材"
        body = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="220" height="96" viewBox="0 0 220 96">
          <rect width="220" height="96" rx="10" fill="#F8F7FF"/>
          <rect x="24" y="24" width="48" height="48" rx="8" fill="{color}"/>
          <rect x="86" y="24" width="48" height="48" rx="8" fill="#8F55FD"/>
          <rect x="148" y="24" width="48" height="48" rx="8" fill="#F3F0FF" stroke="#EBE5FA"/>
          <text x="48" y="84" fill="#374151" font-size="10" font-family="Arial, sans-serif" text-anchor="middle">{color}</text>
          <text x="110" y="84" fill="#374151" font-size="10" font-family="Arial, sans-serif" text-anchor="middle">#8F55FD</text>
          <text x="172" y="84" fill="#374151" font-size="10" font-family="Arial, sans-serif" text-anchor="middle">#F3F0FF</text>
        </svg>
        """
    return title, " ".join(body.split())


def _material_image(issue: dict[str, Any]) -> str:
    title, svg = _material_svg(issue)
    return (
        f'<img class="material-preview" src="{_text(_svg_data_uri(svg))}" '
        f'alt="{_text(title)}">'
    )


def _issues_table(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return '<p class="meta">未发现明确问题。</p>'
    rows = []
    for index, issue in enumerate(issues, start=1):
        rows.append(
            "<tr>"
            f"<td><span class=\"issue-number\">{_text(_issue_number(index))}</span></td>"
            f"<td>{_text(issue.get('category'))}</td>"
            f"<td>{_text(issue.get('location'))}</td>"
            f"<td>{_text(issue.get('current_observation'))}</td>"
            f"<td>{_text(issue.get('recommendation'))}</td>"
            f"<td>{_material_image(issue)}</td>"
            "</tr>"
        )
    return (
        '<table class="issues-table"><thead><tr>'
        "<th>编号</th><th>分类</th><th>位置</th><th>当前表现</th>"
        "<th>修改建议</th><th>素材资料</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _checklist_table(items: list[dict[str, Any]]) -> str:
    visible = [item for item in items if item.get("status") in {"通过", "不通过"}]
    visible.sort(key=lambda item: 0 if item.get("status") == "通过" else 1)
    return _kv_table(
        visible,
        [("item", "检查项"), ("status", "状态"), ("evidence", "说明")],
        table_class="checklist-table",
        cell_renderer=_checklist_cell,
    )


def _checklist_cell(key: str, value: Any) -> str:
    if key != "status":
        return _text(value)
    status = str(value or "")
    if status == "通过":
        return '<span class="status-pass">通过</span>'
    if status == "不通过":
        return '<span class="status-fail">不通过</span>'
    return _text(value)


def _collapsible_pending(items: list[dict[str, Any]]) -> str:
    return (
        '<details class="pending-details">'
        '<summary>待确认</summary>'
        f'{_kv_table(items, [("item", "项目"), ("reason", "原因")])}'
        '</details>'
    )


def _kv_table(
    items: list[dict[str, Any]],
    columns: list[tuple[str, str]],
    table_class: str | None = None,
    cell_renderer: Any | None = None,
) -> str:
    if not items:
        return '<p class="meta">无</p>'
    header = "".join(f"<th>{_text(label)}</th>" for _, label in columns)
    rows = []
    for item in items:
        cells = "".join(
            f"<td>{cell_renderer(key, item.get(key)) if cell_renderer else _text(item.get(key))}</td>"
            for key, _ in columns
        )
        rows.append(f"<tr>{cells}</tr>")
    class_attr = f' class="{_text(table_class)}"' if table_class else ""
    return f"<table{class_attr}><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _artifact_url(path: str | None, task_id: int | None) -> str | None:
    if not path:
        return None
    if path.startswith("/"):
        return path
    if task_id is None:
        return path

    prefix = f"uploads/{task_id}/"
    normalized = path[len(prefix) :] if path.startswith(prefix) else path
    return f"/artifacts/{task_id}/{normalized}"


def _artifact_link(label: str, path: str | None, task_id: int | None) -> str:
    url = _artifact_url(path, task_id)
    if not url:
        return ""
    return f'<a href="{_text(url)}">{_text(label)}</a>'


def _compliance_status(audit: dict[str, Any]) -> str:
    conclusion = str(audit.get("overall_conclusion") or "")
    if "不符合" in conclusion or "不合规" in conclusion or audit.get("issues"):
        return "不合规"
    return "合规"


def _core_conclusion(audit: dict[str, Any]) -> str:
    summary = audit.get("overall_conclusion") or audit.get("summary") or "审核完成"
    return f"""
      <section class="core-conclusion">
        <strong>整体结论：{_text(_compliance_status(audit))}</strong>
        <p>总结分析：{_text(summary)}</p>
      </section>
    """


def _screenshots(
    artifacts: dict[str, Any],
    issues: list[dict[str, Any]],
    task_id: int | None,
) -> str:
    figures: list[str] = []
    annotated = _artifact_url(artifacts.get("annotated"), task_id)
    if annotated:
        figures.append(
            '<figure class="screenshot-card wide">'
            "<figcaption>全图标注</figcaption>"
            f'<img src="{_text(annotated)}" alt="全图标注">'
            "</figure>"
        )

    indexed_issues = _issues_by_id(issues)
    issue_numbers = _issue_numbers(issues)
    for index, crop in enumerate(artifacts.get("issue_crops") or [], start=1):
        url = _artifact_url(crop, task_id)
        if not url:
            continue
        issue_id = _crop_issue_id(str(crop))
        issue = indexed_issues.get(issue_id, (index, {}))[1]
        issue_index = indexed_issues.get(issue_id, (index, {}))[0]
        issue_number = (
            issue_numbers.get(issue_id)
            if issue_id
            else _issue_number(issue_index)
        )
        caption = (
            f"编号 {issue_number}｜修改建议：{issue.get('recommendation') or issue.get('current_observation')}"
            if issue
            else f"编号 {_issue_number(index)}｜修改建议：问题细节 {index}"
        )
        figures.append(
            '<figure class="screenshot-card">'
            f"<figcaption>{_text(caption)}</figcaption>"
            f'<img src="{_text(url)}" alt="{_text(caption)}">'
            "</figure>"
        )

    if not figures:
        return '<p class="meta">本图没有可生成的标注截图。</p>'
    return "".join(figures)


def _image_section(index: int, result: dict[str, Any], task_id: int | None) -> str:
    audit = filter_font_related_audit(result.get("audit", {}))
    artifacts = result.get("artifacts", {})
    evidence_links = [
        _artifact_link("颜色证据", artifacts.get("tokens"), task_id),
        _artifact_link("测量证据", artifacts.get("measurements"), task_id),
        _artifact_link("问题 JSON", artifacts.get("issues"), task_id),
        _artifact_link("模型 JSON", artifacts.get("audit_json"), task_id),
    ]
    evidence_html = " ".join(link for link in evidence_links if link)
    if not evidence_html:
        evidence_html = '<span class="meta">无</span>'

    return f"""
    <section class="card">
      <h2>{index}. {_text(result.get("filename"))}</h2>
      <p class="meta">页面识别：{_text(audit.get("screen_context"))}</p>

      <h3>核心结论</h3>
      {_core_conclusion(audit)}

      <h3>审核综述</h3>
      {_checklist_table(audit.get("checklist", []))}

      <h3>问题截图</h3>
      <div class="screenshots">{_screenshots(artifacts, audit.get("issues", []), task_id)}</div>

      <h3>详细问题清单</h3>
      {_issues_table(audit.get("issues", []))}

      <h3>符合规范的点</h3>
      {_list(audit.get("passes", []))}

      {_collapsible_pending(audit.get("cannot_verify", []))}

      <h3>测量证据</h3>
      <p>{evidence_html}</p>
    </section>
    """


def _back_link(task_id: int | None) -> str:
    if task_id is None:
        return ""
    return '<a class="back-link" href="/tasks">返回</a>'


def _declared_screen_size(task: dict[str, Any]) -> str:
    width = task.get("screen_width_px")
    height = task.get("screen_height_px")
    if not width or not height:
        return ""
    return f'<p>稿件基准尺寸：{_text(width)} × {_text(height)} px</p>'


def render_report_html(
    task: dict[str, Any],
    image_results: list[dict[str, Any]],
    task_id: int | None = None,
) -> str:
    sections = "".join(
        _image_section(index, result, task_id)
        for index, result in enumerate(image_results, start=1)
    )
    if not sections:
        sections = '<section class="card"><p class="meta">暂无图片审核结果。</p></section>'

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JM AI 设计规范审核报告</title>
  <style>
    :root {{
      color-scheme: light;
      --ai: #6B36FA;
      --ai-soft: #F3F0FF;
      --text: #1f1f24;
      --muted: #767680;
      --line: #e7e7eb;
      --bg: #f7f7f9;
      --card: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 24px 56px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 40px; font-weight: 600; }}
    h2 {{ margin: 0 0 12px; font-size: 20px; line-height: 30px; font-weight: 600; }}
    h3 {{ margin: 24px 0 8px; font-size: 16px; line-height: 24px; font-weight: 600; }}
    p {{ margin: 0 0 10px; }}
    a {{ color: var(--ai); }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; background: var(--card); border: 1px solid var(--line); }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: #fafafa; font-weight: 600; }}
    .summary, .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin-top: 16px; }}
    .core-conclusion {{ background: var(--ai-soft); border-radius: 8px; color: var(--text); padding: 12px 14px; }}
    .core-conclusion strong {{ color: var(--ai); display: inline-block; font-size: 16px; margin-bottom: 6px; }}
    .meta {{ color: var(--muted); }}
    .report-header {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }}
    .back-link {{ flex: 0 0 auto; display: inline-flex; align-items: center; min-height: 32px; padding: 0 10px; border: 1px solid var(--line); border-radius: 6px; background: var(--card); text-decoration: none; font-weight: 600; }}
    .badge {{ display: inline-flex; align-items: center; min-height: 22px; padding: 0 8px; border-radius: 6px; background: var(--ai-soft); color: var(--ai); font-weight: 600; }}
    .issues-table th:nth-child(1), .issues-table td:nth-child(1) {{ width: 7%; }}
    .issues-table th:nth-child(2), .issues-table td:nth-child(2) {{ width: 9%; }}
    .issues-table th:nth-child(3), .issues-table td:nth-child(3) {{ width: 16%; }}
    .issues-table th:nth-child(4), .issues-table td:nth-child(4) {{ width: 23%; }}
    .issues-table th:nth-child(5), .issues-table td:nth-child(5) {{ width: 27%; }}
    .issues-table th:nth-child(6), .issues-table td:nth-child(6) {{ width: 18%; }}
    .issue-number {{ display: inline-flex; align-items: center; justify-content: center; min-width: 30px; min-height: 24px; border-radius: 6px; background: var(--ai-soft); color: var(--ai); font-weight: 700; }}
    .material-preview {{ display: block; width: 100%; max-width: 220px; height: auto; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    .pending-details {{ margin-top: 24px; border: 1px solid var(--line); border-radius: 8px; background: var(--card); }}
    .pending-details summary {{ cursor: pointer; padding: 10px 12px; color: var(--text); font-weight: 600; }}
    .pending-details table, .pending-details .meta {{ margin: 0; border-left: 0; border-right: 0; border-bottom: 0; }}
    .checklist-table th:nth-child(1), .checklist-table td:nth-child(1) {{ width: 30%; }}
    .checklist-table th:nth-child(2), .checklist-table td:nth-child(2) {{ width: 16%; }}
    .checklist-table th:nth-child(3), .checklist-table td:nth-child(3) {{ width: 54%; }}
    .status-pass {{ color: #0F8A4C; font-weight: 700; }}
    .status-fail {{ color: #D92D20; font-weight: 700; }}
    .screenshots {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }}
    .screenshot-card {{ margin: 0; background: var(--card); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    .screenshot-card.wide {{ grid-column: 1 / -1; }}
    .screenshot-card:not(.wide) {{ aspect-ratio: 1 / 1; display: flex; flex-direction: column; }}
    .screenshot-card img {{ display: block; width: 100%; height: auto; }}
    .screenshot-card:not(.wide) img {{ flex: 1 1 auto; min-height: 0; object-fit: contain; background: #fbfbfc; }}
    figcaption {{ min-height: 52px; padding: 10px 12px; color: #6f6f7a; font-weight: 600; overflow-wrap: anywhere; }}
    @media (max-width: 860px) {{
      .screenshots {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 560px) {{
      main {{ padding: 20px 12px 40px; }}
      .report-header {{ display: block; }}
      .back-link {{ margin-top: 10px; }}
      .screenshots {{ grid-template-columns: 1fr; }}
      th, td {{ padding: 8px; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="report-header">
      <h1>JM AI 设计规范审核报告</h1>
      {_back_link(task_id)}
    </div>
    <section class="summary">
      <span class="badge">{_text(task.get("summary") or "审核结果")}</span>
      <p>任务：{_text(task.get("title"))}</p>
      {_declared_screen_size(task)}
    </section>
    {sections}
  </main>
</body>
</html>"""
