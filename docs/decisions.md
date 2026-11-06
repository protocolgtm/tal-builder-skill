# Decisions

- **2026-11-06. One skill, seven commands, one script.** Every Prospeo call, the cache and both credit caps live in `tal.py`, so no prompt can spend money another way. Standard library only, so installing is copying files.
- **2026-11-06. A lift-based rubric the model writes, not fixed rules.** The method's first run used hand-written rules for one market. Here the model writes `rubric.json` from the seed analysis and `tal signals` shows how often each rule fires on seeds, anti-seeds and pulls.
- **2026-11-06. The envelope is tested on seeds and anti-seeds before it gates.** At least 80% of seeds kept, no anti-seeds. Quality filters that sounded right dropped a quarter to two thirds of known fits in the first run (`references/lessons.md`).
- **2026-11-06. `rubric_handles`.** The sample's live run found anti-seeds no filter can separate (an exam-prep publisher labelled Accounting at the right size). They are listed in `envelope.json`, excluded by the rubric, and `tal score` warns if one reaches the target tiers. Not for anti-seeds a filter could remove.
- **2026-11-06. `tal init` writes an AGENTS.md section and a CLAUDE.md import into the user's project**, so any agent there knows to add new customers to `tal/inbox/new-customers.csv`. `/tal-refresh` checks the inbox first and asks when there is nothing new.
- **2026-11-06. New seed groups pull first in a refresh**, so a small weekly credit limit buys the new customers' lookalikes before it finishes an old, partly pulled group.
- **2026-11-06. No Google Sheets sync.** The output is a CSV; where it goes next is the user's choice.
