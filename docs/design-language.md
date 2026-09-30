# MDT Observatory design language

This document extracts the visual and interaction system used by MDT Observatory so another application can reproduce its character without copying its clinical content.

The design should feel like a trusted institutional workstation: calm, dense, inspectable and operational. It is not a consumer dashboard, a marketing site or a generic collection of rounded cards.

## 1. Design signature

The recognizable combination is:

1. **Dark institutional chrome** frames the product and establishes place, workstation and system state.
2. **Cool neutral work surfaces** keep information dense without feeling visually heavy.
3. **One restrained accent** identifies primary actions and selected state.
4. **Semantic status colors** communicate success, warning, failure and links; they never decorate.
5. **Small monospaced labels** provide operational hierarchy above plain-language headings.
6. **Layered disclosure** keeps the active decision visible while evidence, provenance and full records remain one action away.
7. **Distinct workspaces** change information structure, borders and emphasis while retaining the same tokens and controls.
8. **Visible human control** makes review, uncertainty, failure and provenance first-class interface elements.

The system's character comes from hierarchy and restraint more than from illustration, gradients or animation.

## 2. Principles

### Make state legible

Every screen should answer:

- Where am I?
- What object or case am I working on?
- What is happening now?
- What needs attention?
- What can I inspect?
- What can I do next?

Use persistent chrome, a contextual banner, an attention strip and explicit action labels. Do not rely on color alone.

### Put the current task before the full record

The primary canvas contains the active assessment, activity and human controls. Supporting material belongs in sticky rails, expandable sections and inspection drawers.

This creates a consistent depth model:

```text
system and location
  → current object
    → current task and state
      → supporting summary
        → full record, evidence and provenance
```

### Prefer inspectability over apparent simplicity

Complexity is not hidden; it is staged. A compact summary should always lead to the underlying record, source or rationale.

### Use visual variation to express work

Different workspaces may use different grids, border treatments and information structures. They should not introduce independent component libraries or color systems.

### Keep operational and domain information separate

User-facing panels describe the work, findings, uncertainty and required action. Provider metadata, request details and technical telemetry belong in audit or diagnostics surfaces.

## 3. Foundations

### Typography

Use system fonts. The application should look native to an enterprise workstation and render reliably without a web-font dependency.

```css
--font-sans: "Segoe UI", Aptos, Calibri, -apple-system, BlinkMacSystemFont, sans-serif;
--font-mono: Consolas, "Courier New", Courier, monospace;
```

| Element | Treatment |
|---|---|
| Body | 14 px, relaxed line height, regular weight |
| Page title | 30 px, semibold, tight tracking |
| Section title | 20 px, semibold |
| Card title | 16 px, semibold |
| Body detail | 12–14 px, 24–28 px line height |
| Eyebrow / operational label | 10 px, monospaced, uppercase, wide tracking |
| Metadata | 9–11 px, muted |

Headings are sentence case. Uppercase is reserved for short operational labels, not prose.

### Color tokens

Components use semantic tokens rather than literal colors. Preserve this indirection when porting the design.

| Token | Light | Dark | Purpose |
|---|---:|---:|---|
| `--cp-bg` | `#eef2f5` | `#2b3238` | Application canvas |
| `--cp-bg-elevated` | `#f8fafb` | `#242a30` | Recessed or supporting region |
| `--cp-surface` | `#ffffff` | `#1f2429` | Primary surface |
| `--cp-surface-soft` | `#f3f6f8` | `#262c32` | Hover and secondary surface |
| `--cp-border` | `#d8dfe5` | `#3f4953` | Default divider |
| `--cp-border-strong` | `#919191` | `#5f5f5f` | Strong structure |
| `--cp-text` | `#242424` | `#dedede` | Primary text |
| `--cp-text-muted` | `#5c5c5c` | `#919191` | Secondary text |
| `--cp-text-soft` | `#6f6f6f` | `#b0b0b0` | Labels and metadata |
| `--cp-chrome` | `#10304d` | `#0b1a29` | Institutional header |
| `--cp-chrome-fg` | `#eaf2f8` | `#dbe7f1` | Header foreground |
| `--cp-chrome-muted` | `#a9c0d4` | `#8ea6ba` | Header metadata |
| `--cp-banner` | `#e2ebf2` | `#1a2733` | Context banner |
| `--cp-accent` | `#b11f4b` | `#fd8ea1` | Primary action and selection |
| `--cp-accent-hover` | `#9a1a41` | `#fb7b91` | Primary hover |
| `--cp-accent-soft` | `rgba(177,31,75,.08)` | `rgba(253,142,161,.14)` | Selected and emphasized region |
| `--cp-success` | `#16a34a` | `#4ade80` | Completed or supported |
| `--cp-warning` | `#f59e0b` | `#fbbf24` | Conditional or unresolved |
| `--cp-danger` | `#dc2626` | `#f87171` | Failure or blocking state |
| `--cp-link` | `#0078d4` | `#4da6ff` | Links and information |

