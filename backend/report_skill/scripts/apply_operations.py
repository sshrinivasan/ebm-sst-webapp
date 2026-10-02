#!/usr/bin/env python3
"""
apply_operations.py

Generic document operations script for the EBM SST report workflow.

Takes a DOCX and a JSON array of operations, executes each in order, and
saves the result. No domain-specific wording logic — Claude decides all
content and operation details; this script just executes them mechanically.

Usage:
    python3 apply_operations.py <input_docx> <operations_json> [output_docx]

Arguments:
    input_docx        DOCX to modify
    operations_json   Path to JSON file (or raw JSON string) with operations array
    output_docx       Optional output path. Defaults to overwriting the input.

────────────────────────────────────────────────────────────────────────────────
Supported operations
────────────────────────────────────────────────────────────────────────────────

1. replace_table_cells
   Find a table by anchor text, replace cell values identified by their row label.

   {
     "op": "replace_table_cells",
     "table_anchor": "text that uniquely identifies the table",
     "cells": [
       {"label": "Site Name",   "text": "Site 08-13-016-01 W4"},
       {"label": "Spud Date",   "text": "October 29, 1975 / March 15, 1983"},
       ...
     ]
   }

   How it works: searches each table for a cell whose text matches "label",
   then sets the text of the immediately following (non-identical) cell in
   the same row. Works for both merged-span rows (label → one wide value)
   and two-pair rows (label1 → val1, label2 → val2 in same row).
   Existing cell paragraph/run formatting is preserved.

2. insert_blocks
   Find a placeholder paragraph and replace it with styled content blocks,
   in the exact order given.

   {
     "op": "insert_blocks",
     "placeholder": "INSERT_EXAMPLE_HERE",
     "blocks": [
       {"style": "heading3", "text": "Background"},
       {"style": "body",     "text": "Four boreholes...", "bold": false},
       {"style": "body",     "text": "Summary of Results", "bold": true},
       {"style": "bullet",   "runs": [
           {"text": "EC soil rating categories ranged from the "},
           {"text": "Good", "bold": true},
           {"text": " to "},
           {"text": "Poor", "bold": true},
           {"text": " SCARG rating categories."}
       ]}
     ]
   }

   Use "text" (+ optional "bold": true for whole-paragraph bold) when there
   is no mixed bold within a line. Use "runs" for mixed bold/plain within
   one paragraph or bullet. Give one or the other, not both.

3. replace_text
   Simple find-and-replace across all paragraphs in the document body.

   {
     "op": "replace_text",
     "find": "old string",
     "replace": "new string"
   }

Other operations implemented below (see each op_<name> function's own
docstring for full details): delete_table, replace_between, strip_markers,
replace_table_rows, delete_paragraph, set_table_cells_by_position.

────────────────────────────────────────────────────────────────────────────────
Adding new operation types
────────────────────────────────────────────────────────────────────────────────
Add a function def op_<name>(doc, operation) -> bool, then register it in
OPERATIONS at the bottom of this file. The function receives the full Document
object and the operation dict; it should print a ✓ or ✗ status line and return
True/False. No EBM-specific logic should ever appear in this file.
"""

import copy
import json
import os
import random
import sys

from docx import Document
from docx.oxml import parse_xml

NSDECL = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'
)


def pid():
    return format(random.randint(0, 0xFFFFFFFF), "08X")


def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if text else ""


def resolve_bullet_style(doc):
    """Pick whichever bullet style exists in this template: Bullets → List Bullet → none."""
    style_names = {s.name for s in doc.styles}
    if "Bullets" in style_names:
        return "Bullets"
    if "List Bullet" in style_names:
        return "List Bullet"
    return None


# ── Operation: replace_table_cells ───────────────────────────────────────────

def set_cell_text(cell, text):
    """Set cell text, replacing all existing content with plain text."""
    from docx.oxml.ns import qn as _qn
    tc = cell._tc
    # Remove all paragraphs except the first (a cell must have at least one)
    paras = tc.findall(_qn("w:p"))
    for p in paras[1:]:
        tc.remove(p)
    # On the surviving paragraph, strip every inline element (runs, hyperlinks,
    # field codes, bookmarks, etc.) so nothing from the template bleeds through,
    # then add a single plain-text run.
    first_p = paras[0] if paras else tc.add_p()
    keep_tags = {_qn("w:pPr")}  # preserve paragraph properties (style, indent…)
    for child in list(first_p):
        if child.tag not in keep_tags:
            first_p.remove(child)
    from docx.oxml import parse_xml
    lines = str(text).split("\n") if text else [""]
    if len(lines) > 1:
        # Multi-line value: one run with <w:br/> between lines, left-aligned.
        ppr = first_p.find(_qn("w:pPr"))
        if ppr is None:
            ppr = parse_xml(f'<w:pPr {NSDECL}/>')
            first_p.insert(0, ppr)
        for jc in ppr.findall(_qn("w:jc")):
            ppr.remove(jc)
        ppr.append(parse_xml(f'<w:jc {NSDECL} w:val="left"/>'))
        inner = '<w:br/>'.join(f'<w:t xml:space="preserve">{esc(l)}</w:t>' for l in lines)
        first_p.append(parse_xml(f'<w:r {NSDECL}>{inner}</w:r>'))
        return
    first_p.append(
        parse_xml(
            f'<w:r {NSDECL}>'
            f'<w:t xml:space="preserve">{esc(text)}</w:t>'
            f'</w:r>'
        )
    )


