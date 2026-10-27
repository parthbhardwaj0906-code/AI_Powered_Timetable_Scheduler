"""
Regenerates data/small_dataset.json and data/large_dataset.json.

Fields follow the assignment spec exactly:
  Subjects : code, name, weekly hours, type (theory/lab)
  Teachers : name, subjects they can teach, unavailable slots, maximum weekly load
  Classes  : name, strength, list of subjects, lunch break slot
  Rooms    : name, capacity, type (classroom/lab)
  Time     : working days, periods per day, break period(s)

Teacher loads are not typed by hand. We first PLANT an explicit hour allocation (the hours of each subject
are balanced between the teachers who can teach it), then set every teacher's maximum weekly load just
above their planted hours (ceil(planted * slack)). Capacity is therefore tight (~85-90% used) and every
teacher is genuinely needed, while the data stays solvable.
"""
import json
import math
from collections import defaultdict


def S(day, period):
    return {"day": day, "period": period}


def whole_day(day, periods):
    return [S(day, p) for p in range(periods)]


def build(time_structure, subjects, classes, teachers, rooms, slack, extra=0):
    hours = {s[0]: s[2] for s in subjects}
    demand = defaultdict(int)
    for c in classes:
        for code in c[2]:
            demand[code] += hours[code]
    teachers_of = defaultdict(list)
    for t in teachers:
        for code in t[1]:
            teachers_of[code].append(t[0])
    planted = defaultdict(int)
    for code in sorted(demand, key=lambda c: (len(teachers_of[c]), c)):      # scarce subjects first
        for _ in range(demand[code]):
            name = min(teachers_of[code], key=lambda n: (planted[n], n))
            planted[name] += 1
    return {
        "time_structure": time_structure,
        "subjects": [{"code": c, "name": n, "weekly_hours": h, "type": t} for c, n, h, t in subjects],
        "teachers": [{"name": name, "subjects": subs, "unavailable_slots": unavail,
                      "max_weekly_load": math.ceil(planted[name] * slack) + extra} for name, subs, unavail in teachers],
        "classes": [{"name": n, "strength": st, "subjects": subs, "lunch_break_slot": 3} for n, st, subs in classes],
        "rooms": [{"name": n, "capacity": cap, "type": t} for n, cap, t in rooms]}


# ---------------------------------------------------- SMALL: 3 classes, 6 teachers, 4 rooms, 5 days x 6 periods
small = build(
    {"working_days": 5, "periods_per_day": 6, "break_periods": [3]},
    subjects=[("CS301", "Data Structures", 4, "theory"), ("CS302", "Data Structures Lab", 2, "lab"),
              ("MA301", "Discrete Mathematics", 3, "theory"), ("CS303", "Database Systems", 3, "theory"),
              ("CS304", "DBMS Lab", 2, "lab"), ("HS301", "Technical Communication", 2, "theory")],
    classes=[("CSE-A", 60, ["CS301", "CS302", "MA301", "CS303", "HS301"]),
             ("CSE-B", 55, ["CS301", "MA301", "CS303", "CS304", "HS301"]),
             ("AI-A", 50, ["CS301", "CS302", "MA301", "CS304", "HS301"])],
    teachers=[("Dr. Anita Sharma", ["CS301", "CS302"], []),
              ("Prof. Rohit Iyer", ["CS301"], [S(4, 5)]),
              ("Dr. Rajesh Verma", ["MA301"], [S(0, 0)]),
              ("Dr. Suresh Menon", ["CS303", "CS304"], [S(2, 0)]),
              ("Prof. Kiran Rao", ["CS303", "CS304"], []),
              ("Ms. Neha Kulkarni", ["HS301"], [S(4, 4), S(4, 5)])],
    rooms=[("CR-201", 65, "classroom"), ("CR-202", 60, "classroom"),
           ("Lab-1", 65, "lab"), ("Lab-2", 55, "lab")],
    slack=1.12)