The burgundy/pink accent is the product signature. Navy belongs to system chrome. Green, amber and red retain fixed semantic meaning.

### Surfaces and borders

- Application background: cool grey, never pure white.
- Primary content: white or charcoal surfaces.
- Default border: 1 px neutral.
- Cards: 16 px radius.
- Inputs and primary buttons: 12 px radius.
- Compact controls and badges: 6–8 px radius.
- Structural emphasis: a 2–8 px edge, usually on the left or top.
- Shadow: reserve the large soft shadow for drawers and temporary overlays.

Avoid stacking cards inside cards without a clear change in information depth. Supporting regions within a card usually use `--cp-bg-elevated` and a border edge rather than another floating container.

### Spacing

The practical spacing scale is:

```text
4  8  12  16  20  24  32 px
```

Typical use:

- 4–8 px: icon, badge and metadata gaps
- 12 px: compact control padding and row gaps
- 16 px: card padding on constrained screens
- 20–24 px: normal panel padding and section separation
- 32 px: major page separation

Content is compact, but text gets generous line height. Density comes from structure, not cramped prose.

### Iconography

Use one outlined icon family, currently Lucide:

- 14–18 px for controls and metadata
- 18–21 px for navigation
- 28 px for workspace emblems

Icons support a text label or a familiar control. Do not use multiple icon styles or decorative icon clouds.

## 4. Page anatomy

A full application screen follows this stack:

```text
optional safety / environment strip
institutional header
context banner
sidebar + main canvas
  page toolbar / breadcrumb
  attention and error state
  task content
  sticky contextual rail
drawers and modals
```

### Institutional header

The header establishes product identity, organization, workstation, time, connectivity and global controls.

- Navy background and light foreground
- 56 px minimum height
- Compact, high-information layout
- Product mark is geometric and simple
- Organization is secondary to the product name
- Connection and theme state remain visible but quiet

Replace the fictional hospital naming in other products, but preserve the structure:

```text
[mark] PRODUCT / MODULE
       Organization · Department

Location · Workstation        Time    Connection    Global controls
```

### Context banner

The banner identifies the object currently being handled. In another domain this could be a customer, incident, asset, application or project.

It contains:

- a leading identity block;
- 3–5 high-value facts;
- one relevant communication or operating attribute;
- an action to open the complete record.

Only show recorded data. Missing fields remain absent or are explicitly labelled; never fabricate a complete-looking banner.

### Sidebar

The sidebar is a persistent workspace map, not a second command bar.

- 220 px desktop width
- sticky and independently scrollable
- primary shared workspaces first
- specialist or functional workspaces grouped below
- current status appears as a short detail line
- active work may use a small pulsing dot
- explanatory governance copy sits at the bottom

On small screens it becomes a temporary panel opened from the header.

### Main canvas

- Maximum width: approximately 1900 px
- Horizontal padding: 12 px mobile, 24 px tablet, 32 px wide screen
- Shared overview screens may use a sticky 260 px context rail on wide screens
- Focused workspaces place the current-object briefing full-width at the top of the main canvas
- Content grids collapse to one column before information becomes narrow

### Inspection drawer

Use a right-side drawer for evidence, provenance, full assessments and complete records.

- Full viewport height
- 560 px normal width; 720 px for evidence-heavy content
- Surface background, left border and overlay
- Explicit close control
- Escape closes the drawer
- Focus returns to the invoking control
- Clicking the backdrop may close it

The drawer heading uses an eyebrow such as `INSPECTABLE BY DESIGN` to reinforce the interaction model.

## 5. Core components

### Eyebrow

A small monospaced label that explains the role of the section.

```text
SPECIALTY POSITIONS
CURRENT CONCLUSION
CLAIM → SOURCE
```

Use it to orient, not to decorate. Keep it under roughly four words where possible.

### Card and panel

```css
.card {
  border: 1px solid var(--cp-border);
  border-radius: 16px;
  background: var(--cp-surface);
}

.panel {
  min-width: 0;
  padding: 20px 24px;
}
```

Cards group related work. Panels are cards with standard content padding.

