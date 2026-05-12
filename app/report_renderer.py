from __future__ import annotations

from html import escape
from typing import Any

from app.evidence_tools import filter_font_related_audit
from app.materials import match_material, material_url


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


def _image_attrs(web_url: str, alt: str, file_url: str | None = None) -> str:
    attrs = f'src="{_text(web_url)}" alt="{_text(alt)}"'
    if file_url and file_url != web_url:
        attrs += (
            f' data-file-src="{_text(file_url)}"'
            ' onerror="this.onerror=null;this.src=this.dataset.fileSrc;"'
        )
    return attrs


def _material_file_url(material: dict[str, Any], task_id: int | None) -> str | None:
    if task_id is None:
        return None
    crop_path = str(material.get("crop_path") or "").strip()
    if not crop_path or crop_path.startswith("/") or ".." in crop_path.split("/"):
        return None
    return f"../../../assets/spec-materials/{crop_path}"


def _material_image(issue: dict[str, Any], task_id: int | None) -> str:
    material = match_material(issue)
    if not material:
        return '<span class="material-empty">暂无匹配规范素材</span>'
    url = material_url(material)
    if not url:
        return '<span class="material-empty">暂无匹配规范素材</span>'
    title = material.get("title") or "规范素材"
    attrs = _image_attrs(url, str(title), _material_file_url(material, task_id))
    return (
        f'<img class="material-preview" {attrs} data-material-viewer="true" '
        'role="button" tabindex="0" aria-label="放大查看参考素材">'
    )


def _issues_table(issues: list[dict[str, Any]], task_id: int | None) -> str:
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
            f"<td>{_material_image(issue, task_id)}</td>"
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


def _artifact_file_url(path: str | None, task_id: int | None) -> str | None:
    if not path or task_id is None:
        return None
    prefix = f"uploads/{task_id}/"
    if path.startswith(prefix):
        return path[len(prefix) :]

    web_prefix = f"/artifacts/{task_id}/"
    if path.startswith(web_prefix):
        return path[len(web_prefix) :]

    if path.startswith("/"):
        return None
    return path


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
        annotated_file = _artifact_file_url(artifacts.get("annotated"), task_id)
        figures.append(
            '<figure class="screenshot-card wide">'
            "<figcaption>全图标注</figcaption>"
            f'<img {_image_attrs(annotated, "全图标注", annotated_file)}>'
            "</figure>"
        )

    indexed_issues = _issues_by_id(issues)
    issue_numbers = _issue_numbers(issues)
    for index, crop in enumerate(artifacts.get("issue_crops") or [], start=1):
        url = _artifact_url(crop, task_id)
        if not url:
            continue
        file_url = _artifact_file_url(str(crop), task_id)
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
            f'<img {_image_attrs(url, caption, file_url)}>'
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
      {_issues_table(audit.get("issues", []), task_id)}

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


def _material_viewer() -> str:
    return """
    <div class="material-viewer" data-material-viewer-modal hidden aria-hidden="true">
      <button class="material-viewer-close" type="button" aria-label="关闭参考素材预览">关闭</button>
      <div class="material-viewer-stage" data-material-viewer-stage>
        <img class="material-viewer-image" alt="参考素材预览" draggable="false">
      </div>
      <p class="material-viewer-hint">滚轮或双指触控板缩放，拖动查看不同位置，Esc 关闭</p>
    </div>
    """


