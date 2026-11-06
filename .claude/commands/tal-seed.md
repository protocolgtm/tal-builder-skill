---
description: Add or remove seed companies (customers or best prospects) in a named group
argument-hint: "add <group> <domain...> | remove <domain...> | list"
---

Use the `tal-builder` skill. Arguments: `$ARGUMENTS`.

- **add <group> <domains>:** a group holds one kind of company (`core`, `agencies`, `fintech`); if the new seeds are a different kind from the group's existing seeds, suggest a new group. Run `python3 <skill>/scripts/tal.py seed add <group> <domains> --max-credits 3`. That costs at most 3 credits: the lookup, plus a re-test of the envelope if one exists. Say so first. Report each seed's record, and whether it passes the envelope. A seed the envelope drops is a sign the envelope may be wrong. Then offer `tal.py lookalikes <group> --max-credits 1` to count what the group would add (about 1 credit per ten seeds), and say what pulling them would cost before doing it.
- **remove <domains>:** run `tal.py seed remove <domains> --note "<reason>"`, asking for the reason if none is given. Explain that companies found only through lookalikes that included this seed become `stale` at the next merge (never deleted) and that `/tal-refresh` re-pulls the group without it. Then run `tal.py score` and `tal.py merge` (free) and report how many companies changed status.
- **list** or no arguments: `tal.py seed list`.
