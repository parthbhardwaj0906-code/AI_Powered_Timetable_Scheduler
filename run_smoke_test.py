"""Run this BEFORE the Streamlit app:  python run_smoke_test.py
Validates both datasets, runs every solver once, and re-checks each schedule with the unified validator."""
import json
from pathlib import Path

from engine.problem import check_dataset
from engine.validator import TimetableValidator
from models.schemas import TimetableDataset
from utils.benchmarker import ALGORITHMS, make_solver

for fname in ("small_dataset.json", "large_dataset.json"):
    raw = json.loads((Path("data") / fname).read_text())
    ds = TimetableDataset.model_validate(raw).model_dump()
    errors, warnings = check_dataset(ds)
    print(f"\n=== {fname}  (pre-flight errors: {errors or 'none'}, warnings: {warnings or 'none'})")
    val = TimetableValidator(ds)
    for algo in ALGORITHMS:
        res = make_solver(algo, ds, seed=1, time_limit=30).solve()
        ev = val.evaluate(res.schedule) if res.schedule else None
        shown = (f"hard={ev['hard_violations']} soft={ev['soft_penalties']}" if ev else "no schedule")
        print(f"{algo:38s} success={str(res.success):5s} {res.elapsed:6.2f}s nodes/iters={res.nodes:<7d} {shown}")
        if not res.success:
            print("    ->", res.message)
