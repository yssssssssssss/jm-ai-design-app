# JM AI Design App Spec

This reference is extracted from the provided JM AI design specification images. Treat it as the canonical source for audits. Do not invent missing tokens.

Original visual references live in `../assets/spec-images/`.

## Audit Categories

- Brand/logo/accent color inventory
- Color and gradients
- Typography
- Spacing
- AI buttons
- AI tags
- Header component
- AI icon and sparkle mark

## Color

### Theme Colors

Use these colors for AI-branded UI elements:

| Token / role | Hex |
|---|---|
| Dark | `#000A1C` |
| White | `#FFFFFF` |
| Assist light purple | `#8F55FD` |
| Primary deep purple | `#6B36FA` |
| Assist standard blue | `#3544EB` |
| Assist deep blue | `#052474` |

Strict mode:
- Treat visible product logos, brand marks, active navigation icons, selected states, primary actions, floating action buttons, badges, and status accents as color-audit targets.
- If the audit target is supposed to conform to JM AI, these elements should use JM AI color tokens unless the user explicitly exempts the brand mark or marks it as third-party/customer content.
- Flag off-token red, orange, green, cyan, or other non-JM AI accent colors when they drive product UI state or brand perception.

Functional solid tokens:

| Token | Hex |
|---|---|
| `ai/ai-normal` | `#6B36FA` |
| `ai/ai-hover` | `#9975FC` |
| `ai/ai-click` | `#4B26AF` |
| `ai/ai-disable` | `#BEAAF3` |
| `ai/ai-border` | `#EBE5FA` |
| `ai/ai-background` | `#EDEEFF` |
| `ai/ai-light-normal` | `#F3F0FF` |
| `ai/ai-light-hover` | `#F7F5FF` |
| `ai/ai-light-click` | `#EFEBFE` |
| `ai/ai-light-disable` | `#F4F2FA` |
| `ai/ai-light-border` | `#F0EBFC` |
| `ai/ai-light-background` | `#F4F5FF` |

Gradient tokens exist as named tokens:
- `Gradient/ai/ai-normal`
- `Gradient/ai/ai-hover`
- `Gradient/ai/ai-click`
- `Gradient/ai/ai-disable`
- `Gradient/ai/ai-border`
- `Gradient/ai/ai-background`
- `Gradient/ai/ai-light-normal`
- `Gradient/ai/ai-light-hover`
- `Gradient/ai/ai-light-click`
- `Gradient/ai/ai-light-disable`
- `Gradient/ai/ai-light-border`
- `Gradient/ai/ai-light-background`

### Gradient Rules

- Use fluid or linear gradients.
- Purple must dominate.
- Blue must not exceed about `20%` of the gradient area.
- Recommended order: deep blue -> deep purple -> light purple.
- Direction: bottom-left to top-right.
- Do not use non-brand colors.
- Do not change gradient ratio, use other gradient types, or use other angles.

Usage:
- Vivid version: buttons, borders, highlighted text.
- Soft version: buttons, tags, backgrounds.
- Deep version: text, motion/effect changes.

## Typography

### Font Family

Recommended font stack:

`-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Ubuntu, Helvetica Neue, Helvetica, Arial, PingFang SC, Hiragino Sans GB, Microsoft YaHei UI, Microsoft YaHei, Source Han Sans SC CN, Apple Color Emoji`

Do not flag exact font family from screenshots unless the visible font is clearly inconsistent, such as serif, handwritten, or decorative fonts in product UI.

### Screenshot Inference Process

When exact design data is unavailable, still provide the most likely typography conclusion:

1. Identify the text role: display, H1, H2, H3, body, helper/caption, navigation, badge, or control label.
2. Estimate text bounding box height in screenshot pixels.
3. If a design canvas size or export scale is provided, convert screenshot pixels to design pixels.
4. Match to the nearest JM AI type scale token.
5. Estimate weight by visual stroke density: regular-like (`400`) or semibold/bold-like (`600`).
6. Estimate line-height from multi-line text boxes, baseline rhythm, or vertical text container height when visible.
7. Report as "likely" with confidence, not as exact fact, unless Figma/CSS data is provided.

### Line Height

Formula:

`line-height = font-size * 1.5`

If the result is odd or decimal, round up to the nearest even number.

Example: `14px` font size -> `22px` line height.

### Weight

- Regular: `400`
- Semibold/Bold: `600`

### Type Scale

