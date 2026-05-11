# JM AI HTML Report Template

Create a standalone `report.html` in Chinese. Do not depend on remote CSS, JavaScript, fonts, or images. Use relative image paths for screenshots in the same output folder.

Minimum structure:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JM AI 设计规范审核报告</title>
  <style>
    :root {
      color-scheme: light;
      --ai: #6B36FA;
      --ai-soft: #F3F0FF;
      --text: #1f1f24;
      --muted: #767680;
      --line: #e7e7eb;
      --bg: #f7f7f9;
      --card: #ffffff;
      --danger: #d92d20;
      --warn: #b54708;
      --ok: #067647;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
    }
    main { max-width: 1180px; margin: 0 auto; padding: 32px 24px 56px; }
    h1 { margin: 0 0 8px; font-size: 28px; line-height: 40px; font-weight: 600; }
    h2 { margin: 32px 0 12px; font-size: 18px; line-height: 28px; font-weight: 600; }
    p { margin: 0 0 10px; }
    table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); }
    th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { background: #fafafa; font-weight: 600; }
    .summary, .card { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }
    .meta { color: var(--muted); }
    .badge { display: inline-flex; align-items: center; min-height: 22px; padding: 0 8px; border-radius: 6px; background: var(--ai-soft); color: var(--ai); font-weight: 600; }
    .severity-high { color: var(--danger); font-weight: 600; }
    .severity-mid { color: var(--warn); font-weight: 600; }
    .severity-low { color: var(--muted); font-weight: 600; }
    .screenshots { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
    figure { margin: 0; background: var(--card); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
    figure img { display: block; width: 100%; height: auto; }
    figcaption { padding: 10px 12px; color: var(--muted); }
  </style>
</head>
<body>
  <main>
    <h1>JM AI 设计规范审核报告</h1>
    <p class="meta">审核对象：{{image_name}} ｜ 生成时间：{{generated_at}}</p>

    <section class="summary">
      <span class="badge">{{overall_status}}</span>
      <p>{{summary}}</p>
    </section>

    <h2>主要问题</h2>
    {{major_issues_html}}

    <h2>问题截图</h2>
    <div class="screenshots">
      {{screenshots_html}}
    </div>

    <h2>详细问题清单</h2>
    {{issues_table_html}}

    <h2>符合规范的点</h2>
    {{passes_html}}

    <h2>研发/验收 Checklist</h2>
    {{checklist_table_html}}

    <h2>无法确认项</h2>
    {{cannot_verify_table_html}}
  </main>
</body>
</html>
```

Replace placeholders with real HTML. Escape user/design text. Keep the HTML report readable even when there are no issues or screenshots.