def op_replace_table_cells(doc, operation):
    anchor = operation.get("table_anchor", "")
    cells_spec = operation.get("cells", [])

    # Strategy 1: find a paragraph whose text contains the anchor, then use
    # the immediately following table sibling in the document body.
    from docx.oxml.ns import qn as _qn
    target_table = None
    anchor_para_el = None  # track so we can remove it after filling
    skipped_marker_els = []  # placeholder-tag paragraphs skipped en route to the table
    body_children = list(doc.element.body)
    for i, child in enumerate(body_children):
        if not child.tag.endswith("}p"):
            continue
        para_text = "".join(r.text or "" for r in child.findall(".//" + _qn("w:t")))
        if anchor not in para_text:
            continue
        # Walk forward to find the next table sibling. A pure placeholder-tag
        # paragraph (e.g. "<INSERT_24_TABLE>") sitting between the anchor
        # heading and the table is skipped over rather than treated as a
        # stop condition — the new template inserts these marker paragraphs
        # right before several tables, and they shouldn't break the anchor
        # search when the real anchor text is the heading above them.
        pending_skips = []
        for j in range(i + 1, len(body_children)):
            sibling = body_children[j]
            if sibling.tag.endswith("}tbl"):
                from docx.table import Table as _Table
                target_table = _Table(sibling, doc)
                # Only delete the anchor if it's a pure placeholder tag (e.g. <INSERT_...>),
                # not a real heading like "Site Characteristics and Contaminant Sources".
                if para_text.strip().startswith("<") and para_text.strip().endswith(">"):
                    anchor_para_el = child
                skipped_marker_els = pending_skips
                break
            # Stop if we hit another non-empty paragraph — unless it's itself
            # a pure placeholder tag, in which case skip past it (and remove
            # it later once the table is confirmed) while continuing to look
            # for the table.
            if sibling.tag.endswith("}p"):
                sib_text = "".join(r.text or "" for r in sibling.findall(".//" + _qn("w:t")))
                sib_text_stripped = sib_text.strip()
                if sib_text_stripped:
                    if sib_text_stripped.startswith("<") and sib_text_stripped.endswith(">"):
                        pending_skips.append(sibling)
                    else:
                        break
        if target_table:
            break

    # Strategy 2 (fallback): find the table containing the anchor text in a cell
    if target_table is None:
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if anchor in cell.text:
                        target_table = table
                        break
                if target_table:
                    break
            if target_table:
                break

    if target_table is None:
        print(f"  ✗ No table found for anchor '{anchor}'")
        return False

    # Build label → value-cell map by scanning each row
    # For each cell, if its text differs from the next cell's text,
    # treat it as a label and map it to the next cell.
    label_to_cell = {}
    for row in target_table.rows:
        cells = row.cells
        for i in range(len(cells) - 1):
            label = cells[i].text.strip()
            next_text = cells[i + 1].text.strip()
            if label and label != next_text:
                # Only register the first occurrence (avoids overwriting with merged dupes)
                if label not in label_to_cell:
                    label_to_cell[label] = cells[i + 1]

    replaced, missing = [], []
    for spec in cells_spec:
        label = spec["label"]
        text = spec["text"]
        if label in label_to_cell:
            set_cell_text(label_to_cell[label], text)
            replaced.append(label)
        else:
            missing.append(label)

    # Remove the anchor paragraph (Strategy 1 only — Strategy 2 anchor lives inside a cell)
    if anchor_para_el is not None:
        doc.element.body.remove(anchor_para_el)
    # Remove any placeholder-tag marker paragraphs (e.g. "<INSERT_24_TABLE>")
    # that sat between the anchor heading and the table.
    for marker_el in skipped_marker_els:
        parent = marker_el.getparent()
        if parent is not None:
            parent.remove(marker_el)

    print(f"  ✓ replace_table_cells: {len(replaced)} updated ({', '.join(replaced)})")
    if missing:
        print(f"  ✗ Labels not found: {', '.join(missing)}")
    return True


# ── Operation: set_table_cells_by_position ───────────────────────────────────

def _locate_table_by_anchor(doc, anchor):
    """Shared table-location logic for replace_table_cells and
    set_table_cells_by_position: find a paragraph containing `anchor`, walk
    forward past any placeholder-tag marker paragraphs to the next table
    sibling (Strategy 1), or fall back to a table with `anchor` text inside
    one of its own cells (Strategy 2). Returns (table, anchor_para_el,
    skipped_marker_els) — the latter two are None/[] when found via
    Strategy 2, since there's no separate marker paragraph to clean up.
    """
    from docx.oxml.ns import qn as _qn
    target_table = None
    anchor_para_el = None
    skipped_marker_els = []
    body_children = list(doc.element.body)
    for i, child in enumerate(body_children):
        if not child.tag.endswith("}p"):
            continue
        para_text = "".join(r.text or "" for r in child.findall(".//" + _qn("w:t")))
        if anchor not in para_text:
            continue
        pending_skips = []
        for j in range(i + 1, len(body_children)):
            sibling = body_children[j]
            if sibling.tag.endswith("}tbl"):
                from docx.table import Table as _Table
                target_table = _Table(sibling, doc)
                if para_text.strip().startswith("<") and para_text.strip().endswith(">"):
                    anchor_para_el = child
                skipped_marker_els = pending_skips
                break
            if sibling.tag.endswith("}p"):
                sib_text = "".join(r.text or "" for r in sibling.findall(".//" + _qn("w:t")))
                sib_text_stripped = sib_text.strip()
                if sib_text_stripped:
                    if sib_text_stripped.startswith("<") and sib_text_stripped.endswith(">"):
                        pending_skips.append(sibling)
                    else:
                        break
        if target_table:
            break

    if target_table is None:
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if anchor in cell.text:
                        target_table = table
                        break
                if target_table:
                    break
            if target_table:
                break

    return target_table, anchor_para_el, skipped_marker_els