def _material_viewer_script() -> str:
    return """
  <script>
    (() => {
      const viewer = document.querySelector("[data-material-viewer-modal]");
      if (!viewer) return;

      const stage = viewer.querySelector("[data-material-viewer-stage]");
      const image = viewer.querySelector(".material-viewer-image");
      const closeButton = viewer.querySelector(".material-viewer-close");
      let scale = 1;
      let translateX = 0;
      let translateY = 0;
      let dragStartX = 0;
      let dragStartY = 0;
      let startTranslateX = 0;
      let startTranslateY = 0;
      let activePointerId = null;
      let previousBodyOverflow = "";

      const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

      const render = () => {
        image.style.transform = `translate3d(${translateX}px, ${translateY}px, 0) scale(${scale})`;
      };

      const resetView = () => {
        scale = 1;
        translateX = 0;
        translateY = 0;
        render();
      };

      const openViewer = (trigger) => {
        image.src = trigger.currentSrc || trigger.src;
        image.alt = trigger.alt || "参考素材预览";
        resetView();
        previousBodyOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        viewer.hidden = false;
        viewer.setAttribute("aria-hidden", "false");
        closeButton.focus({ preventScroll: true });
      };

      const closeViewer = () => {
        if (viewer.hidden) return;
        viewer.hidden = true;
        viewer.setAttribute("aria-hidden", "true");
        document.body.style.overflow = previousBodyOverflow;
        activePointerId = null;
        stage.classList.remove("is-dragging");
        image.removeAttribute("src");
      };

      document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) return;
        const trigger = event.target.closest("img.material-preview[data-material-viewer]");
        if (!trigger) return;
        event.preventDefault();
        openViewer(trigger);
      });

      document.addEventListener("keydown", (event) => {
        if (!(event.target instanceof Element)) return;
        const trigger = event.target.closest("img.material-preview[data-material-viewer]");
        if (trigger && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          openViewer(trigger);
          return;
        }
        if (event.key === "Escape") {
          closeViewer();
        }
      });

      closeButton.addEventListener("click", closeViewer);

      stage.addEventListener("wheel", (event) => {
        if (viewer.hidden) return;
        event.preventDefault();
        const nextScale = clamp(scale * Math.exp(-event.deltaY * 0.001), 0.5, 8);
        if (nextScale === scale) return;

        const rect = stage.getBoundingClientRect();
        const focusX = event.clientX - rect.left - rect.width / 2 - translateX;
        const focusY = event.clientY - rect.top - rect.height / 2 - translateY;
        const ratio = nextScale / scale;
        translateX -= focusX * (ratio - 1);
        translateY -= focusY * (ratio - 1);
        scale = nextScale;
        render();
      }, { passive: false });

      stage.addEventListener("pointerdown", (event) => {
        if (event.pointerType === "mouse" && event.button !== 0) return;
        activePointerId = event.pointerId;
        dragStartX = event.clientX;
        dragStartY = event.clientY;
        startTranslateX = translateX;
        startTranslateY = translateY;
        stage.classList.add("is-dragging");
        stage.setPointerCapture(event.pointerId);
      });

      stage.addEventListener("pointermove", (event) => {
        if (event.pointerId !== activePointerId) return;
        translateX = startTranslateX + event.clientX - dragStartX;
        translateY = startTranslateY + event.clientY - dragStartY;
        render();
      });

      const stopDragging = (event) => {
        if (event.pointerId !== activePointerId) return;
        activePointerId = null;
        stage.classList.remove("is-dragging");
        if (stage.hasPointerCapture(event.pointerId)) {
          stage.releasePointerCapture(event.pointerId);
        }
      };

      stage.addEventListener("pointerup", stopDragging);
      stage.addEventListener("pointercancel", stopDragging);
    })();
  </script>
    """


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
    .material-preview {{ display: block; width: 100%; max-width: 220px; max-height: 140px; object-fit: contain; border: 1px solid var(--line); border-radius: 8px; background: #fff; cursor: zoom-in; }}
    .material-preview:focus {{ outline: 2px solid var(--ai); outline-offset: 2px; }}
    .material-empty {{ display: inline-flex; align-items: center; min-height: 32px; color: var(--muted); font-size: 12px; }}
    .material-viewer[hidden] {{ display: none; }}
    .material-viewer {{ position: fixed; inset: 0; z-index: 9999; background: rgba(15, 23, 42, 0.72); display: flex; align-items: center; justify-content: center; overflow: hidden; }}
    .material-viewer-stage {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; overflow: hidden; background: transparent; cursor: grab; touch-action: none; }}
    .material-viewer-stage.is-dragging {{ cursor: grabbing; }}
    .material-viewer-image {{ display: block; max-width: 92vw; max-height: 84vh; object-fit: contain; background: transparent; user-select: none; pointer-events: none; transform-origin: center center; will-change: transform; }}
    .material-viewer-close {{ position: fixed; top: 20px; right: 24px; z-index: 1; min-height: 36px; padding: 0 14px; border: 1px solid rgba(255, 255, 255, 0.42); border-radius: 6px; color: #fff; background: rgba(15, 23, 42, 0.54); font-weight: 700; cursor: pointer; }}
    .material-viewer-close:focus {{ outline: 2px solid #fff; outline-offset: 2px; }}
    .material-viewer-hint {{ position: fixed; left: 50%; bottom: 22px; z-index: 1; transform: translateX(-50%); margin: 0; padding: 6px 10px; border-radius: 6px; color: #fff; background: rgba(15, 23, 42, 0.54); font-size: 12px; }}
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
      .material-viewer-close {{ top: 12px; right: 12px; }}
      .material-viewer-hint {{ width: calc(100vw - 24px); text-align: center; }}
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
  {_material_viewer()}
  {_material_viewer_script()}
</body>
</html>"""
