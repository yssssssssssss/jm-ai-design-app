---
name: jm-ai-design-app
description: Audit uploaded JM AI app UI mockups or screenshots against the JM AI design specifications from provided images. Use when a user attaches a PNG/JPG/WebP design draft and asks for a Chinese design review, visual QA, spec compliance check, HTML audit report, annotated screenshots, or acceptance checklist covering JM AI colors, typography, spacing, buttons, tags, header components, and AI icon usage.
---

# JM AI Design App

## Quick Start

Use this skill to review image-based JM AI app design drafts. Load `references/jm-ai-design-spec.md` before judging any design detail. Use `references/report-template.md` for the final Markdown report structure and `references/html-report-template.md` for the HTML artifact.

Keep the report designer-readable first: explain impact, location, and adjustment advice in Chinese. Add a compact checklist for engineering or acceptance review. When there are visible issues, include annotated screenshots or cropped problem areas.

Default to strict JM AI compliance when the user asks to audit "against JM AI specs". In strict mode, all visible brand marks, logos, active navigation states, primary actions, badges, selected states, and accent colors are in scope unless the user explicitly marks them as out-of-scope third-party content.

## Inputs

Accept:
- Uploaded UI mockups or screenshots in `.png`, `.jpg`, `.jpeg`, or `.webp`
- One image or multiple related images in the same flow
- Optional design canvas size, export scale, or DPR information

If the image is not clearly a JM AI app surface, do not silently relax the audit. State the context uncertainty, then continue strict checks for visible brand/logo/accent colors, typography, spacing, buttons, and page hierarchy. Only exempt external content when it is clearly a media asset, customer-provided image, video content, or explicitly out of scope.

## Review Workflow

1. Identify the screen context and visible modules.
2. Read `references/jm-ai-design-spec.md`.
3. Inspect the image by category:
   - brand/logo/accent color inventory
   - color and AI gradients
   - typography
   - spacing
   - AI buttons
   - AI tags
   - AI header components
   - AI icon and sparkle usage
4. Separate evidence from inference.
   - Mark issues only when the mismatch is visible or measurable.
   - For typography, spacing, and line-height, provide a "maximum-likelihood" conclusion with confidence even when exact values cannot be proven.
   - Put genuinely unmeasurable items under "无法确认", not under "问题项".
5. Run evidence scripts when local file access is available:
   - Use `scripts/analyze_image_tokens.py` to extract image size, dominant accent colors, sampled colors, and optional design scale.
   - Use `scripts/measure_regions.py` after identifying important regions to measure bboxes, gaps, and nearest spacing/type tokens.
6. Write a Chinese review report using `references/report-template.md`.
7. Create an HTML report file for the same findings using `references/html-report-template.md`.
8. If any issue has a visible location, create issue screenshots with `scripts/annotate_issues.py`.

## Measurement Rules

- Use pixel coordinates or precise visual descriptions for locations.
- If you claim a color, provide sampled or approximate hex when feasible.
- If you claim a spacing or font size, explain whether it was measured from pixels or visually inferred.
- Allow normal screenshot noise: `±1px` for spacing/font measurements and small color sampling drift.
- Do not invent tokens that are not in `references/jm-ai-design-spec.md`.

When the user provides the design canvas size:
- Compute `scale_x = screenshot_pixel_width / design_canvas_width` and `scale_y = screenshot_pixel_height / design_canvas_height`.
- Convert measured screenshot pixels back to design pixels before comparing with the spacing/type scale.
- If `scale_x` and `scale_y` differ meaningfully, state that the image may be stretched or cropped and lower confidence.
- If the provided size equals the screenshot pixel size, treat measured pixels as design pixels.

Typography inference must include:
- the visible text role being estimated,
- approximate text bounding box height,
- nearest JM AI type token candidate,
- likely font size / line-height / weight,
- confidence and reason for uncertainty.