def op_set_table_cells_by_position(doc, operation):
    """
    Find a table by anchor text (same anchor-search rules as
    replace_table_cells: a marker/heading paragraph immediately before the
    table, skipping over any `<INSERT_...>` marker paragraphs in between),
    then set individual cell text by (row, col) position instead of by row
    label.

    Use this instead of replace_table_cells whenever the table has more
    than one row sharing the same label text in its first column — label
    lookup only ever finds the first match, so a second row with the same
    label silently never gets updated. E.g. a table with "Direct soil
    contact" appearing once under a "Human" group and again under an
    "Ecological" group (see Section 2.8's exposure-pathway tables).

    Row/column indices are 0-based and count every actual <w:tr>/<w:tc> in
    the table, including the header row and any merged/grouping rows (a
    merged row like "Human" spanning all columns is still just row N — it's
    never a target itself, since this op only ever writes to specific
    (row, col) pairs the caller supplies). The caller (Claude) is expected
    to know the table's fixed row layout, since these are static template
    tables whose structure doesn't change per site.

    {
      "op": "set_table_cells_by_position",
      "table_anchor": "<INSERT_28_AG_ALL_TABLE>",
      "cells": [
        {"row": 4,  "col": 1, "text": "chloride*"},
        {"row": 6,  "col": 1, "text": "EC, SAR, pH, chloride*"},
        {"row": 2,  "col": 1, "text": ""}
      ]
    }
    """
    target_table, anchor_para_el, skipped_marker_els = _locate_table_by_anchor(
        doc, operation.get("table_anchor", "")
    )

    if target_table is None:
        print(f"  ✗ No table found for anchor '{operation.get('table_anchor', '')}'")
        return False

    rows = target_table.rows
    set_count, missing = 0, []
    for spec in operation.get("cells", []):
        r, c, text = spec["row"], spec["col"], spec.get("text", "")
        if r >= len(rows) or c >= len(rows[r].cells):
            missing.append((r, c))
            continue
        set_cell_text(rows[r].cells[c], text)
        set_count += 1

    if anchor_para_el is not None:
        doc.element.body.remove(anchor_para_el)
    for marker_el in skipped_marker_els:
        parent = marker_el.getparent()
        if parent is not None:
            parent.remove(marker_el)

    print(f"  ✓ set_table_cells_by_position: {set_count} cell(s) updated")
    if missing:
        print(f"  ✗ Out-of-range (row, col) pairs: {missing}")
    return True


# ── Operation: insert_blocks ─────────────────────────────────────────────────

def build_runs_xml(block):
    if block.get("runs"):
        runs = block["runs"]
    else:
        runs = [{"text": block.get("text", ""), "bold": block.get("bold", False)}]
    parts = []
    for r in runs:
        rpr = "<w:rPr><w:b/></w:rPr>" if r.get("bold") else ""
        parts.append(
            f'<w:r>{rpr}<w:t xml:space="preserve">{esc(r.get("text", ""))}</w:t></w:r>'
        )
    return "".join(parts)


def build_block_element(block, bullet_style):
    style = block.get("style", "body")
    runs_xml = build_runs_xml(block)

    if style == "heading3":
        pPr = '<w:pPr><w:pStyle w:val="Heading3"/></w:pPr>'
    elif style == "smalltitle":
        # "Small Titles" Word style (style ID "SmallTitles") — used for
        # "Summary of Results" sub-headers in Section 4.2+ areas. Confirmed
        # against the live template's own "Summary of Results" paragraphs
        # (e.g. Section 4.2.1's), which use this style rather than bold body
        # text.
        pPr = '<w:pPr><w:pStyle w:val="SmallTitles"/></w:pPr>'
    elif style == "bullet":
        pPr = f'<w:pPr><w:pStyle w:val="{bullet_style}"/></w:pPr>' if bullet_style else ""
    else:  # "body"
        pPr = ""

    return parse_xml(
        f'<w:p {NSDECL} w14:paraId="{pid()}" w14:textId="{pid()}">'
        f"{pPr}{runs_xml}</w:p>"
    )


def op_insert_blocks(doc, operation):
    placeholder_text = operation.get("placeholder", "")
    blocks = operation.get("blocks", [])
    bullet_style = resolve_bullet_style(doc)

    body = doc.element.body
    placeholder = None
    for para in doc.paragraphs:
        if placeholder_text in para.text:
            placeholder = para._element
            break

    if placeholder is None:
        print(f"  ✗ Placeholder '{placeholder_text}' not found")
        return False

    idx = list(body).index(placeholder)
    for i, block in enumerate(blocks):
        body.insert(idx + i, build_block_element(block, bullet_style))
    body.remove(placeholder)

    print(f"  ✓ insert_blocks at '{placeholder_text}': {len(blocks)} block(s) inserted")
    return True


# ── Operation: delete_table ──────────────────────────────────────────────────

