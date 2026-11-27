"""Server-drawn SVG geometry for the semester GPA chart (no JavaScript, no chart library).

One series (each semester's GPA, as bars in the same order as the semester table) and one
reference line (overall CGPA). Semester order is the student's own order on the Semesters
page; the chart does not claim it is chronological.
"""
from decimal import Decimal

WIDTH, HEIGHT = 640, 260
LEFT, RIGHT, TOP, BOTTOM = 40, 72, 16, 44
PLOT_WIDTH, PLOT_HEIGHT = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
MAX_POINTS = Decimal(5)
LABEL_LIMIT = 14


def _y(value, top=MAX_POINTS):
    top = Decimal(top)
    return TOP + float((top - Decimal(value)) / top) * PLOT_HEIGHT


def _bar_path(x, y, width, base):
    """A bar with 4 px rounded top corners, square at the baseline."""
    radius = min(4.0, width / 2, max(base - y, 0))
    return (f"M{x:.1f},{base:.1f}V{y + radius:.1f}Q{x:.1f},{y:.1f} {x + radius:.1f},{y:.1f}"
            f"H{x + width - radius:.1f}Q{x + width:.1f},{y:.1f} {x + width:.1f},{y + radius:.1f}V{base:.1f}Z")


def semester_chart(summary, top=MAX_POINTS):
    """Geometry for the chart (0 to the scale's maximum), or None when no semester has a GPA yet."""
    rows = summary["semesters"]
    if not any(row["gpa"] is not None for row in rows):
        return None
    band = PLOT_WIDTH / len(rows)
    bar_width = min(56.0, band * 0.6)
    base = _y(0, top)
    bars = []
    for index, row in enumerate(rows):
        centre = LEFT + band * index + band / 2
        label = row["label"] if len(row["label"]) <= LABEL_LIMIT else row["label"][:LABEL_LIMIT - 1] + "…"
        bar = {"label": label, "full_label": row["label"], "centre": round(centre, 1), "gpa": row["gpa"]}
        if row["gpa"] is not None:
            height = _y(row["gpa"], top)
            bar["path"] = _bar_path(centre - bar_width / 2, height, bar_width, base)
            bar["hit"] = {"x": round(centre - band / 2, 1), "width": round(band, 1)}
        bars.append(bar)
    cgpa = summary["gpa"]
    return {
        "width": WIDTH, "height": HEIGHT, "left": LEFT, "right": WIDTH - RIGHT, "top": TOP, "base": round(base, 1),
        "plot_height": PLOT_HEIGHT, "label_y": HEIGHT - BOTTOM + 18,
        "ticks": [{"value": n, "y": round(_y(n, top), 1)} for n in range(int(top) + 1)],
        "bars": bars, "show_labels": len(rows) <= 8,
        "cgpa": None if cgpa is None else {"value": cgpa, "y": round(_y(cgpa, top), 1)},
    }
