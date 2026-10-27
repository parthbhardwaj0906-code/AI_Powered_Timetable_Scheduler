"""
Single place where the CSP is built, so every solver shares identical variables/domains.

Variable : one weekly session of a (class, subject).
Value    : (day, period, room, teacher).
Domain   : only values that already satisfy the unary hard constraints
           (teacher qualified + available, room type + capacity, not the class lunch slot).
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

Value = Tuple[int, int, str, str]
ROOM_FOR = {"theory": "classroom", "lab": "lab"}   # subject type -> required room type


@dataclass(frozen=True)
class Variable:
    id: int
    class_name: str
    subject_code: str
    session_index: int
    is_lab: bool


class Problem:
    def __init__(self, dataset: Dict[str, Any]):
        ts = dataset["time_structure"]
        self.dataset = dataset
        self.days = ts["working_days"]
        self.periods = ts["periods_per_day"]
        self.subjects = {s["code"]: s for s in dataset["subjects"]}
        self.teachers = {t["name"]: t for t in dataset["teachers"]}
        self.classes = {c["name"]: c for c in dataset["classes"]}
        self.rooms = {r["name"]: r for r in dataset["rooms"]}
        self.max_load = {n: t["max_weekly_load"] for n, t in self.teachers.items()}
        self.breaks = set(ts.get("break_periods", []))

        self.variables: List[Variable] = []
        self.domains: Dict[int, List[Value]] = {}
        self.siblings: Dict[Tuple[str, str], List[int]] = defaultdict(list)  # (class, subject) -> var ids
        self.class_vars: Dict[str, List[int]] = defaultdict(list)
        self.empty_domain_vars: List[int] = []
        self._build()

    def _build(self):
        qualified = defaultdict(list)
        for tn, td in self.teachers.items():
            for sc in td["subjects"]:
                qualified[sc].append(tn)
        unavail = {tn: {(u["day"], u["period"]) for u in td.get("unavailable_slots", [])}
                   for tn, td in self.teachers.items()}

        vid = 0
        for cn, cd in self.classes.items():
            lunch = cd["lunch_break_slot"]
            for sc in cd["subjects"]:
                sub = self.subjects[sc]
                rooms = [r["name"] for r in self.rooms.values()
                         if r["type"] == ROOM_FOR[sub["type"]] and r["capacity"] >= cd["strength"]]
                teachers = qualified.get(sc, [])
                for h in range(sub["weekly_hours"]):
                    var = Variable(vid, cn, sc, h, sub["type"] == "lab")
                    dom = [(d, p, r, t)
                           for d in range(self.days) for p in range(self.periods) if p != lunch and p not in self.breaks
                           for r in rooms for t in teachers if (d, p) not in unavail[t]]
                    self.variables.append(var)
                    self.domains[vid] = dom
                    self.siblings[(cn, sc)].append(vid)
                    self.class_vars[cn].append(vid)
                    if not dom:
                        self.empty_domain_vars.append(vid)
                    vid += 1

    # ---- conversions -------------------------------------------------
    def to_schedule(self, assignment: Dict[int, Value]) -> List[Dict[str, Any]]:
        out = []
        for v in sorted(assignment):
            var = self.variables[v]
            d, p, r, t = assignment[v]
            out.append({"class_name": var.class_name, "subject_code": var.subject_code,
                        "teacher_name": t, "room_name": r, "day": d, "period": p})
        return out

    def values_from_schedule(self, schedule: List[Dict[str, Any]]) -> Optional[Dict[int, Value]]:
        queues = {k: list(ids) for k, ids in self.siblings.items()}
        out = {}
        for s in schedule:
            q = queues.get((s["class_name"], s["subject_code"]))
            if not q:
                return None
            out[q.pop(0)] = (s["day"], s["period"], s["room_name"], s["teacher_name"])
        return out

    def explain_empty(self, v: int) -> str:
        var = self.variables[v]
        sub = self.subjects[var.subject_code]
        cd = self.classes[var.class_name]
        teachers = [t for t, td in self.teachers.items() if var.subject_code in td["subjects"]]
        rooms = [r for r in self.rooms.values()
                 if r["type"] == ROOM_FOR[sub["type"]] and r["capacity"] >= cd["strength"]]
        if not teachers:
            return f"{var.class_name}/{var.subject_code}: no teacher is qualified for this subject"
        if not rooms:
            return (f"{var.class_name}/{var.subject_code}: no {ROOM_FOR[sub['type']]} with capacity "
                    f">= {cd['strength']}")
        return f"{var.class_name}/{var.subject_code}: every slot is blocked by teacher availability"


def check_dataset(dataset: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Pre-flight sanity checks (run before heavy solvers). Returns (errors, warnings)."""
    P = Problem(dataset)
    errors, warnings = [], []
    seen = set()
    for v in P.empty_domain_vars:
        msg = P.explain_empty(v)
        if msg not in seen:
            seen.add(msg)
            errors.append(msg)

    common_lunch = set.intersection(*[{c["lunch_break_slot"]} for c in P.classes.values()]) if P.classes else set()
    blocked_for_all = P.breaks | common_lunch                     # periods no room can ever be used in
    demand_by_type = {"theory": 0, "lab": 0}
    demand_by_subject = defaultdict(int)
    for cn, cd in P.classes.items():
        hours = sum(P.subjects[s]["weekly_hours"] for s in cd["subjects"])
        usable_slots = P.days * (P.periods - len(P.breaks | {cd["lunch_break_slot"]}))
        if hours > usable_slots:
            errors.append(f"Class {cn} needs {hours} sessions but only {usable_slots} non-lunch/break slots exist")
        for s in cd["subjects"]:
            h = P.subjects[s]["weekly_hours"]
            demand_by_type[P.subjects[s]["type"]] += h
            demand_by_subject[s] += h

    for stype, room_type in ROOM_FOR.items():
        supply = sum(1 for r in P.rooms.values() if r["type"] == room_type) * P.days * (P.periods - len(blocked_for_all))
        if demand_by_type[stype] > supply:
            errors.append(f"{stype} sessions needed ({demand_by_type[stype]}) exceed total {room_type} "
                          f"available room-slots ({supply})")

    for s, hours in demand_by_subject.items():
        cap = sum(td["max_weekly_load"] for td in P.teachers.values() if s in td["subjects"])
        if cap and hours > cap:
            errors.append(f"Subject {s} needs {hours} hours but qualified teachers can give at most {cap}")

    total_cap = sum(td["max_weekly_load"] for td in P.teachers.values())
    total_dem = sum(demand_by_subject.values())
    if total_dem > total_cap:
        errors.append(f"Total demand {total_dem} exceeds total teacher capacity {total_cap}")
    elif total_dem > 0.85 * total_cap:
        warnings.append(f"Teacher capacity is tight ({total_dem}/{total_cap} hours): expect harder search")
    return errors, warnings
