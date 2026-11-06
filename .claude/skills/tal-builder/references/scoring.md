# Writing rubric.json

The rubric is applied offline to every stored company. It has two parts: `exclude` (deal-breakers: the company becomes `outside` with the reason) and `signals` (points, positive or negative). Tiers come from `config.json` → `tiers` (A at 55, B at 35, C at 15 by default).

```json
{
  "exclude": [
    {"reason": "staffing or recruiting firm", "when": {"path": "description_ai", "op": "regex", "value": "staffing (firm|agency)|recruit(ing|ment) (firm|agency)"}},
    {"reason": "sells what we sell", "when": {"path": "keywords", "op": "contains_any", "value": ["client portal software"]}}
  ],
  "signals": [
    {"label": "lookalike of a seed", "points": 20, "when": {"path": "sources", "op": "contains_any", "value": ["lookalike"]}},
    {"label": "hiring for the role our product replaces", "points": 25, "when": {"path": "job_postings.active_titles", "op": "contains_any", "value": ["tax manager", "client services"]}},
    {"label": "publishes pricing", "points": 10, "when": {"path": "attributes.has_pricing", "op": "eq", "value": true}},
    {"label": "20 to 100 employees", "points": 10, "when": {"path": "employee_count", "op": "between", "value": [20, 100]}},
    {"label": "raised a venture round in the last 3 years", "points": -15, "when": {"path": "funding.latest_funding_date", "op": "within_years", "value": 3}}
  ]
}
```

Conditions: `{"path", "op", "value"}`, combined with `{"all": [...]}`, `{"any": [...]}` and `{"not": {...}}`. Ops: `exists`, `eq`, `in`, `gte`, `lte`, `between` ([lo, hi]), `contains_any` (case-insensitive, over text or lists), `regex` (case-insensitive), `within_years` (a date field). The path `sources` tests which searches found the company: `lookalike`, `lookalike:<group>`, or a slice name from `slices.json`.

## How to choose weights

1. **Weight by lift, not by how sensible a signal sounds.** Lift is the share of seeds with the signal divided by the share of the market with it. `tal signals` estimates it against what you have pulled. For an exact market share, size the envelope plus the signal's filter (`tal size '<json>' --max-credits 1`) and divide by the envelope's size. A signal near 1x carries no information however sensible it sounds; in the run this skill came from, a "sales-led" flag covered two thirds of the market and slightly fewer of the fits.
2. **No single signal will hold every fit.** That is why signals score and do not gate. With ten to twenty seeds, read lifts as an ordering, not as precise numbers.
3. **Give lookalike membership real points**, more for a tight tier.
4. **Penalise what the anti-seeds share** and the seeds do not, and check the penalty against every seed: an adjective such as "AI-powered" was on known fits and known misses alike, and only "AI is the product" separated them.
5. **A kind of company the seeds do not cover needs its own terms**, and they are untested until it has seeds of its own. For such a kind, the usual signals can be the trade itself (marketing automation at a marketing agency), so score who it serves and what it makes instead, and admit only its top tier until it has seeds.
6. **Rerun `tal score` after every rubric change** and read a sample of the new top tier, not just the counts. A bug in a rule shows up in ten rows before it shows in a total.