Color inventory must include:
- logo/brand mark colors,
- active navigation colors,
- selected row/card colors,
- primary/floating button colors,
- badges/status colors,
- AI icons or sparkle marks.

In strict mode, flag off-token logo or accent colors as issues. Do not miss brand marks just because they are "logo" elements.

## Severity

- `高`: Blocks spec compliance, brand consistency, readability, or core interaction recognition.
- `中`: Visible inconsistency that should be fixed before delivery.
- `低`: Minor polish issue or weak evidence but useful adjustment.

## Output Requirements

Return a concise Markdown summary in Chinese and link to the generated HTML report. Include issue screenshots inline when available.

Required Markdown sections:
1. `总体结论`
2. `主要问题`
3. `符合规范的点`
4. `识别与测量过程`
5. `详细问题清单`
6. `研发/验收 Checklist`
7. `无法确认项`
8. `交付物`

For each problem, include:
- category
- location
- current observation
- spec expectation
- adjustment recommendation
- severity
- confidence
- evidence or measurement method

Do not write a long essay. Favor clear, actionable review notes.

## HTML And Screenshot Artifacts

For real audits, always write artifacts under the skill folder's `outpu/` directory. Create one timestamped run folder named like:

`outpu/jm-ai-audit-YYYYMMDD-HHMMSS/`

Create `outpu/` first if it does not exist. Do not write audit artifacts directly into the skill root.

Put these files inside:
- `report.html`: standalone Chinese HTML report
- `annotated.png`: full screenshot with numbered issue boxes when there are located issues
- `issue-<id>.png`: cropped screenshot for each located issue
- `issues.json`: machine-readable issue list used to generate screenshots

The final answer should link to `report.html` and show the most useful issue crops with Markdown image syntax. Use absolute filesystem paths.

Use `scripts/annotate_issues.py` like this:

```bash
python3 scripts/annotate_issues.py <input-image> <issues.json> <output-dir>
```

`issues.json` must be a JSON array. Each issue with screenshots needs:

```json
{
  "id": "color-01",
  "title": "中间箭头渐变方向不符合规范",
  "severity": "中",
  "category": "色彩/渐变",
  "bbox": [1008, 360, 45, 48]
}
```

Skip screenshot generation for issues without reliable coordinates.

Use `scripts/analyze_image_tokens.py` for color evidence:

```bash
python3 scripts/analyze_image_tokens.py <input-image> \
  --design-size 1508x815 \
  --sample logo:180:54 \
  --sample primary_button:2938:1510 \
  --output tokens.json
```

Use `scripts/measure_regions.py` for region and gap evidence:

```bash
python3 scripts/measure_regions.py <input-image> regions.json \
  --design-size 1508x815 \
  --crop-dir region-crops \
  --output measurements.json
```

`regions.json` can be:

```json
{
  "regions": [
    {"id": "left_nav_title", "title": "培训中心", "bbox": [110, 158, 130, 38], "role_hint": "heading", "measure_kind": "text"},
    {"id": "selected_lesson", "title": "选中课程", "bbox": [506, 411, 655, 116], "measure_kind": "component"}
  ],
  "distances": [
    {"id": "nav_to_content", "from": "left_nav_title", "to": "selected_lesson", "axis": "x"}
  ]
}
```

Treat script output as evidence. The final report must still explain the component role, expected JM AI token, and confidence.

Use tight text-only bboxes for typography inference. Do not feed an entire toolbar, card, or row bbox as a text bbox; that will overestimate line-height.

## References

- `references/jm-ai-design-spec.md`: canonical checklist and extracted tokens
- `references/report-template.md`: output format
- `references/html-report-template.md`: standalone HTML report structure
- `scripts/analyze_image_tokens.py`: image size, color inventory, token-distance evidence
- `scripts/measure_regions.py`: region size, gap, crop, and scale-conversion evidence
- `scripts/annotate_issues.py`: issue box and crop generator
- `assets/spec-images/`: original reference images for visual comparison when needed
