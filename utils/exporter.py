"""Grid building + CSV / Excel export (shared by the UI and the downloads)."""
import io
import re
from collections import defaultdict
from typing import Any, Dict, List

import pandas as pd

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def schedule_to_dataframe(schedule: List[Dict[str, Any]], dataset: Dict[str, Any]) -> pd.DataFrame:
    names = {s["code"]: s["name"] for s in dataset["subjects"]}
    rows = [{"Class": s["class_name"], "Subject Code": s["subject_code"],
             "Subject": names.get(s["subject_code"], ""), "Teacher": s["teacher_name"],
             "Room": s["room_name"], "Day": DAY_NAMES[s["day"]], "Period": s["period"] + 1}
            for s in schedule]
    df = pd.DataFrame(rows, columns=["Class", "Subject Code", "Subject", "Teacher", "Room", "Day", "Period"])
    order = {d: i for i, d in enumerate(DAY_NAMES)}
    return df.sort_values(["Class", "Day", "Period"], key=lambda c: c.map(order) if c.name == "Day" else c) \
             .reset_index(drop=True) if len(df) else df


def _match(s, kind, name):
    return s[{"class": "class_name", "teacher": "teacher_name", "room": "room_name"}[kind]] == name


def describe(s: Dict[str, Any], kind: str) -> str:
    if kind == "class":
        return f"{s['subject_code']} | {s['teacher_name']} | {s['room_name']}"
    if kind == "teacher":
        return f"{s['class_name']} | {s['subject_code']} | {s['room_name']}"
    return f"{s['class_name']} | {s['subject_code']} | {s['teacher_name']}"


def grid_cells(schedule, kind: str, name: str):
    """(day, period) -> [(session_index, session)]"""
    cells = defaultdict(list)
    for i, s in enumerate(schedule):
        if _match(s, kind, name):
            cells[(s["day"], s["period"])].append((i, s))
    return cells


def grid_dataframe(schedule, dataset, kind: str, name: str) -> pd.DataFrame:
    ts = dataset["time_structure"]
    cells = grid_cells(schedule, kind, name)
    lunch = next((c["lunch_break_slot"] for c in dataset["classes"] if c["name"] == name), None) \
        if kind == "class" else None
    data = {}
    for p in range(ts["periods_per_day"]):
        col = []
        for d in range(ts["working_days"]):
            if lunch == p:
                col.append("LUNCH")
            else:
                col.append(" / ".join(describe(s, kind) for _, s in cells.get((d, p), [])))
        data[f"Period {p + 1}"] = col
    return pd.DataFrame(data, index=DAY_NAMES[:ts["working_days"]])


def to_csv_bytes(schedule, dataset) -> bytes:
    return schedule_to_dataframe(schedule, dataset).to_csv(index=False).encode("utf-8")


def _sheet(name: str, used: set) -> str:
    base = re.sub(r"[\[\]\*\?/\\:]", "-", name)[:31]
    out, k = base, 2
    while out in used:
        out = f"{base[:28]}~{k}"
        k += 1
    used.add(out)
    return out


def to_excel_bytes(schedule, dataset) -> bytes:
    buf, used = io.BytesIO(), set()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        schedule_to_dataframe(schedule, dataset).to_excel(xw, sheet_name=_sheet("All Sessions", used), index=False)
        for kind, key, prefix in (("class", "classes", "Class"), ("teacher", "teachers", "Teacher"),
                                  ("room", "rooms", "Room")):
            for item in dataset[key]:
                grid_dataframe(schedule, dataset, kind, item["name"]).to_excel(
                    xw, sheet_name=_sheet(f"{prefix} {item['name']}", used))
    return buf.getvalue()
