---
name: uni-command-center-redesign
description: Redesign plan for the UniCommand dashboard based on the Academic Studio design system.
metadata:
  type: project
---

# Redesign Plan: UniCommand Dashboard

I am redesigning the University Command Center (UniCommand) dashboard to align with the "Academic Studio" design system.

## Design Plan

### Token System
- **Color**:
  - `--color-canvas`: #F7F8F6 (Light), #101918 (Dark)
  - `--color-surface`: #FFFFFF (Light), #172321 (Dark)
  - `--color-primary`: #176B5B (Light), #87D4BD (Dark)
  - `--color-text`: #172A2A (Light), #F0F5F2 (Dark)
  - `--color-text-muted`: #536466 (Light), #B4C4BC (Dark)
  - `--color-border-subtle`: #D9E0DC (Light), #41584D (Dark)
- **Type**:
  - Use the system UI sans-serif stack: `system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif`.
  - Maintain a clear typographic scale: 32px title, 22px section heading, 16px body, 13px meta.
- **Layout**:
  - Sidebar navigation (15rem desktop) with main content (76rem max) centered.
  - Responsive stack for phones.
  - Spacing scale: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64px.

### Principles
- **Clarity over decoration**: Focus on alignment, whitespace, and typographic hierarchy.
- **Academic truth**: Ensure actual vs. hypothetical grades are distinct.
- **Trustworthy feedback**: Use semantic colors and clear labels for success/error/warning states.
- **Accessible**: Ensure focus visibility, keyboard navigation, and contrast compliance.

## Implementation Steps
1.  **Define CSS variables**: Add the semantic color and spacing tokens in `web_app.py` or a new CSS file.
2.  **Refactor Layout**: Update `web_app.py` structure to use a more modular component approach (PageHeader, Section, MetricCard).
3.  **Refine Dashboard**: Restructure the dashboard to highlight Actual CGPA, Upcoming Assignments, and Semester Performance clearly.
4.  **Polish Typography/Spacing**: Apply the new typographic and spacing scales across the pages.
5.  **Audit**: Ensure accessibility and responsiveness.

**Why:** The current dashboard uses default Streamlit components which feel templated. This redesign provides a distinctive, high-end dashboard interface that is more usable and trustworthy.
**How to apply:** Apply the design tokens and structural changes step-by-step, starting with the dashboard UI, ensuring all existing functionality remains intact.