| Usage | Font size | Line height | Weight |
|---|---:|---:|---|
| Display text | `32` | `48` | Bold |
| Display text | `24` | `36` | Bold |
| H1 | `18` | `28` | Bold |
| H2 | `16` | `24` | Bold |
| H3 | `14` | `22` | Bold |
| Body | `14` | `22` | Regular |
| Helper / caption | `12` | `18` | Regular |

## Spacing

Spacing follows an even-number rule. Usually use multiples of `4`; minimum can use `2` or `0`.

Allowed spacing scale:

`0, 2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 56`

Common vertical spacing:

| Value | Name | Recommended use |
|---:|---|---|
| `32px` | `@vertical-xxl` | Major split between user and bot content |
| `20px` | `@vertical-l` | Panel outer spacing or container inner spacing |
| `12px` | `@vertical-s` | Small separation between item groups |
| `8px` | `@vertical-xs` | Small separation between item rows |

Flag visible measured gaps that are not in the allowed scale, except for unavoidable screenshot scaling noise.

When the user provides design dimensions, convert screenshot measurements back to design pixels before checking the scale. This materially improves spacing validation when images are exported at 2x or 3x.

Report the measurement process:
- screenshot bbox or endpoints,
- measured screenshot px,
- design scale if provided,
- converted design px,
- nearest allowed spacing token,
- pass/fail confidence.

## AI Buttons

Allowed button style families:
- Primary filled
- Secondary filled
- Primary outline
- Dashed gradient button
- Ghost gradient button
- Dashed button
- Secondary outline
- Primary text
- Link

Review points:
- Button family must be recognizable as one of the allowed families.
- AI-branded button colors must use AI color or gradient tokens.
- Filled primary buttons should emphasize the primary action and use AI purple/gradient.
- Disabled buttons should use disabled or light disabled tokens, not just arbitrary opacity.
- Text and link buttons should not look like filled or outline buttons.

Known limits:
- The provided images do not expose exact button padding, height, radius, icon size, or per-state colors for every button size. Mark those as unable to verify unless the uploaded image or Figma export provides values.

## AI Tags

Allowed tag families:
- Solid new
- Solid
- Default
- Border / outline
- Corner badge

Review points:
- AI tags must match one of these families.
- AI-branded tag colors must come from AI tokens.
- Corner badge uses a small purple `AI` label at the top-right of a card or image.
- Do not introduce unlisted tag styles without a clear product reason.

Known limits:
- Exact tag padding, height, radius, and border width are not readable from the provided images. Mark those as unable to verify unless values are provided.

## Header Component

The header spec image defines a JM AI/dongDesign-AI design-spec style header, used as a reference for visual hierarchy:
- Large Chinese title paired with a lighter English label.
- Supporting description below title when needed.
- Right-side brand text and version pill.
- Light neutral header background.
- Clear separation between header and content area.

Review app screens for:
- Clear page title hierarchy.
- Right-side actions or brand/version elements not competing with the main title.
- Adequate top and side safe spacing based on the spacing scale.
- Consistent neutral background and text contrast.

Do not require every app screen to show brand/version text; use this section for hierarchy and spacing checks unless the product explicitly uses the design-spec header component.

## AI Icon And Sparkle Mark

Purpose:
- Mark AI capability in product UI.
- Commonly used with AI buttons, strategy titles, and AI-related content.

When to add sparkle:
- Generation, creation, enhancement, or "magic" features.
- New/unique AI features needing user education.
- Brand reinforcement moments.

When not to add sparkle:
- Basic analysis, query, conversation, or already familiar AI features unless brand emphasis is needed.

Construction:
- Use base functional icon + sparkle mark.
- Sparkle usually sits top-right or bottom-right.
- It must not block the base icon or reduce recognition.
- Keep stroke style consistent within the same icon set.

Reference geometry from icon spec:
- Base example canvas: `576px * 576px`
- Common sparkle region: `240px * 240px`
- Corner radius: `48px`
- Type 1 common icon stroke: `48px`
- Type 2 card icon stroke: `36px`
- Non-regular inside placement sparkle region: `144px * 144px`, breakpoint `28px`
- Non-regular outside placement sparkle region: `206px * 206px`

In ordinary UI screenshots, treat these as proportional guidance rather than strict 1:1 measurements.

## Evidence Standards

Flag as a problem only when:
- A visible UI element clearly violates a listed token or rule.
- A measurement can be reasonably inferred from the screenshot.
- The mismatch affects recognizability, hierarchy, brand consistency, or delivery quality.

Mark as unable to verify when:
- The component is too small or blurred.
- Exact dimensions are not in the provided specs.
- A screenshot cannot prove font family, font weight, or exact token values.
- The image has compression, scale, or export artifacts that make measurement unreliable.