# ---------------------------------------------------- LARGE: 8 classes, 16 teachers, 8 rooms, 5 days x 7 periods
large = build(
    {"working_days": 5, "periods_per_day": 7, "break_periods": [3]},
    subjects=[("CS301", "Data Structures", 4, "theory"), ("CS303", "Database Systems", 3, "theory"),
              ("CS305", "Operating Systems", 4, "theory"), ("CS307", "Computer Networks", 3, "theory"),
              ("AI301", "Machine Learning", 4, "theory"), ("AI303", "Deep Learning", 3, "theory"),
              ("EC301", "Digital Signal Processing", 4, "theory"), ("EC303", "Analog Circuits", 3, "theory"),
              ("MA301", "Probability and Statistics", 3, "theory"), ("MA303", "Discrete Mathematics", 3, "theory"),
              ("HS301", "Professional Ethics", 2, "theory"),
              ("CS302", "Data Structures Lab", 2, "lab"), ("CS304", "DBMS Lab", 2, "lab"),
              ("CS306", "Operating Systems Lab", 2, "lab"), ("AI302", "Machine Learning Lab", 2, "lab"),
              ("EC302", "DSP Lab", 2, "lab")],
    classes=[("CSE-A", 62, ["CS301", "CS303", "CS305", "MA303", "HS301", "CS302", "CS304"]),
             ("CSE-B", 58, ["CS301", "CS303", "CS307", "MA303", "HS301", "CS302", "CS306"]),
             ("IT-A", 56, ["CS301", "CS305", "CS307", "MA301", "HS301", "CS304", "CS306"]),
             ("IT-B", 54, ["CS303", "CS305", "CS307", "MA301", "HS301", "CS302", "CS304"]),
             ("AIDS-A", 55, ["AI301", "CS301", "MA301", "MA303", "HS301", "AI302", "CS302"]),
             ("AIDS-B", 52, ["AI301", "AI303", "CS303", "MA301", "HS301", "AI302", "CS304"]),
             ("ECE-A", 62, ["EC301", "EC303", "MA301", "CS307", "HS301", "EC302", "CS306"]),
             ("ECE-B", 60, ["EC301", "EC303", "MA303", "CS305", "HS301", "EC302", "CS306"])],
    teachers=[("Dr. Anita Sharma", ["CS301", "CS302"], []),
              ("Prof. Rohit Iyer", ["CS301"], [S(0, 0)]),
              ("Dr. Meera Nair", ["CS303", "CS304"], [S(2, 6)]),
              ("Prof. Kiran Rao", ["CS303"], [S(0, 0), S(0, 1)]),
              ("Dr. Suresh Menon", ["CS305", "CS306"], []),
              ("Prof. Neha Kulkarni", ["CS305"], [S(3, 6)]),
              ("Dr. Arjun Patel", ["CS307"], [S(1, 0)]),
              ("Prof. Deepa Joshi", ["CS307", "CS306"], []),
              ("Dr. Vikram Bose", ["AI301", "AI302"], [S(0, 0)]),
              ("Prof. Lakshmi Reddy", ["AI301", "AI303"], [S(1, 0), S(1, 1)]),
              ("Dr. Farhan Ali", ["EC301", "EC302"], [S(4, 6)]),
              ("Prof. Sunita Das", ["EC301", "EC303"], []),
              ("Dr. Rajesh Verma", ["MA303", "HS301"], [S(4, 5), S(4, 6)]),
              ("Prof. Pooja Mishra", ["MA301"], []),
              ("Dr. Kavita Singh", ["MA303", "HS301"], [S(2, 0)]),
              ("Prof. Anil Kapoor", ["HS301", "EC303"], whole_day(0, 7) + whole_day(4, 7))],
    rooms=[("CR-301", 65, "classroom"), ("CR-302", 65, "classroom"), ("CR-303", 60, "classroom"),
           ("CR-304", 58, "classroom"), ("CR-305", 56, "classroom"),
           ("Lab-1", 65, "lab"), ("Lab-2", 60, "lab"), ("Lab-3", 56, "lab")],
    slack=1.1, extra=1)   # one spare hour per teacher: tight, but not so tight that search thrashes

if __name__ == "__main__":
    for name, ds in (("small", small), ("large", large)):
        with open(f"data/{name}_dataset.json", "w") as f:
            json.dump(ds, f, indent=2)
    print("written")
