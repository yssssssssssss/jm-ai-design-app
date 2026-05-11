# JM AI 设计规范审核报告模板

Use this structure for final answers. Keep the tone professional, direct, and useful for designers.

## 总体结论

- 一句话说明整体是否符合 JM AI 规范。
- 列出最需要优先调整的 2-4 个问题。
- 说明哪些部分无法从图片中确认。

## 主要问题

Use bullets. Each bullet should include impact and recommended direction.

Format:
- `高/中/低`：位置 - 问题。建议：调整方式。

## 符合规范的点

List clear passes. Do not praise vague things.

Format:
- 分类：位置 - 符合的规范点。

## 识别与测量过程

Explain how conclusions were reached. Include maximum-likelihood typography and spacing judgments even when exact values cannot be proven from the screenshot.

Required bullets or table:
- 图片尺寸 / 用户提供的设计稿尺寸 / 是否存在缩放换算
- 色彩采样点：位置、近似 hex、是否命中 JM AI token
- 字体识别：文本角色、估计 bbox 高度、最可能字号/行高/字重、置信度
- 间距识别：测量位置、截图 px、换算后设计 px、最近规范 token、置信度

## 详细问题清单

| 优先级 | 分类 | 位置 | 当前表现 | 规范要求 | 修改建议 | 测量/证据 | 置信度 |
|---|---|---|---|---|---|---|---|
| 高/中/低 | 色彩/字体/间距/按钮/标签/头部/图标/其他 | 坐标或清晰描述 | 观察结果 | 规范依据 | 可执行调整 | 采样、bbox、像素测量或视觉推断 | 0.0-1.0 |

## 研发/验收 Checklist

| 检查项 | 状态 | 说明 |
|---|---|---|
| AI 主色/渐变符合规范 | 通过/不通过/无法确认 | 说明 |
| 字号、行高、字重符合规范 | 通过/不通过/无法确认 | 说明 |
| 间距来自 2/4 倍数体系 | 通过/不通过/无法确认 | 说明 |
| AI 按钮样式属于规范类型 | 通过/不通过/无法确认 | 说明 |
| AI 标签样式属于规范类型 | 通过/不通过/无法确认 | 说明 |
| 头部组件层级与留白合理 | 通过/不通过/无法确认 | 说明 |
| AI 图标/星标位置与语义合理 | 通过/不通过/无法确认 | 说明 |

## 无法确认项

| 分类 | 原因 | 建议补充材料 |
|---|---|---|
| 示例：字体族 | 截图无法可靠识别具体字体 | 提供 Figma 标注或 CSS |

## 交付物

- HTML 报告：`/absolute/path/to/report.html`
- 全图标注：`/absolute/path/to/annotated.png`
- 问题截图：
  - `issue-color-01`：`/absolute/path/to/issue-color-01.png`

When no screenshots are generated, explain why, such as "本次问题无法可靠定位到具体截图区域".
