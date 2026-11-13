"""Write eval/structured/web.json, the data the write-up's November section draws.

Reads eval/structured/results.json and runs_*.jsonl (no model calls).

    python -m eval.export_web
"""

from __future__ import annotations

import json
from pathlib import Path

D = Path(__file__).resolve().parent / "structured"


def main() -> None:
    res = json.loads((D / "results.json").read_text())
    runs = {}
    for s in ("before", "after"):
        runs[s] = {json.loads(x)["runner"]: json.loads(x) for x in (D / f"runs_{s}.jsonl").read_text().splitlines() if x}
    runners = {r["id"]: r for r in json.loads((D / "runners.json").read_text())["runners"]}
    out = {"summary": {k: v for k, v in res.items() if k != "per_runner"}, "runners": []}
    for row in res["per_runner"]:
        rid = row["runner"]
        b, a = runs["before"].get(rid), runs["after"].get(rid)
        entry = {**row, "profile": runners[rid]}
        if b and not b["error"]:
            entry["before"]["assessment"] = {k: b["assessment"].get(k) for k in
                                             ("feasible", "recommended_goal_time", "peak_weekly_miles", "rationale")}
            entry["before"]["long_runs"] = [w.get("long_run_miles") for w in b["final"] if isinstance(w, dict)]
            entry["before"]["log"] = b["log"]
        if a and not a["error"]:
            entry["after"]["assessment"] = a["assessment"]
            entry["after"]["long_runs"] = [w["long_run_miles"] for w in (a["weeks"] or [])]
            entry["after"]["log"] = a["log"]
            if a["plan"] and isinstance(a["plan"], dict) and a["plan"].get("weeks"):
                entry["after"]["sample_week"] = a["plan"]["weeks"][len(a["plan"]["weeks"]) // 2]
        out["runners"].append(entry)
    (D / "web.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print("wrote", D / "web.json")


if __name__ == "__main__":
    main()
