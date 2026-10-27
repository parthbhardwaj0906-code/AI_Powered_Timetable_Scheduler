"""
Backtracking CSP solver.

Switches let the benchmark compare a plain baseline with the improved search:
  use_mrv                 Minimum Remaining Values variable ordering
  use_degree              Degree heuristic (tie-break for MRV; static ordering when MRV is off)
  use_forward_checking    prune neighbour domains after every assignment (+ teacher-load pruning)
  symmetry_breaking       sessions of the same (class, subject) are interchangeable -> force
                          them into increasing slot order
  value_ordering          LCV-style: prefer days where the class is lightest / labs back-to-back
"""
import random
import sys
import time
from collections import defaultdict

from engine.problem import Problem
from engine.result import SolverResult


class _Timeout(Exception):
    pass


class BacktrackingCSPSolver:
    def __init__(self, dataset, use_mrv=True, use_degree=True, use_forward_checking=True,
                 symmetry_breaking=True, value_ordering=True, randomize=False, seed=None,
                 time_limit=30.0, name=None):
        self.dataset = dataset
        self.use_mrv, self.use_degree = use_mrv, use_degree
        self.use_fc, self.sym, self.value_ordering = use_forward_checking, symmetry_breaking, value_ordering
        self.randomize, self.seed, self.time_limit = randomize, seed, time_limit
        self.name = name or ("Backtracking (MRV + Degree + FC)" if use_forward_checking
                             else "Backtracking (plain baseline)")

    def solve(self) -> SolverResult:
        t0 = time.perf_counter()
        P = Problem(self.dataset)
        n = len(P.variables)
        rng = random.Random(self.seed)
        sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))

        if n == 0:
            return SolverResult(self.name, False, [], message="Dataset has no sessions to schedule")
        if P.empty_domain_vars:
            msgs = sorted({P.explain_empty(v) for v in P.empty_domain_vars})
            return SolverResult(self.name, False, [], elapsed=time.perf_counter() - t0,
                                message="Unsatisfiable: " + "; ".join(msgs[:3]))

        cls = [v.class_name for v in P.variables]
        key = [(v.class_name, v.subject_code) for v in P.variables]
        max_load = P.max_load
        dom, size = [], []
        for v in range(n):
            d = {}
            for (dd, pp, r, t) in P.domains[v]:
                d.setdefault((dd, pp), set()).add((r, t))
            dom.append(d)
            size.append(len(P.domains[v]))
        teachers_of = [{x[3] for x in P.domains[v]} for v in range(n)]
        degree = [sum(1 for b in range(n) if b != a and (cls[a] == cls[b] or teachers_of[a] & teachers_of[b]))
                  for a in range(n)]
        sibs = [[u for u in P.siblings[key[v]] if u != v] for v in range(n)]

        assignment = {}
        class_busy, teacher_busy, room_busy = set(), set(), set()
        load = defaultdict(int)
        cday, sday = defaultdict(int), defaultdict(int)
        nodes = [0]

        def consistent(v, val):
            d, p, r, t = val
            if (cls[v], d, p) in class_busy or (t, d, p) in teacher_busy or (r, d, p) in room_busy:
                return False
            if load[t] >= max_load[t]:
                return False
            if self.sym:
                for u in sibs[v]:
                    a = assignment.get(u)
                    if a is not None:
                        if u > v and (a[0], a[1]) <= (d, p):
                            return False
                        if u < v and (a[0], a[1]) >= (d, p):
                            return False
            return True

        def place(v, val):
            d, p, r, t = val
            assignment[v] = val
            class_busy.add((cls[v], d, p)); teacher_busy.add((t, d, p)); room_busy.add((r, d, p))
            load[t] += 1; cday[(cls[v], d)] += 1; sday[(cls[v], key[v][1], d)] += 1
            nodes[0] += 1

        def unplace(v, val):
            d, p, r, t = val
            del assignment[v]
            class_busy.discard((cls[v], d, p)); teacher_busy.discard((t, d, p)); room_busy.discard((r, d, p))
            load[t] -= 1; cday[(cls[v], d)] -= 1; sday[(cls[v], key[v][1], d)] -= 1

        def prune(v, val, un):
            d, p, r, t = val
            slot, c, trail = (d, p), cls[v], []
            for u in un:
                if u == v:
                    continue
                s = dom[u].get(slot)
                if s:
                    rem = set(s) if cls[u] == c else {x for x in s if x[0] == r or x[1] == t}
                    if rem:
                        s -= rem
                        trail.append((u, slot, rem))
                        size[u] -= len(rem)
                        if size[u] == 0:
                            return False, trail
            if self.sym:
                for u in sibs[v]:
                    if u in assignment:
                        continue
                    for sl, s in dom[u].items():
                        if s and ((u > v and sl <= slot) or (u < v and sl >= slot)):
                            rem = set(s)
                            s.clear()
                            trail.append((u, sl, rem))
                            size[u] -= len(rem)
                    if size[u] == 0:
                        return False, trail
            if load[t] >= max_load[t]:                      # teacher is full: remove him everywhere
                for u in un:
                    if u == v:
                        continue
                    for sl, s in dom[u].items():
                        if s:
                            rem = {x for x in s if x[1] == t}
                            if rem:
                                s -= rem
                                trail.append((u, sl, rem))
                                size[u] -= len(rem)
                    if size[u] == 0:
                        return False, trail
            return True, trail

        def restore(trail):
            for u, sl, rem in reversed(trail):
                dom[u][sl] |= rem
                size[u] += len(rem)

        def select(un):
            if self.use_mrv:
                return min(un, key=lambda u: (size[u], -degree[u] if self.use_degree else 0, u))
            if self.use_degree:
                return max(un, key=lambda u: (degree[u], -u))
            return un[0]

        def ordered_values(v):
            slots = [s for s, vals in dom[v].items() if vals]
            if self.randomize:
                rng.shuffle(slots)
            else:
                slots.sort()
            if self.value_ordering:
                c, sc, lab = cls[v], key[v][1], P.variables[v].is_lab

                def skey(s):
                    d, p = s
                    if lab:
                        adj = any(assignment[u][0] == d and abs(assignment[u][1] - p) == 1
                                  for u in sibs[v] if u in assignment)
                        return (0 if adj else 1, cday[(c, d)])
                    return (sday[(c, sc, d)], cday[(c, d)])
                slots.sort(key=skey)
            for s in slots:
                vals = list(dom[v][s])
                if self.randomize:
                    rng.shuffle(vals)
                else:
                    vals.sort()
                if self.value_ordering:
                    vals.sort(key=lambda x: load[x[1]])
                for (r, t) in vals:
                    yield (s[0], s[1], r, t)

        def search():
            if len(assignment) == n:
                return True
            un = [u for u in range(n) if u not in assignment]
            v = select(un)
            for val in ordered_values(v):
                if time.perf_counter() - t0 > self.time_limit:
                    raise _Timeout()
                if not consistent(v, val):
                    continue
                place(v, val)
                ok, trail = True, []
                if self.use_fc:
                    ok, trail = prune(v, val, un)
                if ok and search():
                    return True
                if self.use_fc:
                    restore(trail)
                unplace(v, val)
            return False

        try:
            found = search()
            msg = "Complete feasible schedule found" if found else "Search space exhausted: no feasible schedule exists"
        except _Timeout:
            found, msg = False, f"Timed out after {self.time_limit:.0f}s without finding a schedule"
        elapsed = time.perf_counter() - t0
        schedule = P.to_schedule(assignment) if found else []
        return SolverResult(self.name, found, schedule, nodes=nodes[0], elapsed=elapsed, message=msg)
