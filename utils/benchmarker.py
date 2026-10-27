"""Solver factory + automated benchmark runner (averaged over N runs for randomised methods)."""
import argparse
import json
import statistics
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from engine.backtracking import BacktrackingCSPSolver
from engine.min_conflicts import MinConflictsSolver
from engine.optimizer_sa import HybridCSPSolver, SimulatedAnnealingOptimizer
from engine.validator import TimetableValidator

ALGORITHMS = [
    "Backtracking (plain baseline)",
    "Backtracking (MRV + Degree + FC)",
    "Min-Conflicts",
    "Simulated Annealing (random start)",
    "Hybrid CSP + Simulated Annealing",
]
RANDOMIZED = {"Min-Conflicts", "Simulated Annealing (random start)", "Hybrid CSP + Simulated Annealing"}


def make_solver(name: str, dataset: dict, seed: Optional[int] = None, time_limit: float = 30.0,
                max_iterations: int = 20000):
    if name == "Backtracking (plain baseline)":
        return BacktrackingCSPSolver(dataset, use_mrv=False, use_degree=False, use_forward_checking=False,
                                     symmetry_breaking=False, value_ordering=False, time_limit=time_limit,
                                     name=name)
    if name == "Backtracking (MRV + Degree + FC)":
        return BacktrackingCSPSolver(dataset, randomize=seed is not None, seed=seed, time_limit=time_limit,
                                     name=name)
    if name == "Min-Conflicts":
        return MinConflictsSolver(dataset, max_iterations=max_iterations, seed=seed, time_limit=time_limit)
    if name == "Simulated Annealing (random start)":
        return SimulatedAnnealingOptimizer(dataset, seed=seed, time_limit=time_limit)
    if name == "Hybrid CSP + Simulated Annealing":
        return HybridCSPSolver(dataset, seed=seed, time_limit=time_limit)
    raise ValueError(f"Unknown algorithm: {name}")


class BenchmarkRunner:
    def __init__(self, datasets: Dict[str, dict], runs: int = 10, time_limit: float = 30.0,
                 algorithms: Optional[List[str]] = None, progress: Optional[Callable[[str], None]] = None):
        self.datasets, self.runs, self.time_limit = datasets, runs, time_limit
        self.algorithms = algorithms or ALGORITHMS
        self.progress = progress or (lambda msg: None)
        self.histories: Dict[tuple, List[float]] = {}
        self.raw = pd.DataFrame()

    def run(self) -> pd.DataFrame:
        rows, raw = [], []
        for ds_name, ds in self.datasets.items():
            validator = TimetableValidator(ds)
            for algo in self.algorithms:
                n_runs = self.runs if algo in RANDOMIZED else 1          # deterministic => 1 run is enough
                for seed in range(n_runs):
                    self.progress(f"{ds_name} | {algo} | run {seed + 1}/{n_runs}")
                    res = make_solver(algo, ds, seed=seed, time_limit=self.time_limit).solve()
                    ev = validator.evaluate(res.schedule) if res.schedule else None
                    raw.append({"Dataset": ds_name, "Algorithm": algo, "Run": seed + 1,
                                "Success": bool(res.success and ev and ev["is_feasible"]),
                                "Time (s)": res.elapsed, "Nodes/Iterations": res.nodes,
                                "Hard": ev["hard_violations"] if ev else None,
                                "Soft": ev["soft_penalties"] if ev else None})
                    if seed == 0:
                        self.histories[(ds_name, algo)] = res.cost_history
        self.raw = pd.DataFrame(raw)
        for (ds_name, algo), g in self.raw.groupby(["Dataset", "Algorithm"], sort=False):
            rows.append({"Dataset": ds_name, "Algorithm": algo, "Runs": len(g),
                         "Success rate (%)": round(100 * g["Success"].mean(), 1),
                         "Avg time (s)": round(g["Time (s)"].mean(), 3),
                         "Avg nodes/iterations": round(g["Nodes/Iterations"].mean(), 1),
                         "Avg hard violations": round(g["Hard"].mean(), 2) if g["Hard"].notna().any() else None,
                         "Avg soft penalty": round(g["Soft"].mean(), 2) if g["Soft"].notna().any() else None})
        return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--time-limit", type=float, default=30.0)
    ap.add_argument("--out", default="benchmark_results.csv")
    a = ap.parse_args()
    from models.schemas import TimetableDataset
    data = {}
    for label, f in (("Small", "small_dataset.json"), ("Large", "large_dataset.json")):
        data[label] = TimetableDataset.model_validate(json.loads(Path("data", f).read_text())).model_dump()
    runner = BenchmarkRunner(data, runs=a.runs, time_limit=a.time_limit, progress=print)
    df = runner.run()
    print(df.to_string(index=False))
    df.to_csv(a.out, index=False)
    runner.raw.to_csv(a.out.replace(".csv", "_raw.csv"), index=False)
    print(f"\nSaved {a.out}")
