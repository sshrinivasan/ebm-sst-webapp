# Client — Orphan Well Association

`## Aliases` and `## Address` are read entirely by Python
(`generate_cover_page()`'s `_lookup_client_address()` helper in
`scripts/generate_ebm_report.py`) — keep those two headings exactly as-is;
the parser looks for those literal headings and stops at the next
`#`-prefixed line.

`## Short Name` is read by Claude (not Python) wherever a client acronym or
short reference is needed in report text — e.g. the Exec Summary's OWA
variant (see `prompts/exec_summary.md`) and Section 1.2.1's
previous-assessment reference (see
`prompts/s1_2_1_previous_assessments.md`).

## Aliases
Orphan Well Association
OWA

## Short Name
OWA

## Address
Orphan Well Association
2100, 715-5th Ave SW
Calgary, Alberta
T2P 2X6
