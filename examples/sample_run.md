# Example run

```
$ python -m src.cli --race boston --goal 3:05:00 --weeks 16 \
      --current-mpw 22 --longest 9 --days 5 --temp 74
```

Output (Boston goal 3:05, hot race day). Note the agent judged 3:05 unrealistic
and recommended 3:20, tailored the plan to the Newton hills and 74°F heat, and its
`critique` node caught 5 issues on the first draft that a `revise` pass then fixed:

```

================================================================
ASSESSMENT
================================================================
Goal looks ambitious ⚠️. Target: 3:20:00  (peak ~45 mpw)
A 3:05 marathon (~7:03/mi) typically requires a 40-55 mi/week base with long runs already near 16-18 miles; starting from 22 mi/week and a 9-mile longest run leaves too little runway in 16 weeks to safely build both the mileage and the speed. Targeting 3:20 is an aggressive-but-achievable stretch that lets you peak around 45 mi/week without high injury risk.

================================================================
TRAINING PLAN
================================================================
Wk  Phase  Miles  Long  Focus / key sessions
----------------------------------------------------------------
 1  Base      28    10  Establish aerobic base and early heat/hydration habits; keep non-long days truly easy — 4x strides on easy day; easy aerobic run + hydration routine practice
 2  Base      30    12  Build easy volume; begin heat acclimation on warmer runs — 6x100m strides; 5 mi steady on rolling terrain
 3  Base      32    13  Introduce MP feel and even-effort pacing; prime quads for downhills — 4x1 mi @ marathon pace (~7:38, controlled start); gentle downhill strides
 4  Base      29    11  Step-back recovery week; light quad conditioning — easy run + strides; short downhill drills
 5  Build     34    14  Add threshold work; drill controlled, even pacing with easy days between hard efforts — 5x1000m @ 10K pace; 6 mi @ MP with even splits
 6  Build     38    15  Boston-specific hill strength and quad durability on descents — 4 mi tempo; rolling Newton-style hill repeats (up + down)
 7  Build     35    13  Step-back recovery week; reinforce fueling/hydration on-the-move — 3 mi tempo; downhill strides + hydration practice
 8  Build     41    16  Sharpen speed; practice MP under fatigue with an easy day flanking the long run — 6x800m @ 5K pace; 16 mi long run w/ 4 @ MP in final miles
 9  Build     45    17  Build downhill/quad resilience; carry fuel + fluids on long run — 5 mi tempo; sustained downhill running practice for Newton descents
10  Peak      41    15  Step-back before peak; calibrate hot-day pace band vs. goal effort — 4 mi tempo; hot-day pace-band run (rehearse ~74F effort)
11  Peak      48    18  Peak endurance; only one hard quality day plus the long run, with genuine easy running between — 2x2 mi @ threshold (easy days on either side); 18 mi w/ 5 @ MP in miles 12-17
12  Peak      53    19  Simulate Boston profile, fueling, and heat; keep midweek relaxed so the long run stays the week's hardest effort — 5 mi steady (moderate, not hard); 19 mi race sim: downhill start, Newton hills at ~15-19 mi
13  Peak      57    20  Peak dress rehearsal at higher aerobic volume; long run ~35% of week, surrounded by easy days — 4 mi tempo (buffered by easy days); 20 mi w/ 6 @ MP over Newton sim + full race-day fueling
14  Taper     44    16  Begin taper; hold sharpness and quad readiness, keep heat exposure — 4 mi @ MP; short downhill hill strides
15  Taper     33    12  Reduce volume, stay fresh; lock in controlled-start pacing plan — 3 mi @ MP (rehearse conservative early pace); 6x strides + light heat exposure
16  Taper     22     9  Race week: rest, fuel, hydrate; even-effort start, respect Newton hills and heat, adjust 3:20 goal to hot-day band — 2 mi @ MP + strides; shakeout jog + hydration/fuel check

================================================================
AGENT TRACE
================================================================
  • assess → feasible=False, target 3:20:00, peak 45 mpw
  • plan → drafted 16 weeks
  • adjust → tailored plan to course & weather
  • critique → 5 issue(s): week 5 jumps mileage >20% (23→28)
  • revise #1 → addressed 5 issue(s)
  • critique → clean
  ✔ final plan passed all safety checks
```