### Buttons

There are four button levels:

| Type | Use |
|---|---|
| Primary | One main action in the local decision area |
| Secondary | Normal reversible actions |
| Text | Low-emphasis actions embedded in content |
| Icon | Familiar compact actions with an accessible name |

Buttons use plain labels: `Start case`, `Send instruction`, `Open original source`. Avoid vague labels such as `Continue` when the result is not obvious.

Primary actions use the accent fill. Destructive actions do not borrow the accent; they use explicit danger treatment and wording.

### Badge and status

Badges are compact textual labels with a border and subtle fill. They are never color-only.

Suggested tone mapping:

| Tone | Meaning |
|---|---|
| Neutral | Category, metadata or dormant state |
| Accent | Active work or selected context |
| Success | Complete, published, supported or concurred |
| Warning | Review, uncertainty, conditional state or limitation |
| Danger | Error, failed review, escalation or blocking state |

Only actively running work pulses. Completion does not animate.

### Attention strip

The attention strip sits near the top of a workspace and combines:

- a 4 px semantic left border;
- a status badge;
- one plain-language explanation.

It states what changed or what the user needs to do. It does not repeat the whole page status.

### Blocking handoff

When progress depends on a human, place a warning-bordered alert directly below the attention strip:

- eyebrow naming the block (`HUMAN FINDING REQUIRED · MDT BLOCKED`);
- who the process is waiting for and what the next step hinges on;
- a numbered "what unlocks this" sequence;
- one primary action that focuses and scrolls to the input field, which is itself warning-bordered and opened.

Show it only while the dependency is genuinely open. An insufficient reply keeps it visible and says why.

### Reasoning path

Present an agent's public account as a numbered sequence, each step with a label, a one-line explanation and bounded content:

1. Trying to answer
2. Considered
3. This showed
4. But this remains uncertain (warning border)
5. So the current conclusion is
6. Next

Label it as a public summary, never as private model deliberation. Link to the full assessment drawer.

### Data fields

Use definition lists for structured facts:

- label: 10 px, muted, uppercase for standard fields;
- value: 12–14 px with generous line height;
- compact mode: two-column label/value rows;
- each row separated by a neutral divider.

Tables are for comparison across records. Definition lists are for inspecting one record.

### Activity stream

Activity is newest first and bounded in height when it supports a live task.

Each item has:

- a small node;
- an operational label;
- a monospaced timestamp;
- one readable summary.

Show the domain action, finding or failure. Do not replace it with request IDs, model names or infrastructure details.

### Expandable section

Use native `details`/`summary` for supporting records and optional detail. The summary states exactly what opens.

Good:

```text
Open radiology clinical workspace and source records
Position provenance
Case timeline and treatment history
```

Avoid nesting several closed disclosure controls before the user can reach essential information.

### Alert

Alerts use a visible border, semantic text color and actionable language. Failures remain failures; do not convert them into empty states or success-shaped fallbacks.

### Forms

- Labels remain programmatically associated even when visually hidden.
- Inputs use the surface color, neutral border and 12 px radius.
- Text areas have a minimum height of 96 px and remain vertically resizable.
- Placeholder text is an example, not a substitute for a label.
- A form footer places helper actions left and the primary submission right.
- After submission, show a compact receipt with the submitted text and resulting state.

## 6. Workspace variation

Shared chrome, controls, typography and semantic colors remain fixed. A workspace may vary:

- page background tint;
- grid proportions;
- border placement and thickness;
- emblem shape;
- restrained use of monospace;
- the structure used to represent its work.

MDT Observatory uses these patterns:

| Workspace character | Structural treatment |
|---|---|
| Image comparison | Dark high-contrast header, blue orientation color, wide visual column |
| Treatment and tolerability | Accent-tinted canvas, three-column board, rounded header |
| Procedural planning | Green edge, planning facts beside a larger clinical canvas |
| Tissue / laboratory report | Squared report treatment, strong rules, more monospace |
| Research evidence | Table-led layout, square edges, double rule and source emphasis |
| Conditional pathway | Amber edge and explicit eligibility conditions |
| Human preferences | Softer centered composition, pill-shaped focus labels, narrower maximum width |

This is the main reuse rule: **vary the representation of the work, not the design-system fundamentals**.

For a new application, assign each major workspace:

```ts
interface WorkspaceVisualLanguage {
  identity: string;
  orientationColor: SemanticToken;
  canvasTreatment: string;
  headerTreatment: string;
  grid: string;
  focusLabels: [string, string, string];
}
```

