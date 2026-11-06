# Worked example: US accounting firms

One capped run of the sample, on 2026-11-06, for 22 Prospeo credits. Use it to see what each step produces, not as an answer: derive your own envelope and rubric from your own seeds.

| Step | What happened | Credits |
|---|---|---|
| Lookup | All 10 seeds and 12 anti-seeds resolved (1 credit per 25 domains; two calls because two anti-seeds were added after reading the first ten) | 2 |
| Read the controls | Seeds: US, labelled Accounting, 41 to 149 staff. Two anti-seeds look identical on every filter: an exam-prep publisher and a remote staffing company, both labelled Accounting at the right size | 0 |
| Envelope | US, 11 to 200 staff, Accounting. Kept 10 of 10 seeds and 2 of 12 anti-seeds; the two are listed under `rubric_handles` and caught by a rubric exclusion | 1 |
| Size | 8,146 companies inside the envelope | 1 |
| Lookalikes | 2,122 lookalikes of the ten seeds inside the envelope (85 pages); 375 pulled under the cap | 1 + 14 |
| Score | 0 of 13 anti-seeds in the target tiers; 8 of 11 seeds there without lookalike points | 0 |
| Read | 40 companies read: 36 kept, 3 to check (no domain; a possible acquirer; a holding-company platform), 1 dropped (describes itself as 425+ staff although the record says 185) | 0 |
| Refresh | One new customer and one new anti-seed in the inbox; looked up, envelope re-tested, more lookalikes pulled, rescored, exported | 6 |

What the run taught, which the skill now says:

- **Read the records.** Two records in the anti-seed lookup described a different company from the one at that domain. A headcount on a record can understate a firm by half; the description said so.
- **Some misses pass every filter.** No filter separates an exam-prep publisher labelled Accounting from a CPA firm. That is what `rubric_handles` and the read are for.
- **Roll-ups hide in plain sight.** 13 of 374 lookalikes had already been bought by a larger firm or platform, and said so in their name ("a Springline company", "now EisnerAmper") or description ("has joined", "now part of"). The rubric excludes them.
- **Check every exclusion against the seeds.** The first version of that exclusion matched "private equity" and removed a seed that serves private-equity funds. Rerun `tal score` and read the seed line after every rubric change.
- **Lift against your own lookalikes is close to 1x for everything**, because lookalikes already resemble the seeds. Measure lift against the envelope (`tal size '<envelope plus signal>'`) when the weight matters.
