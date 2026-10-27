import copy
import hashlib
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine.problem import check_dataset
from engine.validator import TimetableValidator
from models.schemas import TimetableDataset
from utils.benchmarker import ALGORITHMS, BenchmarkRunner, make_solver
from utils.exporter import DAY_NAMES, grid_dataframe, to_csv_bytes, to_excel_bytes
from utils.ui import CSS, badge, kpi, render_grid

_V = tuple(int(x) for x in st.__version__.split(".")[:2])
STRETCH = {"width": "stretch"} if _V >= (1, 50) else {"use_container_width": True}

st.set_page_config(page_title="AI Timetable Scheduler", page_icon="📅", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

DATA_DIR = Path(__file__).parent / "data"
SOURCES = {"Small sample (3 classes, 6 teachers)": "small_dataset.json",
           "Large sample (8 classes, 16 teachers)": "large_dataset.json",
           "Upload JSON": None}


def validate(raw: dict) -> dict:
    return TimetableDataset.model_validate(raw).model_dump()


def load_sample(fname: str) -> dict:
    return validate(json.loads((DATA_DIR / fname).read_text()))


for key, default in (("schedule", []), ("result", None), ("undo", []), ("ds_sig", None), ("bench", None)):
    st.session_state.setdefault(key, default)

# ------------------------------------------------------------------ sidebar
st.sidebar.title("⚙️ Configuration")
source = st.sidebar.radio("Dataset", list(SOURCES))
dataset, load_error = None, None
try:
    if SOURCES[source]:
        dataset = load_sample(SOURCES[source])
    else:
        up = st.sidebar.file_uploader("Timetable JSON", type=["json"])
        if up is not None:
            dataset = validate(json.load(up))
except Exception as e:                                   # pydantic / JSON errors
    load_error = str(e)

if load_error:
    st.sidebar.error(f"Invalid dataset:\n\n{load_error}")
if dataset is None:
    st.markdown('<div class="hero"><h1>📅 AI-Based Timetable Scheduler</h1>'
                '<p>Choose or upload a dataset in the sidebar to begin.</p></div>', unsafe_allow_html=True)
    st.stop()

sig = hashlib.md5(json.dumps(dataset, sort_keys=True).encode()).hexdigest()
if sig != st.session_state.ds_sig:                       # new dataset -> clear previous results
    st.session_state.update(ds_sig=sig, schedule=[], result=None, undo=[])

errors, warnings = check_dataset(dataset)
for e in errors:
    st.sidebar.error(e)
for w in warnings:
    st.sidebar.warning(w)
if not errors:
    st.sidebar.success("Pre-flight checks passed")

st.sidebar.markdown("---")
algo = st.sidebar.selectbox("Algorithm", ALGORITHMS, index=4)
time_limit = st.sidebar.slider("Time limit (s)", 5, 120, 30)
max_iter = st.sidebar.number_input("Min-Conflicts max iterations", 500, 200000, 20000, step=500)
fixed_seed = st.sidebar.checkbox("Fixed random seed", value=False)
seed = st.sidebar.number_input("Seed", 0, 10**6, 42) if fixed_seed else None

if st.sidebar.button("🚀 Generate timetable", type="primary", **STRETCH, disabled=bool(errors)):
    with st.spinner(f"Running {algo}…"):
        res = make_solver(algo, dataset, seed=seed, time_limit=time_limit, max_iterations=int(max_iter)).solve()
    st.session_state.update(result=res, schedule=copy.deepcopy(res.schedule), undo=[])

# ------------------------------------------------------------------ header + KPIs
validator = TimetableValidator(dataset)
schedule = st.session_state.schedule
res = st.session_state.result
ev = validator.evaluate(schedule, detail=True) if schedule else None
conflicts = frozenset(ev["conflict_sessions"]) if ev else frozenset()

st.markdown('<div class="hero"><h1>📅 AI-Based Timetable Scheduler</h1>'
            '<p>Constraint satisfaction · Min-Conflicts · Simulated Annealing · live conflict validation</p></div>',
            unsafe_allow_html=True)

if res is not None and not res.success:
    st.error(f"**{res.algorithm} did not produce a feasible timetable.** {res.message}")
elif res is not None:
    st.success(f"**{res.algorithm}:** {res.message}")

if ev:
    c = st.columns(5)
    c[0].markdown(kpi("Status", "Feasible" if ev["is_feasible"] else "Infeasible",
                      "ok" if ev["is_feasible"] else "bad"), unsafe_allow_html=True)
    c[1].markdown(kpi("Hard violations", ev["hard_violations"], "ok" if ev["is_feasible"] else "bad"),
                  unsafe_allow_html=True)
    c[2].markdown(kpi("Soft penalty", ev["soft_penalties"], "warn"), unsafe_allow_html=True)
    c[3].markdown(kpi("Run time", f"{res.elapsed:.2f} s" if res else "-"), unsafe_allow_html=True)
    c[4].markdown(kpi("Nodes / iterations", f"{res.nodes:,}" if res else "-"), unsafe_allow_html=True)
    st.write("")

tab_view, tab_edit, tab_conv, tab_bench, tab_export = st.tabs(
    ["📌 Timetable views", "✏️ Manual editor", "📈 Convergence", "🧪 Benchmarks", "📥 Export"])

# ------------------------------------------------------------------ views
with tab_view:
    if not schedule:
        st.info("Pick an algorithm and press **Generate timetable** in the sidebar.")
    else:
        kind_label = st.radio("Slice by", ["Class", "Teacher", "Room"], horizontal=True)
        kind = kind_label.lower()
        pool = {"class": dataset["classes"], "teacher": dataset["teachers"], "room": dataset["rooms"]}[kind]
        name = st.selectbox(kind_label, [x["name"] for x in pool])
        st.markdown(render_grid(schedule, dataset, kind, name, conflicts), unsafe_allow_html=True)
        st.caption("Purple double border = lab · red outline = session involved in a hard-constraint violation")

# ------------------------------------------------------------------ manual editor
with tab_edit:
    if not schedule:
        st.info("Generate a timetable first.")
    else:
        st.subheader("Move a session — validated instantly")
        ts = dataset["time_structure"]

        def label(i):
            s = schedule[i]
            return (f"#{i} · {s['class_name']} · {s['subject_code']} · {DAY_NAMES[s['day']][:3]} P{s['period'] + 1}"
                    f" · {s['room_name']} · {s['teacher_name']}")

        idx = st.selectbox("Session", range(len(schedule)), format_func=label)
        cur = schedule[idx]
        a, b, c_, d_ = st.columns(4)
        new_day = a.selectbox("Day", range(ts["working_days"]), index=cur["day"],
                              format_func=lambda x: DAY_NAMES[x], key=f"day{idx}")
        new_period = b.selectbox("Period", range(ts["periods_per_day"]), index=cur["period"],
                                 format_func=lambda x: f"Period {x + 1}", key=f"per{idx}")
        room_names = [r["name"] for r in dataset["rooms"]]
        new_room = c_.selectbox("Room", room_names, index=room_names.index(cur["room_name"]), key=f"room{idx}")
        teacher_names = [t["name"] for t in dataset["teachers"]]
        new_teacher = d_.selectbox("Teacher", teacher_names, index=teacher_names.index(cur["teacher_name"]),
                                   key=f"tea{idx}")

        trial = copy.deepcopy(schedule)
        trial[idx].update(day=new_day, period=new_period, room_name=new_room, teacher_name=new_teacher)
        tev = validator.evaluate(trial, detail=True)
        mine = [m for code, m, idxs in tev["details"] if idx in idxs]
        changed = trial[idx] != cur

        m1, m2 = st.columns(2)
        m1.metric("Hard violations", tev["hard_violations"], tev["hard_violations"] - ev["hard_violations"],
                  delta_color="inverse")
        m2.metric("Soft penalty", tev["soft_penalties"], tev["soft_penalties"] - ev["soft_penalties"],
                  delta_color="inverse")
        if not changed:
            st.caption("Change a field above to preview the effect of a move.")
        elif mine:
            st.markdown("".join(badge("⚠ " + m, "red") for m in mine), unsafe_allow_html=True)
        else:
            st.markdown(badge("✓ This move introduces no violation for this session", "green"),
                        unsafe_allow_html=True)

        b1, b2, _ = st.columns([1, 1, 4])
        if b1.button("Apply move", type="primary", disabled=not changed):
            st.session_state.undo.append(copy.deepcopy(schedule))
            st.session_state.schedule = trial
            st.rerun()
        if b2.button("↩ Undo", disabled=not st.session_state.undo):
            st.session_state.schedule = st.session_state.undo.pop()
            st.rerun()

        st.markdown("#### Current violations")
        if ev["details"]:
            st.dataframe(pd.DataFrame([{"Rule": code, "Problem": msg, "Sessions": ", ".join(f"#{i}" for i in idxs)}
                                       for code, msg, idxs in ev["details"]]),
                         **STRETCH, hide_index=True)
        else:
            st.markdown(badge("No hard-constraint violations", "green"), unsafe_allow_html=True)
        with st.expander("Constraint breakdown"):
            st.write("Hard:", {k: v for k, v in ev["hard_breakdown"].items() if v})
            st.write("Soft (weighted):", ev["soft_breakdown"])

# ------------------------------------------------------------------ convergence
with tab_conv:
    if res is None or not res.cost_history:
        st.info("Run Min-Conflicts, Simulated Annealing or the Hybrid solver to see its cost history "
                "(plain backtracking has no cost trajectory).")
    else:
        fig = go.Figure()
        label_x = "Iteration" if res.algorithm == "Min-Conflicts" else "Temperature step"
        fig.add_trace(go.Scatter(y=res.cost_history, mode="lines",
                                 name="Cost" if res.algorithm == "Min-Conflicts" else "Best cost",
                                 line=dict(width=3)))
        cur_hist = res.extra.get("current_history")
        if cur_hist:
            fig.add_trace(go.Scatter(y=cur_hist, mode="lines", name="Current cost", line=dict(width=1, dash="dot")))
        fig.update_layout(title=f"{res.algorithm}: cost = 1000·hard + soft", xaxis_title=label_x,
                          yaxis_title="Total cost", height=430,
                          yaxis_type="log" if st.checkbox("Log scale", value=False) else "linear")
        st.plotly_chart(fig, **STRETCH)
        if res.extra.get("phase1_soft") is not None:
            st.caption(f"Phase 1 ({res.extra['phase1']}) soft penalty: {res.extra['phase1_soft']} → "
                       f"after SA: {ev['soft_penalties'] if ev else '-'}")

# ------------------------------------------------------------------ benchmarks
with tab_bench:
    st.subheader("Experiment runner")
    st.caption("Randomised algorithms are averaged over N seeded runs; deterministic backtracking runs once.")
    bc1, bc2 = st.columns([1, 3])
    runs = bc1.slider("Runs per randomised algorithm", 1, 10, 3)
    chosen = bc2.multiselect("Algorithms", ALGORITHMS, default=ALGORITHMS)
    if st.button("Run benchmark on both sample datasets"):
        box = st.empty()
        runner = BenchmarkRunner({"Small": load_sample("small_dataset.json"), "Large": load_sample("large_dataset.json")},
                                 runs=runs, time_limit=time_limit, algorithms=chosen,
                                 progress=lambda m: box.caption(f"⏳ {m}"))
        df = runner.run()
        box.empty()
        st.session_state.bench = (df, runner.raw)
    if st.session_state.bench:
        df, raw = st.session_state.bench
        st.dataframe(df, **STRETCH, hide_index=True)
        fig = go.Figure()
        for dsn, g in df.groupby("Dataset"):
            fig.add_trace(go.Bar(x=g["Algorithm"], y=g["Avg time (s)"], name=dsn))
        fig.update_layout(barmode="group", title="Average run time (s)", height=380, yaxis_type="log")
        st.plotly_chart(fig, **STRETCH)
        st.download_button("Download summary CSV", df.to_csv(index=False).encode(), "benchmark_summary.csv", "text/csv")
        st.download_button("Download raw runs CSV", raw.to_csv(index=False).encode(), "benchmark_raw.csv", "text/csv")

# ------------------------------------------------------------------ export
with tab_export:
    if not schedule:
        st.info("Generate a timetable to enable downloads.")
    else:
        if ev and not ev["is_feasible"]:
            st.warning(f"This timetable still has {ev['hard_violations']} hard violation(s).")
        e1, e2 = st.columns(2)
        e1.download_button("📄 Download CSV", to_csv_bytes(schedule, dataset), "timetable.csv", "text/csv",
                           **STRETCH)
        e2.download_button("📊 Download Excel (all grids)", to_excel_bytes(schedule, dataset), "timetable.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           **STRETCH)
