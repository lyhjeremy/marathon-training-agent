"""Streamlit demo UI for the marathon training-plan agent.

Run:  streamlit run app.py

Uses the LangGraph agent's ``.stream()`` so you watch each node fire —
assess → plan → adjust → critique → revise — as the agent drafts and then
self-corrects the plan.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.graph import build_agent

st.set_page_config(page_title="Marathon Training Plan Agent", page_icon="🏃", layout="centered")

st.title("🏃 Marathon Training Plan Agent")
st.caption(
    "A LangGraph agent that drafts a periodized plan, then **critiques and revises "
    "its own work** until it passes real safety checks — you can watch it think below."
)

NODE_LABELS = {
    "assess": "Assessing whether the goal is realistic",
    "plan": "Drafting a periodized week-by-week plan",
    "adjust": "Tailoring to the course & race-day weather",
    "critique": "Running safety checks + an LLM review",
    "revise": "Revising the issues it flagged",
}

with st.sidebar:
    st.header("Your race")
    race = st.selectbox("Goal race", ["boston", "chicago", "berlin", "nyc", "london", "tokyo"])
    goal = st.text_input("Goal finish time (H:MM:SS)", "3:15:00")
    weeks = st.slider("Weeks until race day", 8, 24, 16)
    current_mpw = st.number_input("Current weekly mileage", 5, 120, 25)
    longest = st.number_input("Longest recent run (mi)", 3, 26, 10)
    days = st.slider("Days per week you can train", 3, 7, 5)
    temp = st.number_input("Expected race-day temp °F (0 = unknown)", 0, 100, 0)
    max_rev = st.slider("Revision budget", 0, 3, 2)
    go = st.button("Generate plan", type="primary", use_container_width=True)

if not go:
    st.info("Set your race details in the sidebar, then hit **Generate plan**.")
    st.stop()

profile = {
    "goal_race": race,
    "goal_time": goal,
    "weeks": weeks,
    "current_mpw": float(current_mpw),
    "longest_run_mi": float(longest),
    "days_per_week": days,
    "race_temp_f": float(temp) or None,
}

agent = build_agent()
state: dict = {}

with st.status("Running the agent…", expanded=True) as status:
    for step in agent.stream({"profile": profile, "max_revisions": max_rev}, {"recursion_limit": 50}):
        for node, delta in step.items():
            state.update(delta)
            note = ""
            if node == "critique":
                c = state.get("critique", {})
                note = " — clean ✅" if c.get("ok") else f" — {len(c.get('issues', []))} issue(s) found"
            st.write(f"**{NODE_LABELS.get(node, node)}**{note}")
    status.update(label="Agent finished", state="complete")

# --- assessment -------------------------------------------------------------
a = state.get("assessment", {})
verdict = "Realistic ✅" if a.get("feasible") else "Ambitious ⚠️"
st.subheader("Assessment")
c1, c2, c3 = st.columns(3)
c1.metric("Verdict", verdict)
c2.metric("Target time", str(a.get("recommended_goal_time", goal)))
c3.metric("Peak mileage", f"{a.get('peak_weekly_miles', '—')} mpw")
if a.get("rationale"):
    st.write(a["rationale"])

# --- the plan ---------------------------------------------------------------
st.subheader("Training plan")
weeks_data = state.get("weeks", [])
if weeks_data:
    df = pd.DataFrame(weeks_data)
    if "quality_sessions" in df.columns:
        df["quality_sessions"] = df["quality_sessions"].apply(
            lambda q: "; ".join(q) if isinstance(q, list) else q
        )
    cols = [c for c in ["week", "phase", "weekly_miles", "long_run_miles", "focus", "quality_sessions"]
            if c in df.columns]
    st.dataframe(df[cols], hide_index=True, use_container_width=True)

    st.line_chart(df.set_index("week")[["weekly_miles", "long_run_miles"]])

# --- safety verdict + trace -------------------------------------------------
crit = state.get("critique", {})
if crit.get("ok"):
    st.success(f"Final plan passed all safety checks after {state.get('revisions', 0)} revision(s).")
else:
    st.warning(f"Finalized with remaining notes: {crit.get('issues')}")

with st.expander("Agent trace — every node, in order"):
    for line in state.get("log", []):
        st.write(f"• {line}")
