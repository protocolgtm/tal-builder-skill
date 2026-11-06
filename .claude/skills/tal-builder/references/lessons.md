# Lessons from the first run

The method was first run by hand, over two days in November 2026, by a B2B services firm on its own market, with Claude Code and Prospeo. Company names are left out. The numbers are its own.

## The numbers

- **Controls:** 17 companies known to be right, 8 known to be wrong.
- **The old list could not contain the customers it wanted.** Each of its four requirements (a marketer on staff, eight salespeople, 31 employees, a "B2B business model" field) excluded known fits. It was not unlucky; it was built to exclude them.
- **Envelope:** United States, 11 to 200 employees, three or fewer marketers, founded 2021 or earlier, nine industries. Kept 12 of 17 fits and 0 of 8 misses. Sized at **79,860** companies (54,415 with a B2B attribute and staffing firms removed). A market size, not a list.
- **Lookalikes:** two seed groups returned 507 and 782 companies with **none in common**. Lookalikes extend the kind of company they are given and nothing else.
- **First night:** 203 credits to a scored list of 3,567 companies in three tiers.
- **Whole run:** 802 credits to a scored list of 7,331; 3,382 in the target after the model read everything inside the envelope and checked each kept company's home page. The read dropped 23% of what the gates and score let through.
- **The expensive detour:** 462 of the 802 credits downloaded a whole category with no seeds of its own (about 10,000 marketing agencies). After the owner said in one sentence what makes an agency wrong, 16 stayed in the target. Ten seeds of that kind would have cost about 33 credits.

## What it taught

1. **Read the seed records before designing filters.** A field can be empty where the matching filter is reliable (see `prospeo-filters.md`).
2. **Test every filter on the seeds and anti-seeds before it gates anything.** Every quality gate that sounded right (small sales team, sales-led, revenue band, pricing page, case studies, hiring, HubSpot) dropped between a quarter and two thirds of the in-envelope fits. They became scored signals.
3. **The best signal was a combination.** A pricing page and HubSpot together was on 4% of the market and a third of the fits: 8 times more common among fits.
4. **Keep seeds in groups of one kind, ten to a search.** Hold-out fits did not come back from the other group's lookalikes.
5. **Lookalikes from real companies beat a written description.** The description-based lookalike drifted to consultancies that matched the words.
6. **Ask what makes a company of a kind wrong, then gate on the answer.** For a services seller the answer was "it sells what we sell". Without that gate the score ranked competitors highest, because the companies most like the seller are the ones a "similar to us" score likes best.
7. **The score orders; the read judges.** With lookalike points removed, 13 of 15 fits scored in the top tiers, and so did 5 of 8 misses. Only the envelope and the read kept the misses out.
8. **The read drops for things the record does not hold**: who owns the company, who buys from it, where it really is. A company's own site says who owns it only about half the time, so mark `check` when the reason comes from memory, then settle it from the site or a search.
9. **Removal is a status, never a deletion.** Companies came back when the rules changed.
10. **A trigger slice is the cheapest weekly refresh.** Companies inside the envelope advertising the role the seller's work replaces: 158 companies, 7 credits, and it found two known fits it was not told about.
