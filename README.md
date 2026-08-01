<p align="center">
  <img src="assets/banner.png" alt="Marathon Training Plan Agent" width="100%">
</p>

# Marathon Training Plan Agent

A **LangGraph agent** that writes you a personalized, periodized marathon training
plan — and then *critiques and revises its own work* until the plan passes a set
of safety checks. Tell it your race, goal time, current fitness and weeks to go;
it assesses whether the goal is realistic, drafts a week-by-week build, tailors it
to your specific race (course + weather), and self-corrects.

> 🌐 **Overview:** https://lyhjeremy.github.io/marathon-training-agent/
> 📖 **Product overview:** https://lyhjeremy.github.io/marathon-training-agent/overview/

## Why an agent (not just a prompt)?
Ask an LLM for a training plan and you get a plausible-looking table that might
ramp mileage too fast, forget a taper, or prescribe a 26-mile long run. This
project wraps the LLM in a **graph with a feedback loop**: a `critique` node runs
real, deterministic safety checks, and a `revise` node fixes what it flags — then
re-checks. The plan you get has survived review, not just generation.

## The graph

<p align="center">
  <img src="assets/architecture.png" alt="Marathon Training Plan Agent architecture" width="760">
</p>

| Node | What it does |
|---|---|
| **assess** | Judges whether the goal time is realistic; sets a target + peak mileage |
| **plan** | Drafts a periodized week-by-week plan (Base → Build → Peak → Taper) |
| **adjust** | Tailors it to the race using my own analyses — course difficulty & the heat tax |
| **critique** | Deterministic safety checks (ramp rate, taper, long-run caps) **+** an LLM review |
| **revise** | Fixes flagged issues and loops back to `critique` (up to a revision budget) |

The `adjust` step draws on findings from my running projects: [course
difficulty](https://github.com/lyhjeremy/marathon-strategy-rag) (Boston's Newton
hills, etc.) and [the heat tax](https://github.com/lyhjeremy/marathon-strategy-rag)
(~1 min/°F), so a hot Boston plan looks different from a cool Berlin one.

## Quick start
```bash
pip install -r requirements.txt

python -m src.cli --race boston --goal 3:05:00 --weeks 16 \
    --current-mpw 22 --longest 9 --days 5 --temp 74

python -m src.cli            # interactive prompts
```
Generation runs on the **Claude CLI** by default (your Claude subscription, no
per-token cost); set `ANTHROPIC_API_KEY` to use the API. Set `CLAUDE_MODEL` (e.g.
`haiku`) to trade a little quality for speed across the agent's several LLM calls.

## Try it in the browser
```bash
streamlit run app.py
```
A Streamlit UI wraps the agent: set your race in the sidebar and **watch it stream
through `assess → plan → adjust → critique → revise` live**, then read the plan
table, a weekly-mileage chart, the safety verdict, and the full agent trace.

## Measuring the safety loop
Does the critique/revise loop actually make plans safer? `src/eval.py` quantifies
it: it runs the agent on a panel of synthetic runners and compares each plan's
safety — scored by the agent's own deterministic `_safety_checks` — **before** the
loop (the raw first draft) against **after** it, reporting the pass-rate lift and
the drop in mean safety issues per plan.
```bash
python -m src.eval        # writes eval/results.csv + eval/safety_gain.png
```

## Files
| Path | What it is |
|---|---|
| `src/graph.py` | The LangGraph state machine: nodes, safety checks, the revise loop |
| `src/knowledge.py` | Course-difficulty & heat-tax figures from my analyses |
| `src/util.py` | Robust JSON extraction from LLM output |
| `src/eval.py` | Safety evaluation — does the self-critique loop make plans safer? |
| `src/llm.py` | LLM wrapper — Claude CLI (default) or Anthropic API |
| `src/cli.py` | Collect inputs, run the agent, print the plan + agent trace |
| `app.py` | **Streamlit demo UI** — watch the agent stream through its nodes |

## Notes
The output includes an **agent trace** so you can see it work — each node's action
and how many issues each critique caught. Educational tool, not medical or
professional coaching advice.

## License
[MIT](LICENSE) © 2026 Jeremy Lee