def op_delete_table(doc, operation):
    """
    Find a placeholder paragraph whose text contains `placeholder`, then remove
    both that paragraph and the immediately following table sibling from the
    document body.

    Optional: set "remove_preceding_heading": true to also remove the nearest
    non-empty paragraph that precedes the placeholder (typically a section
    heading like "Facility" that belongs to the same block being deleted).

    {
      "op": "delete_table",
      "placeholder": "<INSERT_FACILITY_TABLE>",
      "remove_preceding_heading": true
    }
    """
    from docx.oxml.ns import qn as _qn
    placeholder_text = operation.get("placeholder", "")
    remove_heading = operation.get("remove_preceding_heading", False)
    body = doc.element.body
    bc = list(body)

    para_el = None
    table_el = None
    para_idx = None
    for i, child in enumerate(bc):
        if not child.tag.endswith("}p"):
            continue
        texts = "".join(r.text or "" for r in child.findall(".//" + _qn("w:t")))
        if placeholder_text not in texts:
            continue
        para_el = child
        para_idx = i
        # Find the next table sibling
        for j in range(i + 1, len(bc)):
            sibling = bc[j]
            if sibling.tag.endswith("}tbl"):
                table_el = sibling
                break
            # Stop if a non-empty paragraph intervenes
            if sibling.tag.endswith("}p"):
                sib_text = "".join(r.text or "" for r in sibling.findall(".//" + _qn("w:t")))
                if sib_text.strip():
                    break
        break

    if para_el is None:
        print(f"  ✗ Placeholder paragraph '{placeholder_text}' not found")
        return False

    # Optionally remove the preceding heading (walk backward to nearest non-empty para)
    heading_el = None
    if remove_heading and para_idx is not None:
        for k in range(para_idx - 1, -1, -1):
            candidate = bc[k]
            if candidate.tag.endswith("}p"):
                ctext = "".join(r.text or "" for r in candidate.findall(".//" + _qn("w:t")))
                if ctext.strip():
                    heading_el = candidate
                    break

    body.remove(para_el)
    if table_el is not None:
        body.remove(table_el)
    if heading_el is not None:
        body.remove(heading_el)
        print(f"  ✓ delete_table: removed heading, placeholder '{placeholder_text}', and its table")
    elif table_el is not None:
        print(f"  ✓ delete_table: removed placeholder '{placeholder_text}' and its table")
    else:
        print(f"  ✓ delete_table: removed placeholder '{placeholder_text}' (no following table found)")
    return True


# ── Operation: replace_between ───────────────────────────────────────────────

def op_replace_between(doc, operation):
    """
    Find the paragraph containing `start_placeholder`, find the paragraph
    containing `end_placeholder`, remove both markers and everything between
    them, then insert the given blocks at that position.

    {
      "op": "replace_between",
      "start_placeholder": "<INSERT_EXEC_SUMMARY_START>",
      "end_placeholder":   "<INSERT_EXEC_SUMMARY_END>",
      "blocks": [
        {"style": "body", "text": "..."}
      ]
    }
    """
    from docx.oxml.ns import qn as _qn
    start_text = operation.get("start_placeholder", "")
    end_text   = operation.get("end_placeholder", "")
    blocks     = operation.get("blocks", [])
    bullet_style = resolve_bullet_style(doc)

    body = doc.element.body
    bc   = list(body)

    start_el = end_el = None
    for child in bc:
        texts = "".join(r.text or "" for r in child.findall(".//" + _qn("w:t")))
        if start_el is None and start_text in texts:
            start_el = child
        elif start_el is not None and end_text in texts:
            end_el = child
            break

    if start_el is None:
        print(f"  ✗ Start placeholder '{start_text}' not found")
        return False
    if end_el is None:
        print(f"  ✗ End placeholder '{end_text}' not found")
        return False

    start_idx = bc.index(start_el)
    end_idx   = bc.index(end_el)

    # Remove everything from start_el through end_el (inclusive), first rescuing
    # any heading bookmark (TOC anchor) that lives inside the removed range.
    rescue_orphan_bookmarks(bc[start_idx : end_idx + 1], end_el.getnext())
    for child in bc[start_idx : end_idx + 1]:
        body.remove(child)

    # Insert new blocks at the position where start_el was
    for i, block in enumerate(blocks):
        body.insert(start_idx + i, build_block_element(block, bullet_style))

    print(f"  ✓ replace_between '{start_text}'…'{end_text}': {len(blocks)} block(s) inserted")
    return True


# ── Operation: replace_text ───────────────────────────────────────────────────

def op_replace_text(doc, operation):
    find = operation.get("find", "")
    replace = operation.get("replace", "")
    count = 0
    for para in doc.paragraphs:
        if find in para.text:
            for run in para.runs:
                if find in run.text:
                    run.text = run.text.replace(find, replace)
                    count += 1
    print(f"  ✓ replace_text: '{find}' → '{replace}' ({count} instance(s))")
    return True


def _move_bookmark_starts(src_el, dst_el):
    """Move every w:bookmarkStart in `src_el` to the start of paragraph `dst_el`
    (just after its w:pPr) so that deleting `src_el` does not orphan a bookmarkEnd."""
    from docx.oxml.ns import qn as _qn
    if src_el is None or dst_el is None or not dst_el.tag.endswith("}p"):
        return 0
    starts = list(src_el.iter(_qn("w:bookmarkStart")))
    if not starts:
        return 0
    pos = 1 if (len(dst_el) and dst_el[0].tag == _qn("w:pPr")) else 0
    for b in starts:
        b.getparent().remove(b)
        dst_el.insert(pos, b)
        pos += 1
    return len(starts)


