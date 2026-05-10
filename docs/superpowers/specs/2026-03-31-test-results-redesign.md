# Test Results Modal — UI Redesign Spec

**Date:** 2026-03-31
**Status:** Approved
**Scope:** Frontend-only redesign of `TestResultsModal.tsx` + backend API addition for acorn cost

## Overview

Complete visual overhaul of the Test Results modal (`frontend/src/components/processing/TestResultsModal.tsx`) to improve readability, visual appeal, and data presentation. The current modal renders flat cards with raw JSON dumps and missing metrics. The redesign introduces a hero stats banner, visual progress timeline, collapsible step cards, and smart data rendering.

## Design Decisions

| Decision | Choice | Alternatives Rejected |
|----------|--------|-----------------------|
| Hero banner style | Clean White + Orange left border | Dark espresso gradient, warm cream gradient, soft orange gradient |
| Hero banner metrics | Duration, Steps, Acorns Used | Token counts (hidden from users), API call counts (unnecessary) |
| Step card data display | Mini Cards Grid (2-column) | Pill tags, alternating row table |
| AI output rendering | Speech-bubble style with "AI Generated" label | Quote block, plain card |
| Step card behavior | Collapsible accordion (collapsed by default) | Always expanded (current) |

## Components

### 1. Hero Stats Banner

White card with `border-left: 4px solid scurry-orange`. Contains:

- **Left side:** Status icon (checkmark/X/spinner in colored circle) + "Execution #ID" + relative timestamp
- **Right side:** Status pill badge (Success/Failed/Running) with colored background
- **Bottom row:** 3 metric cards in a grid:
  - **Duration** — `formatExecutionTime(total_execution_time)`, orange text
  - **Steps** — `completed/total` count, orange text
  - **Acorns Used** — acorn cost with favicon SVG icon, orange text

Each metric card: `bg-scurry-gray-light`, rounded, centered text with uppercase label below.

**Data source for acorns:** The backend currently calculates acorn cost during execution via `usd_to_acorns()` but does not return it in the API response. A new field `acorns_used` must be added to the `Execution` Pydantic response model, computed from token usage at response time (see Backend Changes section).

### 2. Visual Progress Timeline

Horizontal connected-dot timeline between the hero banner and step cards.

- One dot per component execution, connected by a colored line
- **Completed:** green filled circle with checkmark
- **Failed:** red filled circle with X
- **Running:** yellow filled circle with spinning animation
- **Pending:** gray outlined circle
- Below each dot: per-step execution time in small text
- Below the time: component name (truncated if needed)

The line color matches the status of the step it connects to (green up to the last completed step, then gray for pending).

### 3. Collapsible Step Cards

Accordion-style cards, **all collapsed by default**. Each card has:

**Header row (always visible):**
- Colored left border (green=completed, red=failed, yellow=running, gray=pending)
- Type-specific icon in a colored rounded square:
  - `input_sources` → 📥 on `bg-blue-50` (`#E3F2FD`)
  - `text_generation` → 🤖 on `bg-orange-50` (`#FFF3E0`)
  - `ai_filter` → 🧠 on `bg-purple-50` (`#F3E5F5`)
  - `email` → 📧 on `bg-green-50` (`#E8F5E9`)
  - `conditional_logic` → 🔀 on `bg-yellow-50` (`#FFF8E1`)
  - `action` → ⚡ on `bg-cyan-50` (`#E0F7FA`)
  - Default fallback → 📦 on `bg-gray-50`
- Component name (bold) + component type + execution time in subtitle
- Status text (✓ DONE / ✗ FAILED / ⟳ RUNNING / ○ PENDING)
- Chevron indicator (▸ collapsed / ▾ expanded)

**Expanded content:**
- Section header: "Output" (or "AI Output" for text_generation/ai_filter) with orange label and horizontal rule
- Data display (see next section)
- Action buttons row: "📋 Copy" and "{ } Raw" (toggle to show raw JSON)

### 4. Smart Data Display

Two rendering modes based on the component type (not output data shape):

**Structured data (component types: `input_sources`, `email`, `conditional_logic`, `action`):** Mini Cards Grid
- 2-column responsive grid
- Each field gets its own mini card: `bg-scurry-gray-light`, rounded-lg, with:
  - Uppercase label (9px, gray, letter-spaced) — the key name
  - Value text (13px, espresso color, medium weight) — the value
- Arrays render as comma-separated values
- Nested objects show first-level keys only; deeper nesting falls back to Raw JSON

**AI-generated text (component types: `text_generation`, `ai_filter`):** Speech Bubble
- Container: `bg-[#FFF8F5]` with subtle orange border, rounded-xl
- Header: 🤖 icon + "AI Generated" label in orange
- Body text: 13px, line-height 1.7, espresso color
- If the text contains bullet points or lists, render each as a row with orange dot indicator on white-tinted background

**Raw JSON toggle:**
- Clicking "{ } Raw" replaces the smart display with a monospace `<pre>` block
- JSON is syntax-highlighted (keys in gray, strings in espresso, numbers in orange)
- Button text changes to "{ } Smart" to toggle back
- Max height: 200px with scroll overflow

**Copy button:**
- Copies the output_data as formatted JSON to clipboard
- Shows a brief "Copied!" tooltip/toast on success

### 5. Error State Rendering

For failed steps:
- Card border-left: `4px solid scurry-red`
- Expanded content shows error box: `bg-scurry-red-light` with red border
- Error box contains: warning icon + error title (bold) + error message text
- No output data section shown for failed steps (only error)

### 6. Empty & Loading States

**Loading:** Existing `LoadingSpinner` centered (no change needed).

**No results:** Existing empty state with Activity icon (no change needed, already decent).

**Running state:** Hero banner shows "Running..." for duration, progress timeline animates the current step dot, step cards update in real-time via the existing 2-second polling.

## Backend Changes

### Add `acorns_used` to Execution response

File: `backend/executions.py`

Add to `Execution` Pydantic model:
```python
acorns_used: Optional[float] = None
```

In `get_latest_execution()` and `get_execution()`, compute the acorn cost from `AiUsageLog` entries (same approach used in `execute_workflow()` at line 1712):
```python
acorns_used = None
usage_logs = db.query(models.AiUsageLog).filter(
    models.AiUsageLog.execution_id == execution.id
).all()
total_cost_usd = sum(log.cost for log in usage_logs if hasattr(log, 'cost') and log.cost)
if total_cost_usd > 0:
    acorns_used = round(usd_to_acorns(total_cost_usd, db), 2)
```

### Frontend type update

Update `ExecutionResult` interface in `TestResultsModal.tsx`:
```typescript
interface ExecutionResult {
  // ... existing fields ...
  acorns_used?: number
}
```

## Files Modified

| File | Changes |
|------|---------|
| `frontend/src/components/processing/TestResultsModal.tsx` | Complete rewrite of render logic |
| `backend/executions.py` | Add `acorns_used` to Execution model and endpoint responses |

## Out of Scope

- Changing the modal trigger flow (PipelineSidebar "Test Full Process" button)
- Changing the execution polling mechanism (2-second refetchInterval stays)
- Historical execution browsing (only shows latest execution)
- Mobile responsiveness (modal is desktop-focused)
