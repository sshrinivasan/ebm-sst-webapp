# Client — Canadian Natural Resources Limited

`## Aliases` and `## Address` are read entirely by Python
(`generate_cover_page()`'s `_lookup_client_address()` helper in
`scripts/generate_ebm_report.py`) — keep those two headings exactly as-is;
the parser looks for those literal headings and stops at the next
`#`-prefixed line.

`## Short Name` is read by Claude (not Python) wherever a client acronym or
short reference is needed in report text — e.g. the Exec Summary's/Section
1's opening sentence (see `prompts/exec_summary.md`,
`prompts/s1_introduction.md`) and Section 1.2.1's previous-assessment
reference (see `prompts/s1_2_1_previous_assessments.md`).

## Aliases
Canadian Natural Resources Limited
Canadian Natural
CNRL

## Short Name
CNRL

## Address
Canadian Natural Resources Limited
Suite 300, 400 – 4th Ave SW
Calgary, AB
T2P 0J4
