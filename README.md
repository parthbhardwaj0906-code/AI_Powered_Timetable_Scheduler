# AI-Based Timetable Scheduler

A timetable generator built on classical AI search: **Backtracking CSP** (MRV, Degree heuristic, forward checking),
**Min-Conflicts** local search, and a bonus **Simulated Annealing / Hybrid CSP + SA** pipeline. It ships with an
interactive **Streamlit** dashboard, a unified constraint validator, a live manual editor, CSV/Excel export and an
automated benchmark runner.

No LLM is used anywhere in the scheduling engine. Everything is deterministic or seeded-random Python search.

---

## Contents

1. [Quick start](#quick-start)
2. [Project structure](#project-structure)
3. [The problem](#the-problem)
4. [Algorithms](#algorithms)
5. [The Streamlit app](#the-streamlit-app)
6. [Dataset format](#dataset-format)
7. [Benchmarking](#benchmarking)
8. [Troubleshooting](#troubleshooting)
9. [Limitations](#limitations)

---

## Quick start

Requires Python 3.9 or newer.

### 1. Create the environment and install dependencies

| System | Command (run inside the project folder) |
|---|---|
| Windows PowerShell | `.\setup.ps1` |
| Windows CMD | `setup.bat` |
| Linux / macOS / WSL / Git-Bash | `bash setup.sh` |

Each script creates a `venv/` folder, installs `requirements.txt`, and runs the smoke test.

Prefer to do it manually?

```bash
python -m venv venv
# Windows PowerShell:  .\venv\Scripts\Activate.ps1
# Linux / macOS:       source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the smoke test (recommended first step)

```bash
python run_smoke_test.py
```

This validates both sample datasets, runs every algorithm once, and re-checks each result with the unified
validator. If this prints sensible numbers, the engine works.

### 3. Launch the app

```bash
streamlit run app.py
```

The dashboard opens at <http://localhost:8501>.

---

## Project structure

```
timetable_scheduler/
├── app.py                    Streamlit dashboard
├── run_smoke_test.py         Quick end-to-end check of every solver
├── make_datasets.py          Regenerates the sample JSON files in data/
├── requirements.txt
├── setup.sh / setup.ps1 / setup.bat   One-command environment setup
│
├── data/
│   ├── small_dataset.json    Small sample (3 classes, 6 teachers, 4 rooms, 5x6 grid)
│   └── large_dataset.json    Large sample (8+ classes, 15+ teachers, 8+ rooms, 5x7 grid)
│
├── models/
│   └── schemas.py            Pydantic schemas + cross-reference validation
│
├── engine/
│   ├── problem.py            Builds variables/domains once (shared by all solvers) + pre-flight checks
│   ├── validator.py          Unified hard/soft constraint evaluator (single source of truth)
│   ├── backtracking.py       Backtracking CSP (plain baseline or with heuristics)
│   ├── min_conflicts.py      Min-Conflicts local search
│   ├── optimizer_sa.py       Simulated Annealing + Hybrid CSP + SA
│   └── result.py             SolverResult container returned by every solver
│
└── utils/
    ├── benchmarker.py        Solver factory + N-run benchmark runner (also a CLI)
    ├── exporter.py           Grid building, CSV and Excel export
    └── ui.py                 HTML/CSS components for the dashboard
```

**Design principle:** every solver builds its search space from `engine/problem.py` and judges every schedule with
`engine/validator.py`. Backtracking, Min-Conflicts, SA, the manual editor, the benchmarker and the export check
therefore all agree on what counts as a violation.

---

## The problem

Timetable scheduling is an NP-hard Constraint Satisfaction Problem.

- **Variable:** one weekly session of a (class, subject), e.g. "CSE-A / Data Structures, session 2".
- **Value:** a tuple `(day, period, room, teacher)`.
- **Domain:** only values that already satisfy the unary constraints: a qualified and available teacher, a room of
  the right type and capacity, and not the class's lunch slot.

### Cost function

```
Cost = 1000 x (hard violations) + (soft penalties)
```

A schedule is **feasible** when it has zero hard violations.

### Hard constraints (must hold)

| Code | Rule |
|---|---|
| H1 | A teacher cannot be in two places at the same time |
| H2 | A class cannot have two sessions at the same time |
| H3 | A room cannot host two sessions at the same time |
| H4 | Room capacity must be at least the class strength |
| H5 | Lab subjects use lab rooms; theory subjects use classrooms |
| H6 | The teacher must be qualified for the subject and available in that slot |
| H7 | Every (class, subject) gets exactly its required weekly hours |
| H8 | A teacher's total sessions must not exceed their weekly maximum |
| H9 | No session during the class's lunch slot, or during any `break_periods` of the day |

### Soft constraints (optimised, never required)

| Code | Preference | Penalty |
|---|---|---|
| S1 | Minimise free periods (gaps) inside a class's day | 1 per gap |
| S2 | Avoid the same theory subject twice on one day | 2 per extra session |
| S3 | Keep lab sessions in consecutive periods | 3 per isolated lab session |
| S4 | Respect teacher preferences: no first-period class (the assignment's own example) | 2 per session in period 1 |
| S5 | Avoid more than 2 consecutive teaching periods for a teacher | 2 per extra consecutive period |

---

## Algorithms

All algorithms return the same `SolverResult` (success flag, schedule, nodes/iterations, run time, cost history,
message), so the UI and benchmarks treat them uniformly. A solver only reports `success=True` for a complete schedule
with zero hard violations, and failures are reported as failures.

### Backtracking CSP (`engine/backtracking.py`)

Systematic search with switchable improvements, so the plain baseline and the improved version can be compared:

| Option | Effect |
|---|---|
| MRV | Choose the variable with the fewest remaining values |
| Degree heuristic | Tie-break MRV by the number of constraints with other variables |
| Forward checking | After each assignment, prune clashing values from neighbouring domains (fails early on an empty domain); also removes a teacher everywhere once their load limit is reached |
| Symmetry breaking | Sessions of the same (class, subject) are interchangeable, so they are forced into increasing slot order |
| Value ordering | Prefer lighter days for a class, and keep lab sessions back-to-back |

A time limit stops the search and reports a timeout rather than hanging.

### Min-Conflicts (`engine/min_conflicts.py`)

Starts from a complete random assignment, repeatedly picks a conflicted session and moves it to the value with the
fewest hard conflicts (ties broken by a soft-quality heuristic, then randomly). Plateau escape:

- **Random walk:** with probability 0.05 the session moves to a random value.
- **Random restart:** after a stretch of iterations with no improvement, the assignment is re-randomised.

The goal test and the cost history use the unified validator.

### Simulated Annealing and Hybrid (bonus) (`engine/optimizer_sa.py`)

- **Simulated Annealing:** neighbourhood moves are *relocate one session* and *swap two sessions of a class*,
  with Metropolis acceptance `P = exp(-delta / T)` and an exponential cooling schedule.
- **Hybrid CSP + SA:** Backtracking first finds a hard-feasible schedule. If that fails, Min-Conflicts is used as
  a fallback. SA then minimises the soft penalties. Because a hard violation costs 1000, SA effectively never trades
  feasibility for soft gains.

---

## The Streamlit app

| Tab | What it does |
|---|---|
| **Timetable views** | Colour-coded grids sliced by class, teacher or room. Labs have a double border; sessions in violation get a red outline. |
| **Manual editor** | Pick a session and change its day, period, room or teacher. The effect on hard and soft cost is previewed instantly, with the exact violations listed. Apply and Undo are available. |
| **Convergence** | Cost-versus-iteration (Min-Conflicts) or per-temperature-step (SA / Hybrid) plot, with an optional log scale. |
| **Benchmarks** | Run the experiment suite on both sample datasets and download the results as CSV. |
| **Export** | Download the schedule as CSV or as an Excel workbook (all sessions plus one sheet per class, teacher and room). |

The sidebar chooses the dataset (small sample, large sample, or an uploaded JSON), shows **pre-flight checks**
(impossible configurations such as a subject with no qualified teacher, or more hours than room-slots), picks the
algorithm and sets the time limit and seed. Generation is disabled while pre-flight errors exist.

---

## Dataset format

Datasets are JSON and use exactly the fields the assignment specifies:

| Entity | Fields |
|---|---|
| Subjects | `code`, `name`, `weekly_hours`, `type` (`theory` or `lab`) |
| Teachers | `name`, `subjects` (they can teach), `unavailable_slots`, `max_weekly_load` |
| Classes | `name`, `strength`, `subjects`, `lunch_break_slot` |
| Rooms | `name`, `capacity`, `type` (`classroom` or `lab`) |
| Time structure | `working_days`, `periods_per_day`, `break_periods` |

Files are validated with Pydantic before any solver sees them (types, positive numbers, unique names, references to
unknown subjects, slots outside the grid, and so on). Invalid files produce a readable error in the sidebar.

```json
{
  "time_structure": { "working_days": 5, "periods_per_day": 6, "break_periods": [3] },
  "subjects": [
    { "code": "CS301", "name": "Data Structures", "weekly_hours": 4, "type": "theory" },
    { "code": "CS302", "name": "Data Structures Lab", "weekly_hours": 2, "type": "lab" }
  ],
  "teachers": [
    {
      "name": "Dr. Anita Sharma",
      "subjects": ["CS301", "CS302"],
      "unavailable_slots": [ { "day": 0, "period": 0 } ],
      "max_weekly_load": 12
    }
  ],
  "classes": [
    { "name": "CSE-A", "strength": 60, "subjects": ["CS301", "CS302"], "lunch_break_slot": 3 }
  ],
  "rooms": [
    { "name": "CR-201", "capacity": 65, "type": "classroom" },
    { "name": "Lab-1", "capacity": 65, "type": "lab" }
  ]
}
```

Notes:

- Days and periods are **0-indexed** in the file (period index 3 is shown as "Period 4" in the UI).
- `unavailable_slots` is a **hard** constraint (H6): the teacher can never be scheduled there.
- A class's `lunch_break_slot` and the time structure's `break_periods` are periods where no session may be placed (H9).
- Each subject's teacher is chosen by the solver from the teachers whose `subjects` list includes it.
- An optional `avoid_slots` list on a teacher is accepted as an extension (extra S4 preferences). It is **not** part of
  the assignment spec and the sample datasets do not use it.

### Sample datasets

Both are in `data/` and are regenerated by `python make_datasets.py`.

| | Small | Large |
|---|---|---|
| Classes / teachers / rooms | 3 / 6 / 4 | 8 / 16 / 8 |
| Grid | 5 days x 6 periods | 5 days x 7 periods |
| Sessions to schedule | 41 | 156 |
| Teacher capacity used | 85% | 80% |
| Classroom slots used | 66% | 83% |

Both datasets are solvable (the app's pre-flight check confirms required hours do not exceed available room-slots,
teacher capacity or class slots, and the solvers find feasible schedules). Teacher weekly limits are derived from a
planted hour allocation with a small margin, so capacity is tight and every teacher has real work. The large dataset
also has deliberate bottlenecks: a single teacher for some labs, only two classrooms big enough for the 62-student
classes, and a visiting teacher available on three days only.

---

## Benchmarking

From the dashboard, use the **Benchmarks** tab, or from the command line:

```bash
python -m utils.benchmarker --runs 10 --time-limit 30
```

This runs every algorithm on both sample datasets and writes `benchmark_results.csv` (summary) and
`benchmark_results_raw.csv` (every run). Randomised algorithms (Min-Conflicts, SA, Hybrid) are averaged over the
requested number of seeded runs; the deterministic backtracking variants run once.

Metrics reported: success rate, average run time, average nodes/iterations, average hard violations and average
soft penalty. Cost-convergence data is available from the app's Convergence tab.

Algorithms compared: plain backtracking, backtracking with MRV + Degree + forward checking, Min-Conflicts,
Simulated Annealing from a random start, and Hybrid CSP + SA.

### Results

Fill this in from your own runs. Do not copy numbers from another machine.

| Dataset | Algorithm | Success rate | Avg time (s) | Avg nodes/iters | Avg hard | Avg soft |
|---|---|---|---|---|---|---|
| Small | Backtracking (plain) | | | | | |
| Small | Backtracking (MRV + Degree + FC) | | | | | |
| Small | Min-Conflicts | | | | | |
| Small | Simulated Annealing | | | | | |
| Small | Hybrid CSP + SA | | | | | |
| Large | Backtracking (plain) | | | | | |
| Large | Backtracking (MRV + Degree + FC) | | | | | |
| Large | Min-Conflicts | | | | | |
| Large | Simulated Annealing | | | | | |
| Large | Hybrid CSP + SA | | | | | |

---

## Troubleshooting

**PowerShell: "running scripts is disabled on this system"**
Allow scripts for the current terminal only:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
or use `cmd /c setup.bat`. To avoid activation entirely, run the app with
`.\venv\Scripts\python.exe -m streamlit run app.py`.

**`ModuleNotFoundError` for `engine`, `models` or `utils`**
Run commands from the project root (the folder containing `app.py`).

**The `(base)` conda prompt appears**
Not a problem, since the setup creates its own `venv/`. If `python` resolves to the wrong interpreter, run
`conda deactivate` first.

**A solver reports a timeout or "no feasible schedule"**
Raise the time limit in the sidebar. If the pre-flight panel lists errors, fix the dataset first.

**Excel download fails**
Make sure `openpyxl` is installed (it is in `requirements.txt`).

---

## Limitations

- Datasets upload as JSON only (no CSV import yet).
- AC-3 arc-consistency preprocessing is not implemented. Forward checking is used instead.
- The soft-constraint weights are fixed in `engine/validator.py` and are not configurable from the UI.
- S4 is implemented as a fixed rule (no first-period class), not as a per-teacher setting.
- Backtracking has no restarts, so on a very tight dataset it can hit the time limit (plain backtracking does on the
  large sample). Hybrid then falls back to Min-Conflicts for its feasible starting point.
- Each class has a single lunch slot, and every room is assumed available in every non-break period.
