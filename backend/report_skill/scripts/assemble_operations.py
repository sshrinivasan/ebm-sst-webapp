"""Turn the ONE authored-content JSON (written by the single Claude authoring call) into the
operations JSON for apply_operations.py.

Usage: python3 assemble_operations.py <authored.json> <partial_docx> <excel_data.json> <operations.json>

authored.json (see prompts/one_call_authoring.md):
  exec_summary, s4_3_chloride, s8_summary      -> list of blocks (required)
  s5_1_phase1, s5_2_transport, s5_3_footprint  -> list of blocks, or null (must be null/absent when
                                                  section5_present is false; s5_1 may also be null
                                                  when no Phase 1 ESA was provided)
  practitioner_information                     -> {"site","report","check","uncertain","not_found","incomplete"}
                                                  (written to practitioner_info.json beside operations.json)
A block is {"style": heading3|body|bullet|smalltitle, "text": "..."} or {"style": "bullet", "runs": [{"text":..,"bold":true}]}.
"""
import json, os, sys
from docx import Document

STYLES = {"heading3", "body", "bullet", "smalltitle"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def check_blocks(name, blocks):
    errs = []
    if not isinstance(blocks, list) or not blocks:
        return [f"{name}: must be a non-empty list of blocks"]
    for i, b in enumerate(blocks):
        if not isinstance(b, dict) or b.get("style") not in STYLES:
            errs.append(f"{name}[{i}]: bad or missing style")
        elif not (isinstance(b.get("text"), str) and b["text"].strip()) and not b.get("runs"):
            errs.append(f"{name}[{i}]: needs text or runs")
    return errs


def stale_53_paragraphs(docx_path):
    """Template example paragraphs between <INSERT_5_3_START> and <INSERT_5_3_END> that are not
    figure titles/drawings (the generator has already placed the figure table/figures there)."""
    d = Document(docx_path)
    out, on = [], False
    for p in d.paragraphs:
        t = p.text
        if "<INSERT_5_3_START>" in t:
            on = True
            continue
        if "<INSERT_5_3_END>" in t:
            break
        if not on or not t.strip():
            continue
        ps = p._p.find(f"{W}pPr/{W}pStyle")
        sid = ps.get(W + "val") if ps is not None else ""
        if sid in ("FigureTitle", "Caption") or (p.style is not None and p.style.name in ("Figure Title", "Caption")):
            continue
        if list(p._p.iter(W + "drawing")):
            continue
        out.append(t)
    return out


def main(authored_path, docx_path, excel_path, ops_path):
    a = json.load(open(authored_path, encoding="utf-8"))
    ex = json.load(open(excel_path, encoding="utf-8"))
    s5 = bool(ex.get("section5_present"))
    errs, ops = [], []
    rb = lambda s, e, blocks: {"op": "replace_between", "start_placeholder": s, "end_placeholder": e, "blocks": blocks}

    for key, (s, e) in (("exec_summary", ("<INSERT_EXEC_SUMMARY_START>", "<INSERT_EXEC_SUMMARY_END>")),
                        ("s4_3_chloride", ("<INSERT_43_START>", "<INSERT_43_END>"))):
        errs += check_blocks(key, a.get(key))
        ops.append(rb(s, e, a.get(key) or []))

    for key, (s, e) in (("s5_1_phase1", ("<INSERT_5_1_START>", "<INSERT_5_1_END>")),
                        ("s5_2_transport", ("<INSERT_5_2_START>", "<INSERT_5_2_END>"))):
        v = a.get(key)
        if not s5:
            if v:
                errs.append(f"{key}: must be null — Section 5 is removed (section5_present is false)")
        elif v is None:
            if key != "s5_1_phase1":
                errs.append(f"{key}: required when Section 5 is present")
            else:
                ops.append(rb(s, e, []))  # no Phase 1 ESA: remove the empty 5.1 shell
        else:
            errs += check_blocks(key, v)
            ops.append(rb(s, e, v))

    v = a.get("s5_3_footprint")
    if not s5:
        if v:
            errs.append("s5_3_footprint: must be null — Section 5 is removed")
    elif v is None:
        errs.append("s5_3_footprint: required when Section 5 is present")
    else:
        errs += check_blocks("s5_3_footprint", v)
        # Delete the template's stale example paragraphs FIRST (before our text exists, so a prefix
        # match can never hit new text), by a 50-character prefix to survive hidden-whitespace/run splits.
        for t in stale_53_paragraphs(docx_path):
            ops.append({"op": "delete_paragraph", "text": " ".join(t.split())[:50], "exact": False, "after": "Chemistry Footprint", "before": "<INSERT_5_3_END>"})
        ops.append({"op": "insert_blocks", "placeholder": "<INSERT_5_3_START>", "blocks": v})
        ops.append({"op": "delete_paragraph", "text": "<INSERT_5_3_END>", "exact": True})

    errs += check_blocks("s8_summary", a.get("s8_summary"))
    ops.append(rb("<INSERT_8_START>", "<INSERT_8_END>", a.get("s8_summary") or []))

    pi = a.get("practitioner_information")
    if not isinstance(pi, dict) or not all(k in pi for k in ("check", "uncertain", "not_found", "incomplete")):
        errs.append("practitioner_information: must be an object with check/uncertain/not_found/incomplete lists")

    if errs:
        print("authored.json is invalid:\n  " + "\n  ".join(errs))
        sys.exit(1)
    json.dump(ops, open(ops_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    pi_path = os.path.join(os.path.dirname(os.path.abspath(ops_path)), "practitioner_info.json")
    json.dump(pi, open(pi_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"✓ {len(ops)} operation(s) -> {ops_path}; practitioner info -> {pi_path} (section5_present={s5})")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    main(*sys.argv[1:5])