def rescue_orphan_bookmarks(removed_els, dst_el):
    """Before deleting `removed_els` (marker paragraphs / a block), move every
    w:bookmarkStart whose matching w:bookmarkEnd is NOT also being deleted into
    the paragraph `dst_el` (just after its w:pPr). Without this, a heading's
    TOC/cross-reference bookmark that Word parked in a marker paragraph is lost
    and the Table of Contents link for that heading stops working."""
    from docx.oxml.ns import qn as _qn
    if dst_el is None or not dst_el.tag.endswith("}p"):
        return 0
    removed_ids = set()
    for el in removed_els:
        for be in el.iter(_qn("w:bookmarkEnd")):
            removed_ids.add(be.get(_qn("w:id")))
    moved = 0
    pos = 1 if (len(dst_el) and dst_el[0].tag == _qn("w:pPr")) else 0
    for el in removed_els:
        for b in list(el.iter(_qn("w:bookmarkStart"))):
            if b.get(_qn("w:id")) in removed_ids:
                continue
            b.getparent().remove(b)
            dst_el.insert(pos, b)
            pos += 1
            moved += 1
    return moved


# ── Operation: strip_markers ─────────────────────────────────────────────────

def op_strip_markers(doc, operation):
    """
    Remove the start and end marker paragraphs, leaving everything between
    them (headings, tables, body paragraphs) untouched.

    Use this when a section is present and should be kept: strip the
    wrapping placeholders, then fill the table with replace_table_cells.
    For deletion, use replace_between with "blocks": [] instead.

    {
      "op": "strip_markers",
      "start_placeholder": "<INSERT_WELLSITE_START>",
      "end_placeholder":   "<INSERT_WELLSITE_END>"
    }
    """
    from docx.oxml.ns import qn as _qn
    start_text = operation.get("start_placeholder", "")
    end_text   = operation.get("end_placeholder", "")
    body = doc.element.body
    bc   = list(body)

    start_el = end_el = None
    for child in bc:
        texts = "".join(r.text or "" for r in child.findall(".//" + _qn("w:t")))
        if start_el is None and start_text in texts:
            start_el = child
        elif start_el is not None and end_text in texts:
            end_el = child
            break

    if start_el is None:
        print(f"  ✗ Start marker '{start_text}' not found")
        return False
    if end_el is None:
        print(f"  ✗ End marker '{end_text}' not found")
        return False

    # Word sometimes parks a heading's bookmarkStart (TOC/cross-reference anchors)
    # inside the marker paragraph that sits just above the heading. Removing the
    # marker would delete the anchor and break the TOC link, so move those
    # bookmarkStart elements into the next paragraph (the heading) first.
    _move_bookmark_starts(start_el, start_el.getnext())
    _move_bookmark_starts(end_el, end_el.getnext())
    body.remove(start_el)
    body.remove(end_el)
    print(f"  ✓ strip_markers: removed '{start_text}' and '{end_text}'")
    return True


# ── Operation: delete_paragraph ──────────────────────────────────────────────

def op_delete_paragraph(doc, operation):
    """
    Remove a single paragraph matching `text`, optionally bounded to only
    search between an `after` and `before` marker (matched by substring, same
    scan style as replace_between/strip_markers). Use the bounds whenever
    `text` alone isn't unique enough in the whole document to safely target
    one paragraph (e.g. a short divider line like "OR" that could appear as
    a substring elsewhere) — after/before scope the search to one known
    region instead of the first match anywhere in the body.

    Match is exact (paragraph's full trimmed text equals `text`) by default;
    pass "exact": false for a substring match instead.

    {
      "op": "delete_paragraph",
      "text": "OR",
      "after": "<INSERT_1_2_1_START>",
      "before": "<INSERT_1_2_1_END>"
    }
    """
    from docx.oxml.ns import qn as _qn
    target      = operation.get("text", "")
    after_text  = operation.get("after")
    before_text = operation.get("before")
    exact       = operation.get("exact", True)

    body = doc.element.body
    bc   = list(body)

    lo, hi = 0, len(bc)
    if after_text:
        for i, child in enumerate(bc):
            texts = "".join(r.text or "" for r in child.findall(".//" + _qn("w:t")))
            if after_text in texts:
                lo = i + 1
                break
        else:
            print(f"  ✗ delete_paragraph: 'after' marker '{after_text}' not found")
            return False
    if before_text:
        for i in range(lo, len(bc)):
            texts = "".join(r.text or "" for r in bc[i].findall(".//" + _qn("w:t")))
            if before_text in texts:
                hi = i
                break
        else:
            print(f"  ✗ delete_paragraph: 'before' marker '{before_text}' not found")
            return False

    match_el = None
    for child in bc[lo:hi]:
        if not child.tag.endswith("}p"):
            continue
        texts = "".join(r.text or "" for r in child.findall(".//" + _qn("w:t")))
        is_match = (texts.strip() == target) if exact else (target in texts)
        if is_match:
            match_el = child
            break

    if match_el is None:
        scope = f" between '{after_text}' and '{before_text}'" if (after_text or before_text) else ""
        print(f"  ✗ delete_paragraph: no paragraph matching '{target}'{scope}")
        return False

    rescue_orphan_bookmarks([match_el], match_el.getnext())
    body.remove(match_el)
    print(f"  ✓ delete_paragraph: removed '{target}'")
    return True


# ── Operation: replace_table_rows ────────────────────────────────────────────

