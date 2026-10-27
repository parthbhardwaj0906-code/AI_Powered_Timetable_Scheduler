"""Simulated Annealing and the Hybrid CSP + SA pipeline (bonus)."""
import math
import random
import time

from engine.backtracking import BacktrackingCSPSolver
from engine.min_conflicts import MinConflictsSolver
from engine.problem import Problem
from engine.result import SolverResult
from engine.validator import TimetableValidator


class SimulatedAnnealingOptimizer:
    name = "Simulated Annealing"

    def __init__(self, dataset, initial_temp=6.0, cooling_rate=0.95, stopping_temp=0.05,
                 iters_per_temp=150, seed=None, time_limit=60.0, initial_schedule=None):
        self.dataset = dataset
        self.t0, self.alpha, self.t_min, self.iters = initial_temp, cooling_rate, stopping_temp, iters_per_temp
        self.seed, self.time_limit, self.initial_schedule = seed, time_limit, initial_schedule

    def solve(self) -> SolverResult:
        return self.optimize(self.initial_schedule)

    def optimize(self, initial_schedule=None) -> SolverResult:
        start = time.perf_counter()
        P = Problem(self.dataset)
        validator = TimetableValidator(self.dataset)
        rng = random.Random(self.seed)
        if P.empty_domain_vars:
            msgs = sorted({P.explain_empty(v) for v in P.empty_domain_vars})
            return SolverResult(self.name, False, [], message="Unsatisfiable: " + "; ".join(msgs[:3]))

        n = len(P.variables)
        vals = P.values_from_schedule(initial_schedule) if initial_schedule else None
        if not vals or len(vals) != n:
            vals = {v: rng.choice(P.domains[v]) for v in range(n)}
        vals = [vals[v] for v in range(n)]
        dom_sets = [set(P.domains[v]) for v in range(n)]
        sched = P.to_schedule(dict(enumerate(vals)))            # list aligned with variable ids

        def put(v, x):
            s = sched[v]
            s["day"], s["period"], s["room_name"], s["teacher_name"] = x
            vals[v] = x

        cur = validator.evaluate(sched)["total_cost"]
        initial_cost = cur
        best_cost, best_vals = cur, list(vals)
        temp, iters_done = self.t0, 0
        best_hist, cur_hist = [best_cost], [cur]

        while temp > self.t_min and time.perf_counter() - start < self.time_limit:
            for _ in range(self.iters):
                iters_done += 1
                changes = None
                if rng.random() < 0.65:                              # move 1: relocate one session
                    v = rng.randrange(n)
                    x = rng.choice(P.domains[v])
                    if x != vals[v]:
                        changes = [(v, vals[v], x)]
                else:                                                # move 2: swap two sessions of a class
                    v1 = rng.randrange(n)
                    group = P.class_vars[P.variables[v1].class_name]
                    v2 = rng.choice(group)
                    if v2 != v1:
                        a, b = vals[v1], vals[v2]
                        for n1, n2 in (((b[0], b[1], a[2], a[3]), (a[0], a[1], b[2], b[3])),   # swap slots
                                       (b, a)):                                                   # swap everything
                            if n1 in dom_sets[v1] and n2 in dom_sets[v2] and (n1, n2) != (a, b):
                                changes = [(v1, a, n1), (v2, b, n2)]
                                break
                if not changes:
                    continue
                for v, _, x in changes:
                    put(v, x)
                new = validator.evaluate(sched)["total_cost"]
                delta = new - cur
                if delta <= 0 or rng.random() < math.exp(-delta / temp):     # Metropolis criterion
                    cur = new
                    if cur < best_cost:
                        best_cost, best_vals = cur, list(vals)
                else:
                    for v, old, _ in changes:
                        put(v, old)
            best_hist.append(best_cost)
            cur_hist.append(cur)
            temp *= self.alpha

        best_schedule = P.to_schedule(dict(enumerate(best_vals)))
        ev = validator.evaluate(best_schedule)
        return SolverResult(self.name, ev["is_feasible"], best_schedule, nodes=iters_done,
                            elapsed=time.perf_counter() - start, cost_history=best_hist,
                            message=("Feasible schedule" if ev["is_feasible"] else "SA ended with hard violations")
                                    + f" (cost {initial_cost} -> {ev['total_cost']})",
                            extra={"current_history": cur_hist, "initial_cost": initial_cost})


class HybridCSPSolver:
    """Phase 1: Backtracking (or Min-Conflicts fallback) -> hard-feasible schedule.
       Phase 2: Simulated Annealing minimises soft penalties; hard weight 1000 keeps it feasible."""
    name = "Hybrid CSP + Simulated Annealing"

    def __init__(self, dataset, seed=None, time_limit=60.0, sa_params=None):
        self.dataset, self.seed, self.time_limit = dataset, seed, time_limit
        self.sa_params = sa_params or {}

    def solve(self) -> SolverResult:
        t0 = time.perf_counter()
        validator = TimetableValidator(self.dataset)
        bt = BacktrackingCSPSolver(self.dataset, randomize=self.seed is not None, seed=self.seed,
                                   time_limit=self.time_limit / 2).solve()
        start, phase1, nodes = bt.schedule, "Backtracking", bt.nodes
        if not bt.success:
            mc = MinConflictsSolver(self.dataset, seed=self.seed, time_limit=self.time_limit / 2).solve()
            if not mc.success:
                return SolverResult(self.name, False, mc.schedule, nodes=bt.nodes + mc.nodes,
                                    elapsed=time.perf_counter() - t0, cost_history=mc.cost_history,
                                    message=f"Phase 1 failed. Backtracking: {bt.message}. Min-Conflicts: {mc.message}")
            start, phase1, nodes = mc.schedule, "Min-Conflicts (fallback)", mc.nodes
        phase1_eval = validator.evaluate(start)
        sa = SimulatedAnnealingOptimizer(self.dataset, seed=self.seed, time_limit=self.time_limit,
                                         **self.sa_params).optimize(start)
        final = validator.evaluate(sa.schedule)
        return SolverResult(
            self.name, final["is_feasible"], sa.schedule, nodes=nodes, elapsed=time.perf_counter() - t0,
            cost_history=sa.cost_history,
            message=f"{phase1} found a feasible schedule (soft {phase1_eval['soft_penalties']}); "
                    f"SA reduced soft penalties to {final['soft_penalties']}",
            extra={"phase1": phase1, "phase1_soft": phase1_eval["soft_penalties"],
                   "sa_iterations": sa.nodes, "current_history": sa.extra.get("current_history", [])})
