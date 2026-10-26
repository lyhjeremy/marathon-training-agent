# A marathon plan that reviews itself

*Wrapping an LLM in a LangGraph feedback loop, so the plan it returns has been checked before anyone reads it.*

## The problem with "write me a training plan"

Ask a chatbot for a 16-week marathon plan and you get a confident, tidy table. Look closely and it may raise mileage 30% in a week, forget to taper, or prescribe a 26-mile long run. The output looks expert and nobody has reviewed it. For something with real injury risk, that isn't good enough.

## Making the model critique itself

This project is a LangGraph agent: the LLM runs inside a state machine with a feedback loop.

- `assess` judges whether the goal time is realistic for the runner's current fitness and timeline, and proposes a different target if not.
- `plan` drafts a periodized week-by-week build: Base, Build, Peak, Taper.
- `adjust` tailors the plan to the specific race using figures from my own marathon analyses: [course difficulty](https://lyhjeremy.github.io/marathon-majors-course-difficulty/) (Boston's Newton hills call for downhill and quad work) and [the heat tax](https://lyhjeremy.github.io/marathon-heat-tax/) (about 1 minute per °F, so a hot race gets a slower pace band and heat acclimation).
- `critique` runs deterministic safety checks in Python (no week-over-week jump above 20%, race-week mileage at most 75% of peak, longest run at most 22.5 miles, long run no longer than the week) and adds an LLM review for realism.
- `revise` fixes exactly what critique flagged and loops back, up to a revision budget.

The design choice that matters is that critique isn't only an LLM asking itself whether the plan is good, which models do poorly. Part of it is coded rules. The LLM handles judgement; the rules handle the checks that can be written down.

## What it caught

Asked for a 3:05 Boston off 22 miles a week, with a 9-mile longest run and a 74°F forecast, the agent:

1. assessed the goal as unrealistic and recommended 3:20, because "starting from 22 mi/week and a 9-mile longest run leaves too little runway in 16 weeks to safely build both the mileage and the speed";
2. drafted and then tailored the plan, adding Newton-style hill repeats, sustained downhill running for quad durability, a 19-mile Boston race simulation with the hills at miles 15 to 19, and hot-day pace-band rehearsals;
3. caught 5 issues in its first draft, including a mileage jump above 20% in week 5. One revise pass fixed them and the second critique came back clean.

The full run is in [`examples/sample_run.md`](examples/sample_run.md). Every run prints its agent trace, so the self-correction is visible.

One run is an anecdote. `src/eval.py` is built to turn it into a measurement: it runs three synthetic runners (two deliberately aggressive, one realistic control) and scores each plan with the agent's own `_safety_checks` before and after the loop. Those numbers haven't been captured yet; the run was cut short by CLI rate limits during the build. There is also a Streamlit UI (`streamlit run app.py`) that streams the agent through its nodes as it works.

## Design notes

- LangGraph fits this well. Nodes are plain functions, and one `add_conditional_edges("critique", ...)` call gives the revise-or-finish loop.
- Generation runs on the Claude CLI (my subscription, no per-token cost) or the Anthropic API if a key is set. A run makes 4 to 8 calls depending on how many revisions it needs; `CLAUDE_MODEL=haiku` trades some polish for speed.
- The `max_revisions` budget and LangGraph's recursion limit guarantee the loop ends.

## Limitations and next steps

- The safety rules are general defaults, not individualized physiology. A real coach personalizes far more.
- There is no check on intensity distribution yet, such as roughly 80/20 easy to hard. That would be a good next deterministic rule.
- Nothing compares the final peak with the assessment's own suggestion. In the recorded run the plan peaked at 57 miles against a suggested 45.
- It plans once. It doesn't adapt week to week to logged training, which is the natural extension.

*Code: [github.com/lyhjeremy/marathon-training-agent](https://github.com/lyhjeremy/marathon-training-agent)*
