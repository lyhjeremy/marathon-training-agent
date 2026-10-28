# A marathon plan that reviews itself

*Wrapping an LLM in a LangGraph feedback loop, so the plan it returns has been checked before anyone reads it.*

I asked the agent for a 3:05 Boston off 22 miles a week, with a 9-mile longest run, 16 weeks to go and a 74°F forecast. It told me the goal was unrealistic and recommended 3:20, because "starting from 22 mi/week and a 9-mile longest run leaves too little runway in 16 weeks to safely build both the mileage and the speed". Then it drafted a plan, tailored it to Boston, and its own critic found 5 problems in that draft, including a week-5 jump of more than 20% in mileage. One revision fixed them, and the second review came back clean.

That loop is the whole point of the project. Ask a chatbot for a 16-week marathon plan and you get a tidy, confident table, which on a closer look may raise mileage 30% in a week, forget the taper or prescribe a 26-mile long run. Nobody has reviewed it, and those are the mistakes that get runners hurt.

## The graph

The agent is a LangGraph state machine with five nodes. `assess` judges whether the goal time fits the runner's current fitness and timeline and proposes another target if it doesn't. `plan` drafts a periodized week-by-week build through Base, Build, Peak and Taper. `adjust` tailors that draft to the race using figures from my own marathon analyses: [course difficulty](https://lyhjeremy.github.io/marathon-majors-course-difficulty/) (Boston's Newton hills call for downhill and quad work) and [the heat tax](https://lyhjeremy.github.io/marathon-heat-tax/) (about 1 minute per °F, so a hot race gets a slower pace band and heat acclimation).

`critique` is where the checking happens. It runs deterministic safety checks in Python (no week-over-week jump above 20%, race-week mileage at most 75% of peak, longest run at most 22.5 miles, long run no longer than the week) and adds an LLM review for realism. `revise` fixes exactly what critique flagged and loops back, up to a revision budget.

Splitting the critic in two was the main design decision. Models are poor at grading their own work, so the checks that can be written down as arithmetic are written down as code, and the LLM is left with the judgement calls.

## The recorded run in detail

After `assess` moved the goal to 3:20, `adjust` added Newton-style hill repeats, sustained downhill running for quad durability, a 19-mile Boston race simulation with the hills at miles 15 to 19, and hot-day pace-band rehearsals. The critique and the single revise pass followed. The full run is in [`examples/sample_run.md`](examples/sample_run.md); every run prints its agent trace, so you can watch the self-correction happen.

One run is an anecdote. `src/eval.py` is built to turn it into a measurement: it runs three synthetic runners (two deliberately aggressive, one realistic control) and scores each plan with the agent's own `_safety_checks` before and after the loop. Those numbers haven't been captured yet, because CLI rate limits cut the run short during the build. There is also a Streamlit UI (`streamlit run app.py`) that streams the agent through its nodes as it works.

## Design notes

LangGraph suits this shape well: nodes are plain functions, and a single `add_conditional_edges("critique", ...)` call gives the revise-or-finish loop. The `max_revisions` budget and LangGraph's recursion limit guarantee that the loop ends.

Generation runs on the Claude CLI (my subscription, so no per-token cost) or on the Anthropic API if a key is set. A run makes 4 to 8 calls depending on how many revisions it needs, and `CLAUDE_MODEL=haiku` trades some polish for speed.

## Limitations and next steps

The safety rules are general defaults; a coach would personalize far more than four thresholds can. Intensity distribution isn't checked yet (roughly 80/20 easy to hard would be a good next deterministic rule), and nothing compares the final peak with the assessment's own suggestion: in the recorded run the plan peaked at 57 miles against a suggested 45. The agent also plans once. Adapting week to week to logged training is the natural extension.

*Code: [github.com/lyhjeremy/marathon-training-agent](https://github.com/lyhjeremy/marathon-training-agent)*