def op_replace_table_rows(doc, operation):
    """
    Find a table that immediately follows the placeholder paragraph, keep the
    first `header_rows` rows intact, remove all remaining data rows, and append
    new rows from the `rows` array.  The placeholder paragraph is also removed.

    {
      "op": "replace_table_rows",
      "table_anchor": "<INSERT_3_2_SCARG_TABLE>",
      "header_rows": 3,
      "rows": [
        ["0.0–0.3", "Topsoil", "Good", "Good", "2", "4"],
        ...
      ]
    }

    A cell value can also be a dict {"lines": [{"text": "...", "bold": bool},
    ...]} instead of a plain string, to write more than one paragraph into
    that cell (e.g. a bold year on one line, a non-bold reference below it —
    see prompts/s1_2_1_previous_assessments.md). Each entry becomes its own
    paragraph, in order, cloning the cell's own template paragraph for
    formatting (alignment etc.) rather than only ever writing into the first
    paragraph the way the plain-string case does.

    Formatting (font, size, color, shading-aware text color, etc.) is
    inherited automatically from whatever is already on the template's own
    row/cell — the row this function clones its new rows from. A plain-string
    cell's existing run(s) are reused outright (only the text changes), and a
    multi-line cell's new runs start from a deep copy of the template cell's
    own paragraph(s)' run formatting, matched by bold-ness (so a template
    with a bold "year" line and a non-bold "reference" line underneath it
    gives each replacement line the right one of those two styles — see the
    first column of the 1.2.1 previous-assessments table, whose cell is
    shaded dark green with existing white run text: new rows written there
    come out white automatically, with no formatting fields needed in the
    operation JSON at all).

    Only use the optional overrides below when there's no representative
    template row to inherit from, or to deliberately deviate from it. Every
    other `replace_table_rows` call (e.g. SCARG) is unaffected either way,
    since both are no-ops when omitted:
    - An operation-level "cell_font" field ({"name", "size_pt", "align"})
      overrides font/size/alignment for every run this operation writes.
    - A per-line "color" (hex string, no '#', e.g. "FFFFFF") inside a
      "lines" entry overrides just that line's text color.

    {
      "op": "replace_table_rows",
      "table_anchor": "...",
      "cell_font": {"name": "Arial", "size_pt": 9.5, "align": "left"},
      "rows": [...]
    }
    """
    from docx.oxml.ns import qn as _qn
    import copy as _copy

    anchor_text = operation.get("table_anchor", "")
    header_rows = int(operation.get("header_rows", 1))
    new_rows    = operation.get("rows", [])
    cell_font   = operation.get("cell_font")  # optional {"name","size_pt","align"}

    body = doc.element.body
    bc   = list(body)

    # Find anchor paragraph
    anchor_el = None
    anchor_idx = None
    for i, child in enumerate(bc):
        if not child.tag.endswith("}p"):
            continue
        texts = "".join(r.text or "" for r in child.findall(".//" + _qn("w:t")))
        if anchor_text in texts:
            anchor_el  = child
            anchor_idx = i
            break

    if anchor_el is None:
        print(f"  ✗ replace_table_rows: anchor '{anchor_text}' not found")
        return False

    # Find the immediately following table sibling
    tbl_el = None
    for j in range(anchor_idx + 1, len(bc)):
        sibling = bc[j]
        if sibling.tag.endswith("}tbl"):
            tbl_el = sibling
            break
        # skip empty paragraphs
        if sibling.tag.endswith("}p"):
            sib_text = "".join(r.text or "" for r in sibling.findall(".//" + _qn("w:t")))
            if sib_text.strip():
                break  # non-empty paragraph intervenes

    if tbl_el is None:
        print(f"  ✗ replace_table_rows: no table found after anchor '{anchor_text}'")
        return False

    # Work with the python-docx Table wrapper to access rows
    for tbl_wrapper in doc.tables:
        if tbl_wrapper._tbl is tbl_el:
            tbl = tbl_wrapper
            break
    else:
        print(f"  ✗ replace_table_rows: could not find Table wrapper for tbl element")
        return False

    # Grab a template data row (first row after header) to clone for formatting
    all_rows = tbl.rows
    if len(all_rows) <= header_rows:
        template_row_el = all_rows[-1]._tr  # fall back to last header row
    else:
        template_row_el = all_rows[header_rows]._tr

    # Remove all existing data rows (rows after header_rows)
    tr_elements = tbl_el.findall(_qn("w:tr"))
    for tr in tr_elements[header_rows:]:
        tbl_el.remove(tr)

    from lxml import etree

    def _rpr_insert_ordered(rPr, tag, schema_order):
        """Find-or-create a child of the given tag inside rPr, inserting it
        at the position required by CT_RPr's schema order (a short prefix
        of the full sequence is enough here: rFonts, b, bCs, color, sz,
        szCs — the only tags this function ever writes). Returns the
        element so callers can set attributes on it."""
        local = tag.split(":", 1)[-1]
        existing = rPr.find(_qn(tag))
        if existing is not None:
            return existing
        el = etree.Element(_qn(tag))
        my_pos = schema_order.index(local)
        insert_before = None
        for child in rPr:
            child_tag = etree.QName(child).localname
            if child_tag in schema_order and schema_order.index(child_tag) > my_pos:
                insert_before = child
                break
        if insert_before is not None:
            insert_before.addprevious(el)
        else:
            rPr.append(el)
        return el

    _RPR_ORDER = ["rFonts", "b", "bCs", "color", "sz", "szCs"]

    def _apply_font_override(r_el, font_name=None, size_pt=None, color=None):
        """Set/replace rFonts, color, and sz/szCs on a run's rPr, in the
        schema order CT_RPr requires (rFonts, b, bCs, color, sz, szCs).
        No-op for any argument left as None, so callers can apply just a
        color, just a font, or both."""
        if font_name is None and size_pt is None and color is None:
            return
        rPr = r_el.find(_qn("w:rPr"))
        if rPr is None:
            rPr = etree.Element(_qn("w:rPr"))
            r_el.insert(0, rPr)
        if font_name is not None:
            rFonts = _rpr_insert_ordered(rPr, "w:rFonts", _RPR_ORDER)
            for attr in ("w:ascii", "w:hAnsi", "w:cs"):
                rFonts.set(_qn(attr), font_name)
        if color is not None:
            color_el = _rpr_insert_ordered(rPr, "w:color", _RPR_ORDER)
            color_el.set(_qn("w:val"), color)
        if size_pt is not None:
            half_points = str(int(round(size_pt * 2)))
            for tag in ("w:sz", "w:szCs"):
                el = _rpr_insert_ordered(rPr, tag, _RPR_ORDER)
                el.set(_qn("w:val"), half_points)

    def _apply_paragraph_align(p_el, align):
        """Set w:pPr/w:jc to `align` (e.g. 'left', 'center'). No-op if
        align is None; leaves any other pPr children untouched. Per the
        OOXML schema, w:pPr's optional w:rPr (paragraph-mark run
        properties) must be its LAST child, after w:jc — so a new w:jc is
        inserted before any existing w:rPr rather than simply appended."""
        if align is None:
            return
        pPr = p_el.find(_qn("w:pPr"))
        if pPr is None:
            pPr = etree.Element(_qn("w:pPr"))
            p_el.insert(0, pPr)
        jc = pPr.find(_qn("w:jc"))
        if jc is None:
            jc = etree.Element(_qn("w:jc"))
            rPr = pPr.find(_qn("w:rPr"))
            if rPr is not None:
                rPr.addprevious(jc)
            else:
                pPr.append(jc)
        jc.set(_qn("w:val"), align)

    def _apply_bold(rPr, bold):
        """Add or remove <w:b/> (and its complex-script twin <w:bCs/>) on
        an existing rPr, in place, without disturbing any other formatting
        already on it (color, rFonts, etc. from the inherited template)."""
        b_el = rPr.find(_qn("w:b"))
        bCs_el = rPr.find(_qn("w:bCs"))
        if bold:
            if b_el is None:
                _rpr_insert_ordered(rPr, "w:b", _RPR_ORDER)
        else:
            if b_el is not None:
                rPr.remove(b_el)
            if bCs_el is not None:
                rPr.remove(bCs_el)

    def _add_run(p_el, text, bold, font_name=None, size_pt=None, color=None, base_rpr=None):
        """Append a run with `text`. When `base_rpr` is given (a deep copy
        of a template run's rPr — see `_capture_line_templates`), the new
        run starts from that formatting (font/color/lang/etc. all
        inherited as-is) and only its bold state is adjusted to match
        `bold`; explicit font_name/size_pt/color, when given, are applied
        on top as overrides. With no base_rpr, only bold is set (old
        no-template-to-inherit-from behavior)."""
        r_el = etree.SubElement(p_el, _qn("w:r"))
        if base_rpr is not None:
            rPr = _copy.deepcopy(base_rpr)
            r_el.append(rPr)
            _apply_bold(rPr, bold)
        elif bold:
            rPr = etree.SubElement(r_el, _qn("w:rPr"))
            etree.SubElement(rPr, _qn("w:b"))
        t_el = etree.SubElement(r_el, _qn("w:t"))
        t_el.text = text
        _apply_font_override(r_el, font_name, size_pt, color)

    def _capture_line_templates(tc):
        """Deep-copy each existing paragraph's first run's rPr in `tc`,
        paired with whether that run is currently bold. These become the
        formatting base for the lines that replace them, so a cell's own
        pre-existing font/color/etc. (e.g. white text on a shaded column)
        is inherited automatically — the operation JSON doesn't need to
        respecify it unless it wants to override it."""
        templates = []
        for p_el in tc.findall(_qn("w:p")):
            run = p_el.find(_qn("w:r"))
            if run is None:
                continue
            rPr = run.find(_qn("w:rPr"))
            is_bold = rPr is not None and rPr.find(_qn("w:b")) is not None
            templates.append((is_bold, _copy.deepcopy(rPr) if rPr is not None else None))
        return templates

    def _base_rpr_for(templates, bold):
        """Pick a captured template rPr to use as the base for a line with
        the given bold-ness: prefer an exact bold match (e.g. the
        template's own bold "year" line vs. its non-bold "reference"
        line), otherwise adapt whichever template exists — its bold flag
        gets corrected by `_apply_bold` in `_add_run`."""
        if not templates:
            return None
        for is_bold, rPr in templates:
            if is_bold == bold and rPr is not None:
                return _copy.deepcopy(rPr)
        for is_bold, rPr in templates:
            if rPr is not None:
                return _copy.deepcopy(rPr)
        return None

    def _write_multiline_cell(tc, lines):
        """Rewrite tc as one paragraph per entry in `lines`, each a run
        whose formatting is inherited from the template cell's own
        existing paragraph(s) (see `_capture_line_templates`/
        `_base_rpr_for`) — so a shaded column's existing white text stays
        white, etc., with no need to spell that out in the operation JSON.
        Clones the cell's own first paragraph (for its pPr — alignment
        etc.) for every extra line beyond the first. An operation-level
        `cell_font` (name/size/align) or a per-line "color", when given,
        override the inherited formatting rather than replacing it
        outright."""
        font_name = cell_font.get("name") if cell_font else None
        size_pt   = cell_font.get("size_pt") if cell_font else None
        align     = cell_font.get("align") if cell_font else None

        templates = _capture_line_templates(tc)

        paragraphs = tc.findall(_qn("w:p"))
        if not paragraphs:
            return
        para_template = _copy.deepcopy(paragraphs[0])
        for p_el in paragraphs[1:]:
            tc.remove(p_el)
        first_p = tc.findall(_qn("w:p"))[0]
        for r_el in list(first_p.findall(_qn("w:r"))):
            first_p.remove(r_el)
        if lines:
            first_line = lines[0]
            first_bold = first_line.get("bold", False)
            _add_run(first_p, first_line.get("text", ""), first_bold,
                     font_name, size_pt, first_line.get("color"),
                     _base_rpr_for(templates, first_bold))
            _apply_paragraph_align(first_p, align)
        prev_p = first_p
        for line in lines[1:]:
            new_p = _copy.deepcopy(para_template)
            for r_el in list(new_p.findall(_qn("w:r"))):
                new_p.remove(r_el)
            line_bold = line.get("bold", False)
            _add_run(new_p, line.get("text", ""), line_bold,
                     font_name, size_pt, line.get("color"),
                     _base_rpr_for(templates, line_bold))
            _apply_paragraph_align(new_p, align)
            prev_p.addnext(new_p)
            prev_p = new_p

    # Build and append new rows
    for row_values in new_rows:
        new_tr = _copy.deepcopy(template_row_el)
        tc_els = new_tr.findall(_qn("w:tc"))
        for col_idx, cell_value in enumerate(row_values):
            if col_idx >= len(tc_els):
                break
            tc = tc_els[col_idx]
            if isinstance(cell_value, dict) and "lines" in cell_value:
                _write_multiline_cell(tc, cell_value["lines"])
                continue
            # Plain-string case: text is swapped into the template's own
            # existing run(s) without touching rPr at all, so formatting is
            # inherited automatically. cell_font (name/size/align), if
            # given, still applies as an explicit override on top.
            cell_text = cell_value
            font_name = cell_font.get("name") if cell_font else None
            size_pt   = cell_font.get("size_pt") if cell_font else None
            align     = cell_font.get("align") if cell_font else None
            for p_el in tc.findall(_qn("w:p")):
                _apply_paragraph_align(p_el, align)
                for r_el in p_el.findall(_qn("w:r")):
                    t_els = r_el.findall(_qn("w:t"))
                    if t_els:
                        t_els[0].text = cell_text
                        cell_text = ""  # remaining runs get empty
                    else:
                        # Build a w:t element
                        t_el = etree.SubElement(r_el, _qn("w:t"))
                        t_el.text = cell_text
                        cell_text = ""
                    _apply_font_override(r_el, font_name, size_pt, None)
        tbl_el.append(new_tr)

    # Remove the anchor paragraph
    body.remove(anchor_el)

    print(f"  ✓ replace_table_rows: anchor '{anchor_text}' removed, {len(new_rows)} data row(s) written")
    return True