Keep orientation color separate from status. A blue or green workspace does not imply success or approval.

## 7. Content design

### Voice

Interface language is:

- plain;
- direct;
- specific;
- operational;
- honest about uncertainty.

Prefer:

```text
Connection interrupted. Reconnecting to the same meeting; your input is preserved.
Full text has not been retrieved.
Tell me what you reviewed and found.
```

Avoid:

```text
Something went wrong.
AI insights ready.
Proceed with confidence.
```

### Labels

Name the work and actor precisely:

- `Review activity`
- `Published specialist position`
- `Human review required`
- `Evidence applicability`
- `Open complete record`

Do not use intelligence-themed labels when an ordinary work label is clearer.

### Uncertainty and provenance

Uncertainty is a content type, not a disclaimer. Give it a named section and warning treatment.

Claims should be able to expose a chain such as:

```text
claim → evidence → source → scrutiny
```

Access limitations, incomplete records and failed retrieval remain visible beside the affected information.

## 8. Motion

Motion is limited to new public activity:

```css
.clinical-update {
  animation: clinical-arrival 900ms ease-out;
}

@keyframes clinical-arrival {
  from { opacity: .35; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}
```

Rules:

- Never delay state, controls, errors or critical information for animation.
- Do not animate ordinary card entry or navigation.
- Disable animation and transitions under `prefers-reduced-motion: reduce`.
- Use pulsing only for genuinely active work.

## 9. Theme behavior

Support light, dark and system preference.

Apply the theme before the application paints to prevent a flash of the wrong theme:

1. Load a small blocking script in the document head.
2. Read a valid URL override if the product needs one.
3. Read the persisted preference.
4. Fall back to `prefers-color-scheme`.
5. Set `data-theme` on the root element.
6. Subscribe to system and cross-tab storage changes.

If storage is unavailable, the theme still changes for the current visit and the interface states that it could not be saved.

## 10. Accessibility requirements

The visual identity depends on these behaviors:

- a skip link appears on keyboard focus;
- all icon-only buttons have accessible names;
- visible focus uses a 2 px accent outline with 4 px offset;
- status always includes text;
- drawers use the native dialog model and restore focus;
- headings preserve a logical hierarchy;
- tables include captions, even when visually hidden;
- responsive layouts preserve task order;
- reduced-motion preference disables non-essential motion;
- touch targets are normally at least 36–40 px high;
- color is never the sole indication of state, workspace or approval.

## 11. What not to copy

These are product-specific, not part of the reusable design system:

- hospital and department names;
- patient-banner field names;
- clinical role labels and icons;
- safety language specific to a demonstration;
- burgundy as a mandated corporate brand color;
- the exact seven-workspace topology.

Retain their functions: institutional context, current-object identity, explicit environment status and clear workspace orientation.

## 12. Adoption recipe

To make another application look and behave like MDT Observatory:

1. Copy the semantic token structure and define light and dark values.
2. Use the system typography, type scale, spacing, radii and border hierarchy.
3. Build the institutional header, contextual banner, sticky sidebar and bounded main canvas.
4. Implement the core primitives: eyebrow, panel, buttons, badges, attention strip, data fields, activity stream, disclosure section, alert and drawer.
5. Define one visual-language configuration per major workspace.
6. Separate orientation colors from semantic status colors.
7. Make evidence, source data or provenance reachable from every consequential summary.
8. Add before-paint theme selection, keyboard focus, responsive collapse and reduced-motion behavior.
9. Test the result in light and dark themes at mobile, tablet and wide desktop widths.

Do not begin by cloning individual screens. Build the tokens and primitives first; otherwise the result will resemble the screenshots while drifting as soon as new screens are added.

## 13. Source map

The current implementation remains the executable source of truth:

| Concern | Source |
|---|---|
| Theme tokens, typography, primitives and motion | `frontend/src/tailwind.css` |
| Before-paint theme selection | `frontend/public/assets/theme.js` |
| Theme controller | `frontend/src/theme.ts` |
| Institutional header and context banner | `frontend/src/HospitalChrome.tsx` |
| Application shell, navigation and page anatomy | `frontend/src/App.tsx` |
| Shared interface components | `frontend/src/ui.tsx` |
| Workspace-specific visual configurations | `frontend/src/roleLayouts.ts` |
| Specialist workspace composition | `frontend/src/Specialist.tsx` |
| Case-selection pattern | `frontend/src/CaseSelection.tsx` |

When the implementation and this document disagree, inspect whether the code change is intentional and update both together.
