"""
Unified validator: the ONE place constraints are evaluated.
Used by Min-Conflicts, Simulated Annealing, the manual editor, the benchmarker and the export check.

    Cost = 1000 * (hard violations) + (soft penalties)

Hard: H1 teacher clash | H2 class clash | H3 room clash | H4 room capacity | H5 room type
      H6 teacher qualified & available | H7 exact weekly hours | H8 teacher max load | H9 lunch / break slot
Soft: S1 gaps | S2 same theory subject twice a day | S3 lab sessions not consecutive
      S4 teacher preference (no first-period class) | S5 teacher >2 consecutive periods
"""
from collections import defaultdict
from typing import Any, Dict, List

HARD_CODES = ["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9"]
SOFT_CODES = ["S1", "S2", "S3", "S4", "S5"]
HARD_WEIGHT = 1000


class TimetableValidator:
    def __init__(self, dataset: Dict[str, Any]):
        ts = dataset["time_structure"]
        self.days = ts["working_days"]
        self.periods = ts["periods_per_day"]
        self.subjects = {s["code"]: s for s in dataset["subjects"]}
        self.teachers = {t["name"]: t for t in dataset["teachers"]}
        self.classes = {c["name"]: c for c in dataset["classes"]}
        self.rooms = {r["name"]: r for r in dataset["rooms"]}
        self.unavail = {n: {(u["day"], u["period"]) for u in t.get("unavailable_slots", [])}
                        for n, t in self.teachers.items()}
        self.breaks = set(ts.get("break_periods", []))        # periods where nobody has class
        # S4 teacher preference: no first-period class (the PDF's example). `avoid_slots` is an optional
        # extension; the sample datasets do not use it.
        self.avoid = {n: {(u["day"], u["period"]) for u in t.get("avoid_slots", [])}
                      for n, t in self.teachers.items()}
        self.required = {(c["name"], sc): self.subjects[sc]["weekly_hours"]
                         for c in dataset["classes"] for sc in c["subjects"]}

    def evaluate(self, schedule: List[Dict[str, Any]], detail: bool = False) -> Dict[str, Any]:
        H = dict.fromkeys(HARD_CODES, 0)
        details: List[tuple] = []          # (code, message, [session indices])
        t_occ, c_occ, r_occ = defaultdict(list), defaultdict(list), defaultdict(list)
        cs_idx = defaultdict(list)
        t_idx = defaultdict(list)
        class_day = defaultdict(list)      # (class, day) -> [(period, subject)]
        teacher_day = defaultdict(list)    # (teacher, day) -> [period]
        S = dict.fromkeys(SOFT_CODES, 0)

        for i, s in enumerate(schedule):
            c, sc, t, r = s["class_name"], s["subject_code"], s["teacher_name"], s["room_name"]
            d, p = s["day"], s["period"]
            t_occ[(t, d, p)].append(i)
            c_occ[(c, d, p)].append(i)
            r_occ[(r, d, p)].append(i)
            cs_idx[(c, sc)].append(i)
            t_idx[t].append(i)
            class_day[(c, d)].append((p, sc))
            teacher_day[(t, d)].append(p)

            room, cls = self.rooms.get(r), self.classes.get(c)
            sub, tea = self.subjects.get(sc), self.teachers.get(t)
            if room and cls and room["capacity"] < cls["strength"]:
                H["H4"] += 1
                if detail:
                    details.append(("H4", f"{r} (cap {room['capacity']}) too small for {c} ({cls['strength']})", [i]))
            if sub and room and room["type"] != ("lab" if sub["type"] == "lab" else "classroom"):
                H["H5"] += 1
                if detail:
                    details.append(("H5", f"{sc} ({sub['type']}) cannot use {room['type']} {r}", [i]))
            if tea is None or sc not in tea["subjects"]:
                H["H6"] += 1
                if detail:
                    details.append(("H6", f"{t} is not qualified to teach {sc}", [i]))
            elif (d, p) in self.unavail[t]:
                H["H6"] += 1
                if detail:
                    details.append(("H6", f"{t} is unavailable on day {d + 1}, period {p + 1}", [i]))
            if cls and p == cls["lunch_break_slot"]:
                H["H9"] += 1
                if detail:
                    details.append(("H9", f"{c} has a session during its lunch slot (period {p + 1})", [i]))
            elif p in self.breaks:
                H["H9"] += 1
                if detail:
                    details.append(("H9", f"{c} has a session during a break period (period {p + 1})", [i]))
            if p == 0 or (d, p) in self.avoid.get(t, ()):
                S["S4"] += 2

        for code, occ, label in (("H1", t_occ, "teacher"), ("H2", c_occ, "class"), ("H3", r_occ, "room")):
            for (name, d, p), idxs in occ.items():
                if len(idxs) > 1:
                    H[code] += len(idxs) - 1
                    if detail:
                        details.append((code, f"{label} {name} double-booked on day {d + 1}, period {p + 1}", idxs))

        for key in set(self.required) | set(cs_idx):
            exp, act = self.required.get(key, 0), len(cs_idx.get(key, []))
            if exp != act:
                H["H7"] += abs(exp - act)
                if detail:
                    details.append(("H7", f"{key[0]} / {key[1]}: {act} sessions scheduled, {exp} required",
                                    cs_idx.get(key, [])))

        for t, idxs in t_idx.items():
            tea = self.teachers.get(t)
            if tea and len(idxs) > tea["max_weekly_load"]:
                H["H8"] += len(idxs) - tea["max_weekly_load"]
                if detail:
                    details.append(("H8", f"{t} has {len(idxs)} sessions (max {tea['max_weekly_load']})", idxs))

        # ---- soft constraints ----
        for (c, d), items in class_day.items():
            periods = sorted({p for p, _ in items})
            lunch = self.classes[c]["lunch_break_slot"] if c in self.classes else -1
            gaps = (periods[-1] - periods[0] + 1) - len(periods)
            if periods[0] < lunch < periods[-1] and lunch not in periods:
                gaps -= 1                                   # lunch inside the day is not a gap
            S["S1"] += max(0, gaps)
            counts = defaultdict(list)
            for p, sc in items:
                counts[sc].append(p)
            for sc, ps in counts.items():
                sub = self.subjects.get(sc)
                if not sub:
                    continue
                if sub["type"] != "lab" and len(ps) > 1:
                    S["S2"] += 2 * (len(ps) - 1)
                if sub["type"] == "lab" and sub["weekly_hours"] > 1:
                    pset = set(ps)
                    for p in pset:
                        if (p - 1) not in pset and (p + 1) not in pset:
                            S["S3"] += 3

        for (t, d), ps in teacher_day.items():
            ps = sorted(set(ps))
            run = 1
            for a, b in zip(ps, ps[1:] + [None]):
                if b is not None and b == a + 1:
                    run += 1
                else:
                    if run > 2:
                        S["S5"] += 2 * (run - 2)
                    run = 1

        hard = sum(H.values())
        soft = sum(S.values())
        out = {"hard_violations": hard, "soft_penalties": soft,
               "total_cost": HARD_WEIGHT * hard + soft, "is_feasible": hard == 0,
               "hard_breakdown": H, "soft_breakdown": S}
        if detail:
            out["details"] = details
            out["conflict_sessions"] = sorted({i for _, _, idxs in details for i in idxs})
        return out
