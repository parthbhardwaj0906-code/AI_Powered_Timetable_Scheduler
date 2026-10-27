"""HTML/CSS building blocks for the Streamlit UI."""
import html
from typing import Dict

from utils.exporter import DAY_NAMES, grid_cells

CSS = """
<style>
.hero{background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 55%,#0ea5e9 100%);border-radius:16px;padding:26px 30px;
      color:#fff;margin-bottom:18px;box-shadow:0 10px 30px -12px rgba(79,70,229,.55)}
.hero h1{margin:0;font-size:1.7rem;font-weight:700;color:#fff;padding:0}
.hero p{margin:6px 0 0 0;opacity:.88;font-size:.95rem}
.kpi{border:1px solid rgba(128,128,128,.25);border-left:5px solid #6366f1;border-radius:12px;padding:12px 16px;
     background:rgba(128,128,128,.07)}
.kpi .l{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;opacity:.7}
.kpi .v{font-size:1.35rem;font-weight:700;margin-top:2px}
.kpi.ok{border-left-color:#10b981}.kpi.bad{border-left-color:#ef4444}.kpi.warn{border-left-color:#f59e0b}
.badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.75rem;font-weight:600;margin:2px 4px 2px 0}
.badge.red{background:rgba(239,68,68,.15);color:#dc2626;border:1px solid rgba(239,68,68,.4)}
.badge.green{background:rgba(16,185,129,.15);color:#059669;border:1px solid rgba(16,185,129,.4)}
.badge.amber{background:rgba(245,158,11,.15);color:#b45309;border:1px solid rgba(245,158,11,.4)}
table.tt{border-collapse:separate;border-spacing:6px;width:100%;table-layout:fixed}
table.tt th{font-size:.78rem;text-align:center;opacity:.75;font-weight:600;padding:4px}
table.tt th.day{text-align:right;width:96px;padding-right:8px}
table.tt td{vertical-align:top;border-radius:10px;min-height:64px;height:64px;padding:0;
            background:rgba(128,128,128,.06);border:1px dashed rgba(128,128,128,.2)}
table.tt td.lunch{background:repeating-linear-gradient(45deg,rgba(245,158,11,.12),rgba(245,158,11,.12) 8px,
            rgba(245,158,11,.05) 8px,rgba(245,158,11,.05) 16px);text-align:center;vertical-align:middle;
            font-size:.75rem;font-weight:600;color:#b45309;border:1px solid rgba(245,158,11,.35)}
.chip{border-radius:9px;padding:6px 8px;font-size:.78rem;line-height:1.25;margin:2px;border-left:5px solid #6366f1}
.chip b{font-size:.84rem}.chip small{display:block;opacity:.8}
.chip.lab{border-left-style:double}
.chip.conflict{outline:2px solid #ef4444;box-shadow:0 0 0 3px rgba(239,68,68,.25)}
</style>
"""

PALETTE = [(99, 102, 241), (14, 165, 233), (16, 185, 129), (245, 158, 11), (236, 72, 153),
           (139, 92, 246), (20, 184, 166), (234, 88, 12), (101, 163, 13), (225, 29, 72)]


def kpi(label: str, value: str, tone: str = "") -> str:
    return f'<div class="kpi {tone}"><div class="l">{html.escape(label)}</div><div class="v">{html.escape(str(value))}</div></div>'


def badge(text: str, tone: str = "red") -> str:
    return f'<span class="badge {tone}">{html.escape(text)}</span>'


def render_grid(schedule, dataset: Dict, kind: str, name: str, conflicts=frozenset()) -> str:
    ts = dataset["time_structure"]
    subjects = {s["code"]: s for s in dataset["subjects"]}
    colour = {code: PALETTE[i % len(PALETTE)] for i, code in enumerate(sorted(subjects))}
    cells = grid_cells(schedule, kind, name)
    lunch = next((c["lunch_break_slot"] for c in dataset["classes"] if c["name"] == name), None) \
        if kind == "class" else None

    head = "".join(f"<th>Period {p + 1}</th>" for p in range(ts["periods_per_day"]))
    rows = []
    for d in range(ts["working_days"]):
        tds = []
        for p in range(ts["periods_per_day"]):
            if lunch == p:
                tds.append('<td class="lunch">LUNCH</td>')
                continue
            chips = []
            for idx, s in cells.get((d, p), []):
                r, g, b = colour.get(s["subject_code"], (99, 102, 241))
                cls = "chip" + (" lab" if subjects[s["subject_code"]]["type"] == "lab" else "") \
                      + (" conflict" if idx in conflicts else "")
                if kind == "class":
                    l1, l2 = s["subject_code"], f"{s['teacher_name']} · {s['room_name']}"
                elif kind == "teacher":
                    l1, l2 = s["subject_code"], f"{s['class_name']} · {s['room_name']}"
                else:
                    l1, l2 = s["subject_code"], f"{s['class_name']} · {s['teacher_name']}"
                chips.append(f'<div class="{cls}" style="background:rgba({r},{g},{b},.16);border-left-color:rgb({r},{g},{b})">'
                             f'<b>{html.escape(l1)}</b><small>{html.escape(l2)}</small></div>')
            tds.append(f"<td>{''.join(chips)}</td>")
        rows.append(f'<tr><th class="day">{DAY_NAMES[d]}</th>{"".join(tds)}</tr>')
    return f'<table class="tt"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
