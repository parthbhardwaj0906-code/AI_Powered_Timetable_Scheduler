"""
Min-Conflicts local search on a COMPLETE (initially random, conflicting) assignment.

Each iteration: pick a random conflicted session, give it the value with the fewest hard conflicts
(ties broken by a cheap soft-quality heuristic, then randomly). Plateau escape:
  * random walk  - with probability `random_walk_prob` move to a random value
  * random restart - after `restart_after` iterations without a new best cost
Progress, the goal test and the cost history all come from the unified validator.
"""
import random
import time
from collections import defaultdict

from engine.problem import Problem
from engine.result import SolverResult
from engine.validator import TimetableValidator


class MinConflictsSolver:
    name = "Min-Conflicts"

    def __init__(self, dataset, max_iterations=20000, random_walk_prob=0.05, restart_after=2500,
                 seed=None, time_limit=60.0):
        self.dataset = dataset
        self.max_iterations, self.p_walk, self.restart_after = max_iterations, random_walk_prob, restart_after
        self.seed, self.time_limit = seed, time_limit

    def solve(self) -> SolverResult:
        t0 = time.perf_counter()
        P = Problem(self.dataset)
        validator = TimetableValidator(self.dataset)
        rng = random.Random(self.seed)

        if P.empty_domain_vars:
            msgs = sorted({P.explain_empty(v) for v in P.empty_domain_vars})
            return SolverResult(self.name, False, [], message="Unsatisfiable: " + "; ".join(msgs[:3]))

        n = len(P.variables)
        cls = [v.class_name for v in P.variables]
        sub = [v.subject_code for v in P.variables]
        max_load = P.max_load
        val = {}
        c_occ, t_occ, r_occ = defaultdict(int), defaultdict(int), defaultdict(int)
        load, cday, sday = defaultdict(int), defaultdict(int), defaultdict(int)

        def add(v, x):
            d, p, r, t = x
            val[v] = x
            c_occ[(cls[v], d, p)] += 1; t_occ[(t, d, p)] += 1; r_occ[(r, d, p)] += 1
            load[t] += 1; cday[(cls[v], d)] += 1; sday[(cls[v], sub[v], d)] += 1

        def remove(v):
            d, p, r, t = val.pop(v)
            c_occ[(cls[v], d, p)] -= 1; t_occ[(t, d, p)] -= 1; r_occ[(r, d, p)] -= 1
            load[t] -= 1; cday[(cls[v], d)] -= 1; sday[(cls[v], sub[v], d)] -= 1

        def randomize_all():
            for v in list(val):
                remove(v)
            for v in range(n):
                add(v, rng.choice(P.domains[v]))

        def conflicted():
            out = []
            for v, (d, p, r, t) in val.items():
                if (c_occ[(cls[v], d, p)] > 1 or t_occ[(t, d, p)] > 1 or r_occ[(r, d, p)] > 1
                        or load[t] > max_load[t]):
                    out.append(v)
            return out

        randomize_all()
        history, best_cost, best_vals, last_improve, restarts = [], float("inf"), dict(val), 0, 0
        iterations = 0
        for it in range(self.max_iterations):
            iterations = it
            ev = validator.evaluate(P.to_schedule(val))
            cost = ev["total_cost"]
            history.append(cost)
            if cost < best_cost:
                best_cost, best_vals, last_improve = cost, dict(val), it
            if ev["is_feasible"]:
                return SolverResult(self.name, True, P.to_schedule(val), nodes=it, elapsed=time.perf_counter() - t0,
                                    cost_history=history, message="Feasible schedule found",
                                    extra={"restarts": restarts})
            if time.perf_counter() - t0 > self.time_limit:
                break
            if it - last_improve > self.restart_after:       # plateau escape: random restart
                randomize_all()
                restarts += 1
                last_improve = it
                continue

            conf = conflicted() or list(range(n))
            v = rng.choice(conf)
            old = val[v]
            remove(v)
            if rng.random() < self.p_walk:                    # plateau escape: random walk
                add(v, rng.choice(P.domains[v]))
                continue
            c = cls[v]
            best_key, best_x = None, []
            for x in P.domains[v]:
                d, p, r, t = x
                n_conf = (c_occ.get((c, d, p), 0) + t_occ.get((t, d, p), 0) + r_occ.get((r, d, p), 0)
                          + (1 if load[t] >= max_load[t] else 0))
                if best_key is not None and n_conf > best_key[0]:
                    continue
                k = (n_conf, cday.get((c, d), 0) + 2 * sday.get((c, sub[v], d), 0))
                if best_key is None or k < best_key:
                    best_key, best_x = k, [x]
                elif k == best_key:
                    best_x.append(x)
            add(v, rng.choice(best_x) if best_x else old)

        sched = P.to_schedule(best_vals)
        return SolverResult(self.name, False, sched, nodes=iterations, elapsed=time.perf_counter() - t0,
                            cost_history=history,
                            message=f"No feasible schedule within limits (best cost {best_cost})",
                            extra={"restarts": restarts})