# ── Dispatch ──────────────────────────────────────────────────────────────────

OPERATIONS = {
    "replace_table_cells": op_replace_table_cells,
    "insert_blocks":       op_insert_blocks,
    "replace_between":     op_replace_between,
    "replace_text":        op_replace_text,
    "delete_table":        op_delete_table,
    "strip_markers":       op_strip_markers,
    "replace_table_rows":  op_replace_table_rows,
    "delete_paragraph":    op_delete_paragraph,
    "set_table_cells_by_position": op_set_table_cells_by_position,
}


def check_remaining_placeholders(doc):
    """Scan the saved document for any INSERT_ placeholders that were not handled."""
    import re
    from docx.oxml.ns import qn as _qn
    pattern = re.compile(r'INSERT_\w+')
    found = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if pattern.search(text):
            found.append(text[:80])
    # Also check table cells
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if pattern.search(text):
                    found.append(f"[table cell] {text[:80]}")
    return found


def apply_operations(input_docx, operations, output_docx=None):
    if output_docx is None:
        output_docx = input_docx

    doc = Document(input_docx)
    ok = True

    for i, op in enumerate(operations):
        op_type = op.get("op", "")
        print(f"\n[{i + 1}/{len(operations)}] {op_type}")
        if op_type not in OPERATIONS:
            print(f"  ✗ Unknown operation type: '{op_type}'")
            ok = False
            continue
        if not OPERATIONS[op_type](doc, op):
            ok = False

    doc.save(output_docx)
    print(f"\n✓ Saved: {output_docx}")

    # Post-run validation: fail loudly if any placeholders remain
    remaining = check_remaining_placeholders(doc)
    if remaining:
        print(f"\n{'='*70}")
        print(f"✗ UNFILLED PLACEHOLDERS ({len(remaining)}) — document is incomplete:")
        for p in remaining:
            print(f"  • {p}")
        print(f"{'='*70}")
        ok = False
    else:
        print("\n✓ Validation passed: no unfilled placeholders remain.")

    return ok


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 apply_operations.py <input_docx> <operations_json> [output_docx]")
        sys.exit(1)

    input_docx = sys.argv[1]
    json_arg = sys.argv[2]
    output_docx = sys.argv[3] if len(sys.argv) > 3 else None

    if os.path.exists(json_arg):
        with open(json_arg) as f:
            operations = json.load(f)
    else:
        operations = json.loads(json_arg)

    print("=" * 70)
    print("APPLY DOCUMENT OPERATIONS")
    print("=" * 70)
    print(f"  Input:      {input_docx}")
    print(f"  Output:     {output_docx or input_docx}")
    print(f"  Operations: {len(operations)}")

    success = apply_operations(input_docx, operations, output_docx)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
