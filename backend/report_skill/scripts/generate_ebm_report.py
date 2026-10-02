#!/usr/bin/env python3
"""
EBM Routine P2 Environmental Report Generator

This script implements the complete workflow for generating an EBM Phase 2 ESA report
by merging environmental data from Excel with a Word template, guided by a prompt library.
"""

import copy
import io
import re
import os
import zipfile
from collections import OrderedDict, defaultdict
from datetime import datetime
import openpyxl
import sys
from docx import Document
from docx.shared import Inches
from docx.oxml import parse_xml
from lxml import etree

def esc(text):
    """Escape text for XML."""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def format_date(date_str):
    """Convert YYYY-MM-DD or DD-Mmm-YY to 'Month DD, YYYY'."""
    if not date_str:
        return ""
    date_str = date_str.strip()
    for fmt in ["%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%B %d, %Y").replace(" 0", " ")
        except:
            continue
    return date_str

def format_num(val):
    """Format number - integer if whole, 1 decimal place if float."""
    if val is None:
        return "0"
    if isinstance(val, (int, float)):
        if isinstance(val, float) and val != int(val):
            return f"{val:.1f}"
        return str(int(val))
    return str(val)

def format_val(val):
    """Format a cell value for display - preserve strings, clean up floats."""
    if val is None:
        return ""
    if isinstance(val, float):
        if val == int(val):
            return str(int(val))
        # Use up to 3 significant decimal places, strip trailing zeros
        return f"{val:.3g}"
    return str(val)

def number_to_word(n):
    """Convert number to word form."""
    words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
             6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten",
             11: "Eleven", 12: "Twelve"}
    return words.get(n, str(n))

def set_tc_text(tc, text):
    """Replace text in a table cell while preserving paragraph and run formatting."""
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    # Grab the existing paragraph's <w:pPr> and first run's <w:rPr> before removing anything
    existing_p = tc.find(f'{{{ns}}}p')
    existing_pPr = None
    existing_rPr = None
    if existing_p is not None:
        pPr = existing_p.find(f'{{{ns}}}pPr')
        if pPr is not None:
            existing_pPr = copy.deepcopy(pPr)
        # Grab run properties from the first run (carries font size, bold, etc.)
        first_r = existing_p.find(f'{{{ns}}}r')
        if first_r is not None:
            rPr = first_r.find(f'{{{ns}}}rPr')
            if rPr is not None:
                existing_rPr = copy.deepcopy(rPr)
    # Remove all existing paragraphs
    for p in list(tc.findall(f'{{{ns}}}p')):
        tc.remove(p)
    # Build a new paragraph, re-attaching the original formatting
    p = etree.SubElement(tc, f'{{{ns}}}p')
    if existing_pPr is not None:
        p.insert(0, existing_pPr)
    r = etree.SubElement(p, f'{{{ns}}}r')
    if existing_rPr is not None:
        r.insert(0, existing_rPr)
    t = etree.SubElement(r, f'{{{ns}}}t')
    t.text = str(text) if text is not None else ''
    if t.text != t.text.strip():
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

def clear_row_top_border(tr):
    """Set top border to nil on every cell in a table row (removes visible line above the row)."""
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    for tc in tr.findall(f'{{{ns}}}tc'):
        tcPr = tc.find(f'{{{ns}}}tcPr')
        if tcPr is None:
            continue
        tcBorders = tcPr.find(f'{{{ns}}}tcBorders')
        if tcBorders is None:
            continue
        top = tcBorders.find(f'{{{ns}}}top')
        if top is not None:
            top.set(f'{{{ns}}}val', 'nil')
            # Remove size/space/color attrs that are meaningless for nil
            for attr in [f'{{{ns}}}sz', f'{{{ns}}}space', f'{{{ns}}}color']:
                if top.get(attr) is not None:
                    del top.attrib[attr]

def generate_cover_page(doc, references_folder, site_lsd=None, client_name=None):
    """
    Fill in cover page markers that live inside table cells.

    Markers (added by user to the template cover table):
      <INSERT_TITLE_START> / <INSERT_TITLE_END>    — row 1
      <INSERT_CLIENT_START> / <INSERT_CLIENT_END>   — row 2
      <INSERT_DATE_START>  / <INSERT_DATE_END>     — row 4

    Client address lookup is pure Python, no Claude involved: this function
    scans prompts/clients/*.md (a sibling of references_folder — see
    SKILL.md's Reference Files table) for a file whose "## Aliases" section
    contains client_name as a case-insensitive substring, and uses that
    file's "## Address" section verbatim. This replaces the old
    references/address_book.json, which no longer exists.
    """

    # ── Helpers ─────────────────────────────────────────────────────────────
    def _find_cell_with_marker(doc, marker):
        """Return (table, row_idx, col_idx, cell) for first cell containing marker."""
        for tbl in doc.tables:
            for r_idx, row in enumerate(tbl.rows):
                for c_idx, cell in enumerate(row.cells):
                    if marker in cell.text:
                        return tbl, r_idx, c_idx, cell
        return None, None, None, None

    def _extract_md_section(text, heading):
        """Return the non-empty, stripped lines under a '## <heading>' section
        of a markdown file, stopping at the next '#'-prefixed heading."""
        target = f"## {heading}".strip().lower()
        out = []
        in_section = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.lower() == target:
                in_section = True
                continue
            if in_section:
                if stripped.startswith("#"):
                    break
                if stripped:
                    out.append(stripped)
        return out

    def _lookup_client_address(references_folder, client_name):
        """Scan prompts/clients/*.md for a file whose Aliases section matches
        client_name (case-insensitive substring). Returns the matched file's
        Address section as a list of lines, or None if nothing matches."""
        if not client_name:
            return None
        clients_dir = os.path.join(references_folder, "..", "prompts", "clients")
        if not os.path.isdir(clients_dir):
            return None
        needle = client_name.lower()
        for fname in sorted(os.listdir(clients_dir)):
            if not fname.lower().endswith(".md"):
                continue
            fpath = os.path.join(clients_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            aliases = _extract_md_section(text, "Aliases")
            if any(needle in alias.lower() for alias in aliases):
                return _extract_md_section(text, "Address")
        return None

    def _clear_cell(cell):
        """Remove all paragraphs from a cell except the last (required by Word)."""
        for para in cell.paragraphs[:-1]:
            p = para._element
            p.getparent().remove(p)
        # Clear the last paragraph's runs
        last_para = cell.paragraphs[0]
        for run in last_para.runs:
            run.text = ""
        last_para.clear()

    def _make_run(para, text, bold=False, font_size_pt=None):
        run = para.add_run(text)
        run.bold = bold
        if font_size_pt is not None:
            from docx.shared import Pt
            run.font.size = Pt(font_size_pt)
        return run

    # ── Date ────────────────────────────────────────────────────────────────
    _, _, _, date_cell = _find_cell_with_marker(doc, "<INSERT_DATE_START>")
    if date_cell is not None:
        today = datetime.now()
        date_str = today.strftime("%-d %B %Y")  # e.g. "9 September 2026"
        _clear_cell(date_cell)
        para = date_cell.paragraphs[0]
        _make_run(para, "Date: ", bold=True)
        _make_run(para, date_str, bold=False)
        print(f"  ✓ Cover page date: {date_str}")
    else:
        print("  ⚠ <INSERT_DATE_START> marker not found in any table cell")

    # ── Title ────────────────────────────────────────────────────────────────
    # Always 14pt, with the LSD/Wellsite portion on its own line (matches the
    # template's own line break style, e.g. "...for the \n09-02-...W4M Wellsite").
    _, _, _, title_cell = _find_cell_with_marker(doc, "<INSERT_TITLE_START>")
    if title_cell is not None:
        lsd_display = site_lsd or "UNKNOWN LSD"
        _clear_cell(title_cell)
        para = title_cell.paragraphs[0]
        run = _make_run(para, "Phase 2 Environmental Site Assessment for the", bold=True, font_size_pt=14)
        run.add_break()
        _make_run(para, f"{lsd_display} Wellsite", bold=True, font_size_pt=14)
        print(f"  ✓ Cover page title: Phase 2 Environmental Site Assessment for the / {lsd_display} Wellsite")
    else:
        print("  ⚠ <INSERT_TITLE_START> marker not found in any table cell")

    # ── Client ───────────────────────────────────────────────────────────────
    _, _, _, client_cell = _find_cell_with_marker(doc, "<INSERT_CLIENT_START>")
    if client_cell is not None:
        address_lines = _lookup_client_address(references_folder, client_name)

        _clear_cell(client_cell)
        para = client_cell.paragraphs[0]
        if address_lines:
            # Matches the template's own convention (see the original
            # <INSERT_CLIENT_START> cell): "Prepared For:" is NOT bold, the
            # company name (address_lines[0]) IS bold, remaining address
            # lines are NOT bold.
            _make_run(para, "Prepared For:\n", bold=False)
            _make_run(para, address_lines[0], bold=True)
            if len(address_lines) > 1:
                _make_run(para, "\n" + "\n".join(address_lines[1:]), bold=False)
            print(f"  ✓ Cover page client: {address_lines[0]}")
        else:
            _make_run(para, client_name or "CLIENT NAME", bold=True)
            print(f"  ⚠ No matching prompts/clients/*.md file found, using bare name: {client_name}")
    else:
        print("  ⚠ <INSERT_CLIENT_START> marker not found in any table cell")


def remove_section5_if_no_bg_chloride(doc, wb):
    """Tier 1 sites: Section 5 (Background Chloride, Heading 1 through 5.4) exists only when
    some Background-APEC sample has chloride > 100 mg/L (Tier 1 Exceedances: APEC='Background',
    Chemical Group='Chloride'; 'Excluded Background' does not count). Otherwise delete the whole
    section, from its Heading 1 up to (not including) the next Heading 1."""
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    has_bg = False
    if 'Tier 1 Exceedances' in wb.sheetnames:
        rows = list(wb['Tier 1 Exceedances'].iter_rows(values_only=True))
        if rows:
            hdr = list(rows[0])
            ai, gi = hdr.index('APEC'), hdr.index('Chemical Group')
            has_bg = any(r[ai] == 'Background' and r[gi] == 'Chloride' for r in rows[1:])
    if has_bg:
        print("  ✓ Section 5 kept: Background samples with chloride > 100 mg/L present")
        return False
    body = doc.element.body
    kids = list(body)
    def _style(el):
        ps = el.find(f'{{{ns}}}pPr/{{{ns}}}pStyle')
        return ps.get(f'{{{ns}}}val') if ps is not None else ''
    def _text(el):
        return ''.join(t.text or '' for t in el.iter(f'{{{ns}}}t')).strip()
    start = next((i for i, k in enumerate(kids) if k.tag.endswith('}p') and _style(k) in ('Heading1', 'Heading 1') and _text(k) == 'Background Chloride'), None)
    if start is None:
        print("  ⚠ Section 5 heading not found - nothing removed")
        return False
    end = next((i for i in range(start + 1, len(kids)) if kids[i].tag.endswith('}p') and _style(kids[i]) in ('Heading1', 'Heading 1')), len(kids))
    for k in kids[start:end]:
        body.remove(k)
    print(f"  ✓ Section 5 removed (no Background chloride > 100 mg/L): {end - start} element(s) deleted")
    return True


def generate_page_headers(doc, licensee, site_lsd):
    """Fill the page-header placeholders "Licensee [Abadata]" / "Site Name [Abadata]"
    in every section header (default, first-page, even-page). Header parts live outside
    the body, so markers/operations never reach them. Licensee comes from ABAData
    (site_facts), site name is the LSD."""
    subs = {"[Abadata]": None}
    seen = set()
    n = 0
    for sec in doc.sections:
        for h in (sec.header, sec.first_page_header, sec.even_page_header):
            if h.is_linked_to_previous:
                continue
            el = h._element
            if id(el) in seen:
                continue
            seen.add(id(el))
            paras = list(h.paragraphs) + [p for t in h.tables for r in t.rows for c in r.cells for p in c.paragraphs]
            for p in paras:
                for r in p.runs:
                    if "Licensee [Abadata]" in r.text and licensee:
                        r.text = r.text.replace("Licensee [Abadata]", licensee); n += 1
                    if "Site Name [Abadata]" in r.text and site_lsd:
                        r.text = r.text.replace("Site Name [Abadata]", site_lsd); n += 1
                if "[Abadata]" in p.text:
                    print(f"  ⚠ header text still has [Abadata] (split across runs?): {p.text!r}")
    print(f"  ✓ Page headers: {n} placeholder(s) filled (Licensee={licensee!r}, Site={site_lsd!r})")


def generate_appendix_e(doc, wb):
    """
    Generate Appendix E tables for each depth interval sheet in the workbook.
    Replicates the 'Background 0.0 to 0.6 m Data' table for every depth sheet,
    populated with borehole data and summary statistics from the Excel file.

    (Also covers what was once a separate "Section 12" — this template has no
    dedicated <INSERT_12_HERE> marker, so Appendix E is the only place this
    logic runs.)

    Source sheets: Excel sheets whose name starts with a digit (e.g. "0.0-0.6",
    "0.6-1.2"). Row 1 is title/metadata, row 2 is column headers (both skipped);
    data rows have a borehole ID ("BH...") in column 0; stats rows have column 0
    blank and the stat label in column 3.

    Layout template: the "Background 0.0 to 0.6 m Data" heading + table already
    in the Word template is cloned once per depth sheet. See TC_TO_EXCEL and
    TEMPLATE_STATS below for the exact Excel-column → table-cell mapping and
    stats row order/labels — those are the authoritative source, not this
    docstring; update them in one place if the Excel layout ever changes.
    """
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

    # Depth sheets are those whose name starts with a digit
    depth_sheets = [s for s in wb.sheetnames if s[0].isdigit()]
    if not depth_sheets:
        print("  ✗ No depth interval sheets found in Excel file")
        return False

    body = doc.element.body
    body_children = list(body)

    # Locate the template's Appendix E subsections: manually-numbered heading
    # paragraphs ("1.1<tab> Background Topsoil Data 0 to 0.3 m", "1.2 ... Shallow
    # Rooting Zone ...", "1.3 ... Deep Rooting Zone ...") each followed by a table.
    # ALL tables share one layout, so the FIRST heading+table is the clone source;
    # every template heading+table pair is then replaced by one pair per depth sheet
    # (depth range = the Excel sheet name; first sheet = Topsoil, any other sheet whose
    # upper bound is <= 1.0 m = Shallow Rooting Zone, the rest = Deep Rooting Zone).
    import re as _re
    def _ptext(el):
        return ''.join(t.text or '' for t in el.findall(f'.//{{{ns}}}t'))
    _hdr_pat = _re.compile(r'^\s*\d+\.\d+\s*Background\b.*\bData\b.*\bm\s*$', _re.S)
    pairs = []          # (heading_el, table_el)
    # Optional markers: <INSERT_APPE_START> above the first heading, <INSERT_APPE_END> after the last table.
    _ms = _me = None
    for i, child in enumerate(body_children):
        if child.tag.endswith('}p'):
            _t = _ptext(child).strip()
            if _t == '<INSERT_APPE_START>' and _ms is None:
                _ms = i
            elif _t == '<INSERT_APPE_END>' and _ms is not None and _me is None:
                _me = i
    if _ms is None or _me is None:
        print("  ✗ <INSERT_APPE_START> / <INSERT_APPE_END> markers not found in template")
        return False
    print("  ✓ Appendix E markers found")
    for i, child in enumerate(body_children):
        if not (_ms < i < _me):
            continue
        if child.tag.endswith('}p') and _hdr_pat.match(_ptext(child).replace('\t', ' ')):
            tbl_el = None
            for j in range(i + 1, min(i + 4, len(body_children))):
                if body_children[j].tag.endswith('}tbl'):
                    tbl_el = body_children[j]
                    break
                if body_children[j].tag.endswith('}p') and _ptext(body_children[j]).strip():
                    break
            if tbl_el is not None:
                pairs.append((child, tbl_el))
    if not pairs:
        print("  ✗ Could not find the Appendix E 'Background ... Data' template heading/table")
        return False
    template_h2_elem, template_tbl_elem = pairs[0]
    template_h2_pos = body_children.index(template_h2_elem)

    # Inspect template table structure
    tr_elements = template_tbl_elem.findall(f'{{{ns}}}tr')
    # Row layout: 0=header, 1=units, 2-8=placeholder data rows (7),
    #             9=Mean, 10=StdDev, 11=95th, 12=SCARG, 13=Guideline, 14=spacer '.'
    HEADER_ROWS = 2
    PLACEHOLDER_DATA_ROWS = 7   # rows 2-8
    STATS_COUNT = 5             # Mean, StdDev, 95th, SCARG, Guideline

    data_row_template = tr_elements[HEADER_ROWS]          # row 2
    stats_row_template = tr_elements[HEADER_ROWS + PLACEHOLDER_DATA_ROWS]  # row 9 (Mean)

    # Mapping: template stats row label → Excel stats key
    TEMPLATE_STATS = [
        ('Mean',                  'Mean'),
        ('Standard Deviation',    'Standard Deviation'),
        ('95th Percentile',       '95th Percentile'),
        ('SCARG Category Rating', 'Rating Category'),
        ('Guideline',             'Guideline'),
    ]
    # Additional Excel stats not in the template (append as extra rows)
    EXTRA_STATS = ['n(count)', 'Maximum', 'Outlier Calculation',
                   'Outliers (Count)', 'Two Category Jump (Yes/No)']

    # tc index → Excel column index mapping for data rows
    # Excel depth sheet columns: 0 Sample ID, 1 Depth, 2 pH, 3 EC, 4 SAR, 5 Sat, 6 Cl,
    # 7 Sulph, 8 Na, 9 Ca, 10 Mg, 11 K.  Word table cells (one per merged column group):
    # 0 Borehole, 1 Depth, 2 pH, 3 Sat, 4 EC, 5 SAR, 6 Cl, 7 SO4, 8 Na, 9 Ca, 10 Mg, 11 K.
    TC_TO_EXCEL = {0: 0, 1: 1, 2: 2, 3: 5, 4: 3, 5: 4,
                   6: 6, 7: 7, 8: 8, 9: 9, 10: 10, 11: 11}

    new_elements = []

    for sheet_name in depth_sheets:
        # Build section title from the depth sheet name (e.g. "0.0-0.3")
        _m = _re.match(r'^\s*([\d.]+)\s*-\s*([\d.]+)\s*(.*)$', sheet_name)
        if _m:
            _lo, _hi = float(_m.group(1)), float(_m.group(2))
            _lo_txt = "0" if _lo == 0 else f"{_lo:.1f}"
            _hi_txt = f"{_hi:.1f}"
            _suffix = f" {_m.group(3).strip()}" if _m.group(3).strip() else ""
            depth_txt = f"{_lo_txt} to {_hi_txt}{_suffix}"
        else:
            _hi = None
            depth_txt = sheet_name.replace('-', ' to ')
        _idx = depth_sheets.index(sheet_name)
        if _idx == 0:
            kind = "Topsoil"
        elif _hi is not None and _hi <= 1.0:
            kind = "Shallow Rooting Zone"
        else:
            kind = "Deep Rooting Zone"
        title = f'Background {kind} Data {depth_txt} m'
        print(f'  ✓ 1.{_idx + 1} {title}')

        # --- Read Excel sheet ---
        ws = wb[sheet_name]
        all_rows = list(ws.iter_rows(min_row=1, values_only=True))

        # Data rows: rows whose first cell starts with 'BH' (skip rows 0 and 1)
        data_rows = []
        for row in all_rows[2:]:
            if row[0] is None:
                break
            if str(row[0]).upper().startswith('OUTLIER'):
                break
            if str(row[0]).startswith('BH'):
                data_rows.append(row)

        # Stats: rows where col 0 is None and col 2 holds the label (EC col 3, SAR col 4)
        stats_from_excel = {}
        for row in all_rows[2:]:
            if row[0] is None and len(row) > 2 and isinstance(row[2], str):
                label = str(row[2])
                ec_val = row[3] if len(row) > 3 else None
                sar_val = row[4] if len(row) > 4 else None
                stats_from_excel[label] = (ec_val, sar_val)

        # --- Build the heading by cloning the template's first heading (number run + tab/text run)
        heading_el = copy.deepcopy(template_h2_elem)
        for _lr in list(heading_el.iter(f'{{{ns}}}lastRenderedPageBreak')):
            _lr.getparent().remove(_lr)
        _ts = list(heading_el.iter(f'{{{ns}}}t'))
        if len(_ts) >= 2:
            _ts[0].text = f"1.{depth_sheets.index(sheet_name) + 1}"
            _ts[1].text = f" {title}"
            for _extra in _ts[2:]:
                _extra.text = ""
        else:
            for _t in _ts:
                _t.text = ""
            if _ts:
                _ts[0].text = f"1.{depth_sheets.index(sheet_name) + 1}  {title}"
        new_elements.append(heading_el)

        # --- Deep copy template table ---
        tbl_copy = copy.deepcopy(template_tbl_elem)

        # Remove tblHeader from header rows so they don't repeat on every page break
        for tr in tbl_copy.findall(f'{{{ns}}}tr')[:HEADER_ROWS]:
            trPr = tr.find(f'{{{ns}}}trPr')
            if trPr is not None:
                for tblHeader in trPr.findall(f'{{{ns}}}tblHeader'):
                    trPr.remove(tblHeader)

        # Remove placeholder data rows (indices 2 through 2+PLACEHOLDER_DATA_ROWS-1)
        for tr in tbl_copy.findall(f'{{{ns}}}tr')[HEADER_ROWS:HEADER_ROWS + PLACEHOLDER_DATA_ROWS]:
            tbl_copy.remove(tr)

        # Find the units row in the copied table to determine insertion point
        tbl_rows_now = tbl_copy.findall(f'{{{ns}}}tr')
        units_tr = tbl_rows_now[1]  # row 1 = units row
        units_pos = list(tbl_copy).index(units_tr)

        # Insert new data rows after units row
        for i, excel_row in enumerate(data_rows):
            new_tr = copy.deepcopy(data_row_template)
            tc_list = new_tr.findall(f'{{{ns}}}tc')
            for tc_idx, excel_idx in TC_TO_EXCEL.items():
                if tc_idx < len(tc_list) and excel_idx < len(excel_row):
                    set_tc_text(tc_list[tc_idx], format_val(excel_row[excel_idx]))
            tbl_copy.insert(units_pos + 1 + i, new_tr)

        # Update existing stats rows
        tbl_rows_final = tbl_copy.findall(f'{{{ns}}}tr')
        stats_start = HEADER_ROWS + len(data_rows)

        for i, (tmpl_label, excel_key) in enumerate(TEMPLATE_STATS):
            tr_idx = stats_start + i
            if tr_idx < len(tbl_rows_final):
                tr = tbl_rows_final[tr_idx]
                tc_list = tr.findall(f'{{{ns}}}tc')
                if excel_key in stats_from_excel:
                    ec_val, sar_val = stats_from_excel[excel_key]
                    if len(tc_list) > 1:
                        set_tc_text(tc_list[1], format_val(ec_val))
                    if len(tc_list) > 2 and sar_val is not None:
                        set_tc_text(tc_list[2], format_val(sar_val))

        # Add extra stats rows before the Guideline row (index 4 in TEMPLATE_STATS)
        # Guideline is at stats_start + 4; extra rows go just before it
        guideline_tr_idx = stats_start + 4
        tbl_rows_final = tbl_copy.findall(f'{{{ns}}}tr')
        if guideline_tr_idx < len(tbl_rows_final):
            guideline_tr = tbl_rows_final[guideline_tr_idx]
            spacer_pos = list(tbl_copy).index(guideline_tr)
        else:
            spacer_pos = len(list(tbl_copy))

        insert_offset = 0
        for extra_label in EXTRA_STATS:
            if extra_label in stats_from_excel:
                ec_val, sar_val = stats_from_excel[extra_label]
                new_stats_tr = copy.deepcopy(stats_row_template)
                # Strip the top border inherited from the Mean row template
                clear_row_top_border(new_stats_tr)
                tc_list = new_stats_tr.findall(f'{{{ns}}}tc')
                set_tc_text(tc_list[0], extra_label)
                if len(tc_list) > 1:
                    set_tc_text(tc_list[1], format_val(ec_val))
                if len(tc_list) > 2:
                    set_tc_text(tc_list[2], format_val(sar_val) if sar_val is not None else "")
                tbl_copy.insert(spacer_pos + insert_offset, new_stats_tr)
                insert_offset += 1

        new_elements.append(tbl_copy)

    # Insert all new elements at the position of the first template heading
    for i, elem in enumerate(new_elements):
        body.insert(template_h2_pos + i, elem)

    # Remove the markers and everything left between them (old template pairs, spacers);
    # keep any TOC bookmarks parked in the removed elements.
    _start_el, _end_el = body_children[_ms], body_children[_me]
    _removed = []
    _cur = _start_el
    while True:
        _nxt = _cur.getnext()
        _removed.append(_cur)
        if _cur is _end_el:
            break
        _cur = _nxt
    _removed = [r for r in _removed if r not in new_elements]
    from apply_operations import rescue_orphan_bookmarks
    _dst = _end_el.getnext()
    if _dst is not None:
        rescue_orphan_bookmarks(_removed, _dst)
    for r in _removed:
        if r.getparent() is not None:
            body.remove(r)

    print(f"  ✓ Replaced placeholder with {len(depth_sheets)} depth interval tables")
    return True

def pid():
    """Generate a unique paraId."""
    import random
    return format(random.randint(0, 0xFFFFFFFF), "08X")

def make_bullet_xml(text_with_bold):
    """Convert text with <b>...</b> markers to Word Bullets paragraph XML."""
    runs = []
    parts = re.split(r'(<b>.*?</b>)', text_with_bold)
    for part in parts:
        if part.startswith("<b>") and part.endswith("</b>"):
            inner = esc(part[3:-4])
            runs.append(f'<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">{inner}</w:t></w:r>')
        elif part:
            escaped = esc(part)
            runs.append(f'<w:r><w:t xml:space="preserve">{escaped}</w:t></w:r>')
    return f'<w:p w14:paraId="{pid()}" w14:textId="{pid()}" w:rsidR="008B4DC3" w:rsidRDefault="008B4DC3"><w:pPr><w:pStyle w:val="Bullets"/></w:pPr>{"".join(runs)}</w:p>'

def _parse_figure_title(stem):
    """Derive a human-readable figure title from a BG_CHLORIDE PNG filename stem.

    Rules (applied in order):
      A-B_C  →  A/B vs. C        e.g. Cl-SO4_Cl  → Cl/SO4 vs. Cl
      A_B    →  A vs. B          e.g. Na_Cl       → Na vs. Cl
                                 e.g. Cl_SO4+Cl   → Cl vs. SO4+Cl
    """
    m = re.fullmatch(r"([^_]+)-([^_]+)_(.+)", stem)
    if m:
        return f"{m.group(1)}/{m.group(2)} vs. {m.group(3)}"
    m = re.fullmatch(r"([^_]+)_(.+)", stem)
    if m:
        return f"{m.group(1)} vs. {m.group(2)}"
    return stem


def _is_self_comparison(stem):
    """True if a BG_CHLORIDE figure filename stem plots a raw parameter
    against the exact same raw parameter (e.g. "Cl_Cl" -> Cl vs. Cl) --
    always a unit-conversion/QC artifact, never a meaningful
    source-vs-background comparison, so these are excluded from the report
    automatically rather than requiring a human to hand-edit the figures
    zip every run.

    Only the simple "A_B" form is checked. The ratio form "A-B_C" is
    deliberately NOT flagged even when C matches A or B (e.g. "Cl-SO4_Cl",
    i.e. the Cl/SO4 ratio vs. raw Cl) -- a ratio plotted against one of its
    own components is a real, standard technique (detecting mixing/dilution
    trends), not a self-plot, since the ratio is not the same quantity as
    the raw parameter.
    """
    m = re.fullmatch(r"([^_]+)_(.+)", stem)
    if m and "-" not in m.group(1) and "-" not in m.group(2):
        a, b = m.group(1).strip().lower(), m.group(2).strip().lower()
        return a == b
    return False


def generate_section5_3_figures(doc, figures_zip_path, figure_start=1):
    """Insert BG_CHLORIDE chemistry footprint figures between
    <INSERT_5_3_FIGURES_START> and <INSERT_5_3_FIGURES_END>.

    Everything between the two markers (inclusive) is deleted first — this
    is a range replacement, not a single-point insertion, so any stale
    placeholder content (e.g. leftover template example figures) sitting
    inside the range is removed along with the markers themselves. This
    mirrors the `replace_between` pattern used for Claude-authored text
    operations elsewhere in this pipeline.

    For each PNG found in the BG_CHLORIDE/ folder of the zip (sorted
    alphanumerically), inserts:
      1. A FigureTitle-styled heading  "Figure N: <title>"
      2. The image inline, centred, at 6 inches wide
      3. A blank Normal paragraph for spacing

    Falls back to the legacy single-marker form (`<INSERT_5_3_FIGURES>`,
    point-replacement, nothing deleted around it) if the START/END pair
    isn't found in the template, so older templates keep working.

    Args:
        doc:              python-docx Document object
        figures_zip_path: path to the figures zip (may not exist)
        figure_start:     first figure number to use (default 1)

    Returns:
        True if figures were inserted or no zip/folder found (non-fatal);
        False only on an unexpected error.
    """
    START = "<INSERT_5_3_FIGURES_START>"
    END = "<INSERT_5_3_FIGURES_END>"
    LEGACY_PLACEHOLDER = "<INSERT_5_3_FIGURES>"
    NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    if not os.path.exists(figures_zip_path):
        print(f"  ℹ Figures zip not found ({os.path.basename(figures_zip_path)}) — skipping {START}/{END}")
        return True

    with zipfile.ZipFile(figures_zip_path) as zf:
        all_bg_pngs = sorted(
            n for n in zf.namelist()
            if n.startswith("BG_CHLORIDE/") and n.lower().endswith(".png")
        )

    bg_pngs = []
    for n in all_bg_pngs:
        stem = n.split("/")[-1][:-4]
        if _is_self_comparison(stem):
            print(f"  ℹ Skipping {n} — parameter plotted against itself (QC/unit-check artifact, not a real comparison)")
            continue
        bg_pngs.append(n)

    if not bg_pngs:
        print(f"  ℹ No BG_CHLORIDE figures in zip — skipping {START}/{END}")
        return True

    body = doc.element.body

    def _find_by_text(marker):
        for child in list(body):
            texts = "".join(t.text or "" for t in child.findall(f".//{{{NS}}}t"))
            if marker in texts:
                return child
        return None

    start_el = _find_by_text(START)
    end_el = _find_by_text(END)

    if start_el is not None and end_el is not None:
        body_children = list(body)
        start_idx = body_children.index(start_el)
        end_idx = body_children.index(end_el)
        if end_idx < start_idx:
            print(f"  ✗ {END} appears before {START} in document — skipping")
            return False
        # Delete every element from START through END inclusive (removes
        # any stale placeholder content sitting between the markers too).
        insert_idx = start_idx
        for el in body_children[start_idx:end_idx + 1]:
            body.remove(el)
    else:
        # Legacy fallback: single-point placeholder, nothing deleted around it.
        placeholder_el = _find_by_text(LEGACY_PLACEHOLDER)
        if placeholder_el is None:
            print(f"  ✗ Neither '{START}'/'{END}' nor legacy '{LEGACY_PLACEHOLDER}' found in document")
            return False
        insert_idx = list(body).index(placeholder_el)
        body.remove(placeholder_el)

    new_elements = []
    figure_num = figure_start

    with zipfile.ZipFile(figures_zip_path) as zf:
        for png_name in bg_pngs:
            stem = png_name.split("/")[-1][:-4]  # strip .png
            title = _parse_figure_title(stem)
            caption = f"Figure {figure_num}: {title}"
            figure_num += 1

            # ── FigureTitle heading paragraph
            heading_xml = (
                f'<w:p xmlns:w="{NS}">'
                f'<w:pPr><w:pStyle w:val="FigureTitle"/></w:pPr>'
                f'<w:r><w:t>{esc(caption)}</w:t></w:r>'
                f'</w:p>'
            )
            new_elements.append(parse_xml(heading_xml))

            # ── Image paragraph (centred, 6 in wide)
            # python-docx requires appending to the doc, then we relocate the element.
            img_data = io.BytesIO(zf.read(png_name))
            img_para = doc.add_paragraph()
            img_para.alignment = 1  # WD_ALIGN_PARAGRAPH.CENTER
            img_para.add_run().add_picture(img_data, width=Inches(6.0))
            img_el = img_para._element
            body.remove(img_el)   # detach from end-of-body where add_paragraph put it
            new_elements.append(img_el)

            # ── Blank spacing paragraph
            blank_xml = (
                f'<w:p xmlns:w="{NS}">'
                f'<w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
                f'</w:p>'
            )
            new_elements.append(parse_xml(blank_xml))

    for i, el in enumerate(new_elements):
        body.insert(insert_idx + i, el)

    print(f"  ✓ generate_section5_3_figures: inserted {len(bg_pngs)} figure(s)")
    return True



def generate_section4_3_na_profile(doc, figures_zip_path):
    """Replace everything between <INSERT_43_NA_PROFILE_START> and
    <INSERT_43_NA_PROFILE_END> (Section 4.3, right after the "Figure 1.
    Soil Chloride Profile" caption) with the real chloride-delineation
    profile figure(s) from the CL_DELINEATION/ folder of the figures zip,
    laid out in a grid (2 columns max, wrapping to additional rows as
    needed) — or with a literal "Not applicable" sentence if the zip has
    none.

    This is a range replacement, not a single-point insertion: everything
    from START through END (inclusive) is deleted first, which removes the
    template's own static placeholder figure along with the markers
    themselves, whatever else may be sitting in that range. Mirrors the
    `replace_between` pattern used for Claude-authored text operations, and
    the same range-removal approach as generate_section5_3_figures.
    """
    START = "<INSERT_43_NA_PROFILE_START>"
    END = "<INSERT_43_NA_PROFILE_END>"
    NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = doc.element.body

    def _find_by_text(marker):
        for child in list(body):
            texts = "".join(t.text or "" for t in child.findall(f".//{{{NS}}}t"))
            if marker in texts:
                return child
        return None

    start_el = _find_by_text(START)
    end_el = _find_by_text(END)

    if start_el is None or end_el is None:
        print(f"  \u2139 {START}/{END} not found \u2014 skipping (already replaced, or template changed)")
        return True

    body_children = list(body)
    start_idx = body_children.index(start_el)
    end_idx = body_children.index(end_el)
    if end_idx < start_idx:
        print(f"  \u2717 {END} appears before {START} in document \u2014 skipping")
        return False

    # Delete every element from START through END inclusive (removes the
    # template's placeholder figure sitting between the markers too).
    insert_idx = start_idx
    for el in body_children[start_idx:end_idx + 1]:
        body.remove(el)

    pngs = []
    if os.path.exists(figures_zip_path):
        with zipfile.ZipFile(figures_zip_path) as zf:
            pngs = sorted(
                n for n in zf.namelist()
                if n.startswith("CL_DELINEATION/") and n.lower().endswith(".png")
            )

    if not pngs:
        na_xml = (
            f'<w:p xmlns:w="{NS}">'
            f'<w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
            f'<w:r><w:t>Not applicable \u2014 no vertical chloride profile figures were provided for this site.</w:t></w:r>'
            f'</w:p>'
        )
        body.insert(insert_idx, parse_xml(na_xml))
        print(f"  \u2713 generate_section4_3_na_profile: no CL_DELINEATION figures found \u2014 inserted 'Not applicable'")
        return True

    # \u2500\u2500 Grid table: 2 columns max, wrap to additional rows. Each image
    # sized to ~3.1 in wide so two fit side by side within a ~6.5 in text
    # width; a lone odd image out gets an empty cell beside it.
    n_cols = 2 if len(pngs) > 1 else 1
    n_rows = (len(pngs) + n_cols - 1) // n_cols
    img_width = Inches(6.0) if n_cols == 1 else Inches(3.1)

    table = doc.add_table(rows=n_rows, cols=n_cols)
    table.autofit = True
    # Strip visible borders \u2014 this is a layout grid, not a data table.
    tbl_el = table._element
    tblPr = tbl_el.find(f"{{{NS}}}tblPr")
    borders_xml = (
        f'<w:tblBorders xmlns:w="{NS}">'
        + "".join(
            f'<w:{side} w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            for side in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        + "</w:tblBorders>"
    )
    tblPr.append(parse_xml(borders_xml))

    with zipfile.ZipFile(figures_zip_path) as zf:
        for i, png_name in enumerate(pngs):
            row, col = divmod(i, n_cols)
            cell = table.cell(row, col)
            cell_para = cell.paragraphs[0]
            cell_para.alignment = 1  # centered
            img_data = io.BytesIO(zf.read(png_name))
            cell_para.add_run().add_picture(img_data, width=img_width)

    tbl_el = table._element
    body.remove(tbl_el)   # detach from end-of-body where add_table put it
    body.insert(insert_idx, tbl_el)

    print(f"  \u2713 generate_section4_3_na_profile: inserted {len(pngs)} figure(s) in a {n_cols}-column grid")
    return True


def generate_section5_4_background(doc, ecsar_data):
    """Fill the fixed Section 5.4 background-borehole sentence between
    <INSERT_5_4_START> and <INSERT_5_4_END>.

    This is a deterministic text substitution, not an LLM-authored
    paragraph: the sentence itself is fixed template wording (see
    prompts/s5_4_conclusion.md), and only the borehole list varies per
    site. That list is the distinct Sample IDs where APEC == "Background"
    in the `EC & SAR Rating Categories` sheet, sorted alphanumerically.

    Section 5.4 only exists when background chloride is present — if no
    row has APEC == "Background", the markers are left untouched (Claude's
    operations pipeline / the template itself is responsible for removing
    the section in that case, not this function).

    Args:
        doc:        python-docx Document object
        ecsar_data: list of dict rows from the `EC & SAR Rating Categories`
                    sheet (already normalised — see main())

    Returns:
        True if the sentence was inserted, or Section 5.4 legitimately
        doesn't apply (no Background APEC rows); False on an unexpected
        structural error (markers missing/out of order).
    """
    START = "<INSERT_5_4_START>"
    END = "<INSERT_5_4_END>"
    NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    bh_ids = sorted({
        row.get("Sample ID") for row in ecsar_data
        if row.get("Comments") == "Background" and row.get("Sample ID")
    })

    if not bh_ids:
        print(f"  ℹ No Background-APEC boreholes found — leaving {START}/{END} untouched")
        return True

    if len(bh_ids) == 1:
        bh_list = bh_ids[0]
    elif len(bh_ids) == 2:
        bh_list = f"{bh_ids[0]} and {bh_ids[1]}"
    else:
        bh_list = ", ".join(bh_ids[:-1]) + f", and {bh_ids[-1]}"

    sentence = (
        "Based on the above lines of evidence, it is concluded that the elevated "
        "chloride levels at the outlying background locations are not related to "
        "the on-site source area and are due to naturally occurring conditions. "
        f"As such, boreholes {bh_list} were used as background for SCARG "
        "guideline development."
    )

    body = doc.element.body

    def _find_by_text(marker):
        for child in list(body):
            texts = "".join(t.text or "" for t in child.findall(f".//{{{NS}}}t"))
            if marker in texts:
                return child
        return None

    start_el = _find_by_text(START)
    end_el = _find_by_text(END)

    if start_el is None or end_el is None:
        print(f"  ✗ '{START}'/'{END}' not found in document")
        return False

    body_children = list(body)
    start_idx = body_children.index(start_el)
    end_idx = body_children.index(end_el)
    if end_idx < start_idx:
        print(f"  ✗ {END} appears before {START} in document — skipping")
        return False

    for el in body_children[start_idx:end_idx + 1]:
        body.remove(el)

    para_xml = (
        f'<w:p xmlns:w="{NS}">'
        f'<w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
        f'<w:r><w:t xml:space="preserve">{esc(sentence)}</w:t></w:r>'
        f'</w:p>'
    )
    body.insert(start_idx, parse_xml(para_xml))

    print(f"  ✓ generate_section5_4_background: {bh_list}")
    return True


def generate_section3_2_scarg(doc, wb, ecsar_data):
    """Fill Section 3.2 (SCARG Guidelines): the intro paragraph between
    <INSERT_3_2_INTRO_START>/<INSERT_3_2_INTRO_END>, and the guideline table
    rows after <INSERT_SCARG_TABLE>.

    Both halves are deterministic — a fixed-sentence if/else and a direct
    Excel-to-table transcription with two mechanical formatting rules — so
    this is pure Python, not a Claude-authored operation (see
    prompts/s3_2_scarg.md).

    Args:
        doc:        python-docx Document object
        wb:         openpyxl Workbook (for the `SCARG Guideline Summary` sheet)
        ecsar_data: list of dict rows from the `EC & SAR Rating Categories`
                    sheet (already normalised — see main())

    Returns:
        True if both parts were filled; False on a structural error.
    """
    NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    from docx.oxml.ns import qn as _qn
    import copy as _copy

    ok = True

    # ── Part 1 — narrative paragraph ────────────────────────────────────────
    START = "<INSERT_3_2_INTRO_START>"
    END = "<INSERT_3_2_INTRO_END>"

    # Shared with generate_section4_2_1_background() -- both sections must
    # agree on which rows are "background" and whether they're all Good.
    all_good = _background_all_good(ecsar_data)

    if all_good:
        paragraph_a_or_b = (
            "As all background samples were within the Good soil category for "
            "EC and SAR, these guidelines were applied to all characterization "
            "samples and depths as per Tier 1 (EPA, 2024a)."
        )
    else:
        paragraph_a_or_b = (
            "A background statistical evaluation was completed to derive "
            "site-specific EC and SAR guidelines. The background statistics "
            "are summarized below and included in Appendix E."
        )

    body = doc.element.body

    def _find_by_text(marker):
        for child in list(body):
            texts = "".join(t.text or "" for t in child.findall(f".//{{{NS}}}t"))
            if marker in texts:
                return child
        return None

    start_el = _find_by_text(START)
    end_el = _find_by_text(END)

    if start_el is None or end_el is None:
        print(f"  ✗ '{START}'/'{END}' not found in document")
        ok = False
    else:
        body_children = list(body)
        start_idx = body_children.index(start_el)
        end_idx = body_children.index(end_el)
        if end_idx < start_idx:
            print(f"  ✗ {END} appears before {START} in document — skipping")
            ok = False
        else:
            for el in body_children[start_idx:end_idx + 1]:
                body.remove(el)
            para_xml = (
                f'<w:p xmlns:w="{NS}">'
                f'<w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
                f'<w:r><w:t xml:space="preserve">{esc(paragraph_a_or_b)}</w:t></w:r>'
                f'</w:p>'
            )
            body.insert(start_idx, parse_xml(para_xml))
            print(f"  ✓ generate_section3_2_scarg: intro paragraph ({'A' if all_good else 'B'})")

    # ── Part 2 — SCARG guideline table ──────────────────────────────────────
    TABLE_ANCHOR = "<INSERT_SCARG_TABLE>"
    HEADER_ROWS = 3

    if "SCARG Guideline Summary" not in wb.sheetnames:
        print(f"  ✗ 'SCARG Guideline Summary' sheet not found — skipping {TABLE_ANCHOR}")
        return False

    ws = wb["SCARG Guideline Summary"]
    scarg_rows = [row for row in ws.iter_rows(min_row=2, values_only=True) if row[0]]

    def _fmt_depth(val):
        return str(val).replace("-", "–")

    def _fmt_guideline(val):
        s = format_val(val)
        if s.endswith(".0"):
            s = s[:-2]
        return s

    table_rows = [
        [
            _fmt_depth(row[0]),
            str(row[1]) if row[1] is not None else "",
            str(row[2]) if row[2] is not None else "",
            str(row[3]) if row[3] is not None else "",
            _fmt_guideline(row[4]),
            _fmt_guideline(row[5]),
        ]
        for row in scarg_rows
    ]

    body_children = list(body)
    anchor_el = None
    anchor_idx = None
    for i, child in enumerate(body_children):
        if not child.tag.endswith("}p"):
            continue
        texts = "".join(t.text or "" for t in child.findall(f".//{{{NS}}}t"))
        if TABLE_ANCHOR in texts:
            anchor_el = child
            anchor_idx = i
            break

    if anchor_el is None:
        print(f"  ✗ replace_table_rows: anchor '{TABLE_ANCHOR}' not found")
        return False

    tbl_el = None
    for j in range(anchor_idx + 1, len(body_children)):
        sibling = body_children[j]
        if sibling.tag.endswith("}tbl"):
            tbl_el = sibling
            break
        if sibling.tag.endswith("}p"):
            sib_text = "".join(t.text or "" for t in sibling.findall(f".//{{{NS}}}t"))
            if sib_text.strip():
                break

    if tbl_el is None:
        print(f"  ✗ replace_table_rows: no table found after anchor '{TABLE_ANCHOR}'")
        return False

    tbl_wrapper = None
    for t in doc.tables:
        if t._tbl is tbl_el:
            tbl_wrapper = t
            break
    if tbl_wrapper is None:
        print(f"  ✗ replace_table_rows: could not find Table wrapper for '{TABLE_ANCHOR}'")
        return False

    all_rows = tbl_wrapper.rows
    template_row_el = all_rows[HEADER_ROWS]._tr if len(all_rows) > HEADER_ROWS else all_rows[-1]._tr

    tr_elements = tbl_el.findall(_qn("w:tr"))
    for tr in tr_elements[HEADER_ROWS:]:
        tbl_el.remove(tr)

    for row_values in table_rows:
        new_tr = _copy.deepcopy(template_row_el)
        tc_els = new_tr.findall(_qn("w:tc"))
        for col_idx, cell_text in enumerate(row_values):
            if col_idx >= len(tc_els):
                break
            tc = tc_els[col_idx]
            set_tc_text(tc, cell_text)
        tbl_el.append(new_tr)

    body.remove(anchor_el)
    print(f"  ✓ generate_section3_2_scarg: {len(table_rows)} guideline row(s) written")

    return ok



def _canonicalize_auger_method(raw):
    """Normalize auger/drilling-method label variants (e.g. "S.S. Auger" vs
    "Solid Stem Auger") to one consistent phrase for report prose. Log
    templates abbreviate this inconsistently across drilling programs/years
    (see prompts/site_facts_cache.md's `drilling_method` field notes — the
    2023 08-13 logs even had it under the wrong header label entirely), so
    this is tolerant matching, not a literal passthrough.
    """
    if not raw:
        return None
    s = str(raw).strip().lower()
    if "hollow" in s or s in ("h.s. auger", "hs auger"):
        return "hollow-stem auger"
    if "solid" in s or s in ("s.s. auger", "ss auger"):
        return "solid-stem auger"
    # Unrecognized phrasing — return as-is rather than guessing wrong
    return str(raw).strip()


def _parse_drill_date_header(raw):
    """Parse a `drill_date_header` string (e.g. "December 13, 2023" or
    "October 07-08, 2024") into a (start_date, end_date, display_text)
    tuple for event-grouping/sorting. Returns None if unparseable — callers
    must fall back to an "XX" placeholder rather than guessing a date.
    """
    import re
    from datetime import date

    if not raw:
        return None
    raw = str(raw).strip()

    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }

    # "Month DD-DD, YYYY" (contiguous multi-day event within one month)
    m = re.match(r"^([A-Za-z]+)\s+(\d{1,2})\s*-\s*(\d{1,2}),\s*(\d{4})$", raw)
    if m:
        mon_name, d1, d2, yr = m.groups()
        mon = months.get(mon_name.lower())
        if mon:
            try:
                start = date(int(yr), mon, int(d1))
                end = date(int(yr), mon, int(d2))
                return (start, end, raw)
            except ValueError:
                pass

    # "Month DD, YYYY" (single day)
    m = re.match(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$", raw)
    if m:
        mon_name, d1, yr = m.groups()
        mon = months.get(mon_name.lower())
        if mon:
            try:
                d = date(int(yr), mon, int(d1))
                return (d, d, raw)
            except ValueError:
                pass

    # Unrecognized format — surface the raw text but flag as unparsed by
    # returning None, so the caller can fall back rather than mis-sort it.
    return None


def _build_phase2_esa_date_clause(log_sets):
    """Build the "A Phase 2 ESA was conducted on/from ..." (or "Phase 2
    ESAs were conducted on ... and ...") clause from the cached
    `borehole_logs.log_sets[].drill_date_header` values — one event per log
    set, mirroring the singular/plural + date-range phrasing rules already
    established for the executive summary's investigation-date sentence
    (prompts/exec_summary.md, Section 3A), just with this section's own
    "Phase 2 ESA" subject instead of "soil investigation".

    Returns "A Phase 2 ESA was conducted [on/from] XX" (falls back to a
    literal "XX" date if nothing could be parsed) rather than failing the
    whole paragraph over a date-format surprise.
    """
    parsed = []
    for ls in log_sets or []:
        raw = ls.get("drill_date_header")
        p = _parse_drill_date_header(raw)
        if p:
            parsed.append(p)

    if not parsed:
        return "A Phase 2 ESA was conducted on XX"

    parsed.sort(key=lambda t: t[0])

    def _fmt_event(start, end, raw_text):
        if start == end:
            return f"on {start.strftime('%B %-d, %Y')}"
        if start.month == end.month and start.year == end.year:
            return f"from {start.strftime('%B %-d')}–{end.strftime('%-d, %Y')}"
        return f"from {start.strftime('%B %-d, %Y')} to {end.strftime('%B %-d, %Y')}"

    if len(parsed) == 1:
        start, end, raw_text = parsed[0]
        return f"A Phase 2 ESA was conducted {_fmt_event(start, end, raw_text)}"

    event_strs = [_fmt_event(s, e, r) for s, e, r in parsed]
    # Join: "on X and from Y" style — strip the leading "on"/"from" off all
    # but the first so it reads as one sentence with per-event prepositions
    # kept, matching the exec-summary multi-event join style.
    if len(event_strs) == 2:
        joined = f"{event_strs[0]} and {event_strs[1]}"
    else:
        joined = ", ".join(event_strs[:-1]) + f", and {event_strs[-1]}"
    return f"Phase 2 ESAs were conducted {joined}"


def generate_section4_intro(doc, site_facts):
    """Fill Section 4's intro (<INSERT_4_INTRO_START>/<INSERT_4_INTRO_END>):
    the drilling-summary paragraph (date(s), borehole count, depth range,
    drilling method) and the figure/appendix/table reference paragraph.

    Every fact in the first paragraph is a mechanical read/computation off
    `site_facts.json`'s `borehole_logs` block (log_sets' drill_date_header/
    drilling_method/bh_diameter_in, and boreholes[]'s total_depth_m) — no
    narrative judgment, so this is pure Python rather than a Claude-authored
    operation, same reasoning as generate_section2_6/2_7/2_8 and
    generate_section3_2_scarg.

    The second paragraph's "Figure XX"/"Tables XX" are left as literal "XX"
    placeholders on purpose (per user decision) — final figure/table
    numbering depends on the fully-assembled report and is filled in by the
    practitioner at the end, same as today.

    Degrades gracefully: any individual fact that can't be computed (no
    borehole_logs.analysis, unparseable dates, missing total_depth_m,
    inconsistent drilling method across log sets) falls back to an "XX"
    placeholder for just that piece rather than failing the whole paragraph
    or leaving the markers untouched.

    Args:
        doc:         python-docx Document object
        site_facts:  dict loaded from site_facts.json (this run's cache)
    """
    from apply_operations import op_replace_between

    bl = (site_facts or {}).get("borehole_logs") or {}
    log_sets = bl.get("log_sets") or []
    boreholes = bl.get("boreholes") or []

    # ── Borehole count ──────────────────────────────────────────────────────
    n_boreholes = str(len(boreholes)) if boreholes else "XX"

    # ── Depth range ─────────────────────────────────────────────────────────
    depths = [b.get("total_depth_m") for b in boreholes if b.get("total_depth_m") is not None]
    if depths:
        depth_range = f"{min(depths):.1f}-{max(depths):.1f} mbgs"
    else:
        depth_range = "XX mbgs"

    # ── Drilling rig / auger clause ─────────────────────────────────────────
    methods = {_canonicalize_auger_method(ls.get("drilling_method")) for ls in log_sets if ls.get("drilling_method")}
    diameters = {ls.get("bh_diameter_in") for ls in log_sets if ls.get("bh_diameter_in") is not None}
    if len(methods) == 1 and len(diameters) == 1:
        dia = next(iter(diameters))
        dia_str = f"{dia:g}"
        method = next(iter(methods))
        drilling_clause = f"using a truck-mounted drilling rig with a {dia_str}-inch {method}"
    else:
        if len(methods) > 1 or len(diameters) > 1:
            print(f"  ⚠ Section 4 intro: inconsistent drilling method/diameter across log sets ({methods!r}, {diameters!r}) — leaving drilling-rig clause as placeholder for manual review")
        drilling_clause = "using a truck-mounted drilling rig with a XX-inch XX auger"

    # ── Date clause ─────────────────────────────────────────────────────────
    date_clause = _build_phase2_esa_date_clause(log_sets)

    # ── Placement-rationale clause ──────────────────────────────────────────
    has_historical_data = bool((site_facts or {}).get("phase1_esa", {}).get("provided")) or bool((site_facts or {}).get("other_previous_assessments"))
    if has_historical_data:
        placement_sentence = "Borehole placement targeted areas of potential environmental concern identified in the historical investigation data."
    else:
        placement_sentence = "Borehole placement targeted areas of potential environmental concern identified during the site inspection."

    sentence1 = f"{date_clause}, advancing {n_boreholes} boreholes to depths of {depth_range} {drilling_clause}."
    para1 = f"{sentence1} {placement_sentence}"

    para2 = (
        "The borehole locations and exceedance evaluation are shown in Figure XX; "
        "and the borehole logs, laboratory reports, safety protocols and sampling "
        "methodology are provided in Appendices A-C. The soil analytical results "
        "are summarized in Tables XX."
    )

    ok = op_replace_between(doc, {
        "start_placeholder": "<INSERT_4_INTRO_START>",
        "end_placeholder": "<INSERT_4_INTRO_END>",
        "blocks": [
            {"style": "body", "text": para1},
            {"style": "body", "text": para2},
        ],
    })
    if ok:
        print(f"  ✓ generate_section4_intro: {n_boreholes} boreholes, {depth_range}")
    return ok


def generate_section4_1_borehole_rationale(doc, wb):
    """Fill Section 4.1's Borehole Rationale table (<INSERT_41_TABLE>): one
    row per line in the Excel "Borehole Rationale" sheet, with a checkmark
    glyph in the Salinity/Metals/PHC/PAH columns wherever that sheet says
    "Yes" and a dash otherwise. The "Other" column is free text (e.g. a
    glycol/methanol note) rather than a checkbox, straight from the sheet.

    This is a direct Excel-to-table transcription with one mechanical
    formatting rule (Yes/No -> checkmark glyph/dash) — no wording judgment —
    so it's pure Python, same reasoning as generate_section3_2_scarg.

    The checkmark itself is not a literal "check box" form field in the
    template; it's a plain character run (U+2714, "Segoe UI Symbol" font).
    Rather than hardcode that font, this clones the *existing* checked/
    unchecked template cells found in the table's own first data row, so
    formatting always matches whatever the template actually has.

    Args:
        doc: python-docx Document object
        wb:  openpyxl Workbook (for the `Borehole Rationale` sheet)

    Returns:
        True if the table was filled; False on a structural/data error
        (table/marker left in place for manual review either way).
    """
    import copy as _copy
    from docx.oxml.ns import qn as _qn
    from apply_operations import _locate_table_by_anchor

    ANCHOR = "<INSERT_41_TABLE>"
    HEADER_ROWS = 1

    if "Borehole Rationale" not in wb.sheetnames:
        print(f"  ⚠ Section 4.1: 'Borehole Rationale' sheet not found — leaving {ANCHOR} in place for manual review")
        return False

    ws = wb["Borehole Rationale"]
    sheet_rows = [
        row for row in ws.iter_rows(min_row=2, values_only=True)
        if row and row[0]
    ]
    if not sheet_rows:
        print(f"  ⚠ Section 4.1: 'Borehole Rationale' sheet has no data rows — leaving {ANCHOR} in place for manual review")
        return False

    table, anchor_para_el, skipped_marker_els = _locate_table_by_anchor(doc, ANCHOR)
    if table is None:
        print(f"  ✗ Section 4.1: anchor '{ANCHOR}' not found")
        return False

    tbl_el = table._tbl
    all_trs = tbl_el.findall(_qn("w:tr"))
    if len(all_trs) <= HEADER_ROWS:
        print(f"  ✗ Section 4.1: table after '{ANCHOR}' has no template data row to clone")
        return False

    # Find one checked-glyph template cell and one unchecked ("-") template
    # cell anywhere in the existing data rows, so formatting always matches
    # whatever this template actually uses (don't hardcode the font).
    checked_p_template = None
    unchecked_p_template = None
    for tr in all_trs[HEADER_ROWS:]:
        for tc in tr.findall(_qn("w:tc")):
            txt = "".join(t.text or "" for t in tc.findall(f".//{_qn('w:t')}")).strip()
            if txt == "✔" and checked_p_template is None:
                p = tc.find(_qn("w:p"))
                if p is not None:
                    checked_p_template = _copy.deepcopy(p)
            elif txt == "-" and unchecked_p_template is None:
                p = tc.find(_qn("w:p"))
                if p is not None:
                    unchecked_p_template = _copy.deepcopy(p)
        if checked_p_template is not None and unchecked_p_template is not None:
            break

    if checked_p_template is None or unchecked_p_template is None:
        print(f"  ✗ Section 4.1: could not find both a checked and an unchecked template cell in the existing table — leaving {ANCHOR} in place")
        return False

    def _set_checkbox_cell(tc, checked):
        for p in list(tc.findall(_qn("w:p"))):
            tc.remove(p)
        tc.append(_copy.deepcopy(checked_p_template if checked else unchecked_p_template))

    # Template row to clone for each new data row (the first existing data row)
    template_row_el = all_trs[HEADER_ROWS]

    # Remove all existing data rows (keep the header row(s))
    for tr in all_trs[HEADER_ROWS:]:
        tbl_el.remove(tr)

    for row in sheet_rows:
        boreholes = str(row[0]) if row[0] is not None else ""
        apec = str(row[1]) if len(row) > 1 and row[1] is not None else ""
        salinity = str(row[2]).strip().lower() == "yes" if len(row) > 2 and row[2] is not None else False
        metals = str(row[3]).strip().lower() == "yes" if len(row) > 3 and row[3] is not None else False
        phc = str(row[4]).strip().lower() == "yes" if len(row) > 4 and row[4] is not None else False
        pah = str(row[5]).strip().lower() == "yes" if len(row) > 5 and row[5] is not None else False
        other = str(row[6]).strip() if len(row) > 6 and row[6] not in (None, "") else "-"

        new_tr = _copy.deepcopy(template_row_el)
        tc_els = new_tr.findall(_qn("w:tc"))
        if len(tc_els) < 7:
            continue

        set_tc_text(tc_els[0], boreholes)
        set_tc_text(tc_els[1], apec)
        _set_checkbox_cell(tc_els[2], salinity)
        _set_checkbox_cell(tc_els[3], metals)
        _set_checkbox_cell(tc_els[4], phc)
        _set_checkbox_cell(tc_els[5], pah)
        set_tc_text(tc_els[6], other)

        tbl_el.append(new_tr)

    if anchor_para_el is not None:
        anchor_para_el.getparent().remove(anchor_para_el)
    for skip_el in skipped_marker_els:
        skip_el.getparent().remove(skip_el)

    print(f"  ✓ generate_section4_1_borehole_rationale: {len(sheet_rows)} row(s) written")
    return True


def _apec_meets_guidelines_or_justified(wb):
    """Read the `Tier 1 Exceedances` sheet and compute, per normalized APEC
    name, whether every exceedance at that APEC was justified.

    Every row in this sheet already IS an exceedance (that's what the sheet
    contains) -- there's no separate "does this exceed?" test to run. So
    per APEC: "No" if any row has Justified (Yes/No) != "Yes"; "Yes" if
    every row is justified, OR if the APEC has zero rows here at all (no
    exceedances -> trivially meets guidelines).

    DWDA-Char and DWDA-Delineation (two APEC column values in this sheet,
    for the two rounds of DWDA boreholes) are merged into a single "DWDA"
    key, matching how Section 4.2 and Section 4.1's table both treat DWDA
    as one APEC.

    Returns {apec_name: "Yes"|"No"}. Only includes APECs actually seen in
    the sheet -- caller decides what to do for an APEC with no key (treat
    as "Yes", since no rows means no exceedances).
    """
    if "Tier 1 Exceedances" not in wb.sheetnames:
        return {}
    ws = wb["Tier 1 Exceedances"]
    headers = [c.value for c in ws[1]]
    if "APEC" not in headers or "Justified (Yes/No)" not in headers:
        return {}
    idx = {h: i for i, h in enumerate(headers) if h}

    def _normalize(apec):
        if not apec or str(apec).strip() == "-":
            return None
        a = str(apec).strip()
        if a.lower().startswith("dwda"):
            return "DWDA"
        return a

    from collections import defaultdict
    unjustified_count = defaultdict(int)
    seen = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        apec = _normalize(row[idx["APEC"]])
        if apec is None:
            continue
        seen.add(apec)
        justified = row[idx["Justified (Yes/No)"]]
        if str(justified).strip().lower() != "yes":
            unjustified_count[apec] += 1

    return {apec: ("No" if unjustified_count[apec] > 0 else "Yes") for apec in seen}


def generate_section7_1_apec_review(doc, wb):
    """Fill Section 7.1's APEC Review table (<INSERT_71_TABLE>): one row
    per true APEC (Vertical Del SA1, Lateral Del SA2, Lat. And Vert Del
    SA2, DWDA) -- NOT one row per `Borehole Rationale` sheet line, because
    that sheet also carries "Background" and "Unassigned" lines which
    aren't APECs under investigation (confirmed with user 2026-09-29).
    DWDA-Char and DWDA-Delineation are merged into a single "DWDA" row,
    same as everywhere else in the report treats DWDA as one APEC.

    The template's own table for this marker has NO "Boreholes" column
    (verified directly against the template) -- its header is APEC |
    Salinity | Metals | PHC | PAH | Other | Meets Applicable Guidelines
    and/or Justified. That's what's reproduced here; do not add a
    Boreholes column even though the Section 4.1 table has one.

    The Salinity/Metals/PHC/PAH panel flags and "Other" text come from
    `_borehole_rationale_by_apec()` (same sheet/columns as Section 4.1, so
    the two tables never disagree about which panel applied to which
    APEC). DWDA's panel comes from its characterization row (the one the
    required AER panel applies to), via `_dwda_char_delin_boreholes()`.

    The new "Meets Applicable Guidelines and/or Justified" column comes
    from `_apec_meets_guidelines_or_justified()` against the `Tier 1
    Exceedances` sheet. An APEC with zero exceedance rows there defaults
    to "Yes" (nothing to justify).

    Pure Python -- direct Excel-to-table transcription plus one derived
    Yes/No column, no wording judgment. Same checkbox-glyph-cloning
    approach as generate_section4_1_borehole_rationale() so formatting
    always matches the template's own cells rather than a hardcoded font.

    Args:
        doc: python-docx Document object
        wb:  openpyxl Workbook (`Borehole Rationale` and `Tier 1
             Exceedances` sheets)

    Returns:
        True if the table was filled; False on a structural/data error
        (table/marker left in place for manual review either way).
    """
    import copy as _copy
    from docx.oxml.ns import qn as _qn
    from apply_operations import _locate_table_by_anchor

    ANCHOR = "<INSERT_71_TABLE>"
    HEADER_ROWS = 1
    REAL_APECS = ["Vertical Del SA1", "Lateral Del SA2", "Lat. And Vert Del SA2", "DWDA"]

    panel_by_apec = _borehole_rationale_by_apec(wb)
    if not panel_by_apec:
        print(f"  ⚠ Section 7.1: 'Borehole Rationale' sheet not found/empty — leaving {ANCHOR} in place for manual review")
        return False

    # Derive the real APEC names from the sheet (the hard-coded list above is
    # only a fallback / ordering hint from an earlier site).
    _skip = ("background", "unassigned", "-", "")
    _real = []
    for _k in panel_by_apec.keys():
        _ks = str(_k).strip()
        if _ks.lower() in _skip:
            continue
        _name = "DWDA" if _ks.upper().startswith("DWDA") else _ks
        if _name not in _real:
            _real.append(_name)
    if _real:
        REAL_APECS = _real

    dwda_split = _dwda_char_delin_boreholes(panel_by_apec)
    dwda_panel = dwda_split.get("panel")

    meets_by_apec = _apec_meets_guidelines_or_justified(wb)

    rows_to_write = []
    for apec_name in REAL_APECS:
        if apec_name == "DWDA":
            panel = dwda_panel
        else:
            panel = panel_by_apec.get(apec_name)
        if panel is None:
            print(f"  ⚠ Section 7.1: no panel data found for APEC '{apec_name}' — skipping this row")
            continue
        rows_to_write.append({
            "apec": apec_name,
            "salinity": bool(panel.get("salinity")),
            "metals": bool(panel.get("metals")),
            "phc": bool(panel.get("phc")),
            "pah": bool(panel.get("pah")),
            "other": panel.get("other") or "-",
            "meets": meets_by_apec.get(apec_name, "Yes"),
        })

    if not rows_to_write:
        print(f"  ✗ Section 7.1: no real APEC rows resolved — leaving {ANCHOR} in place")
        return False

    table, anchor_para_el, skipped_marker_els = _locate_table_by_anchor(doc, ANCHOR)
    if table is None:
        print(f"  ✗ Section 7.1: anchor '{ANCHOR}' not found")
        return False

    tbl_el = table._tbl
    all_trs = tbl_el.findall(_qn("w:tr"))
    if len(all_trs) <= HEADER_ROWS:
        print(f"  ✗ Section 7.1: table after '{ANCHOR}' has no template data row to clone")
        return False

    checked_p_template = None
    unchecked_p_template = None
    for tr in all_trs[HEADER_ROWS:]:
        for tc in tr.findall(_qn("w:tc")):
            txt = "".join(t.text or "" for t in tc.findall(f".//{_qn('w:t')}")).strip()
            if txt == "✔" and checked_p_template is None:
                p = tc.find(_qn("w:p"))
                if p is not None:
                    checked_p_template = _copy.deepcopy(p)
            elif txt == "-" and unchecked_p_template is None:
                p = tc.find(_qn("w:p"))
                if p is not None:
                    unchecked_p_template = _copy.deepcopy(p)
        if checked_p_template is not None and unchecked_p_template is not None:
            break

    if checked_p_template is None or unchecked_p_template is None:
        print(f"  ✗ Section 7.1: could not find both a checked and an unchecked template cell in the existing table — leaving {ANCHOR} in place")
        return False

    def _set_checkbox_cell(tc, checked):
        for p in list(tc.findall(_qn("w:p"))):
            tc.remove(p)
        tc.append(_copy.deepcopy(checked_p_template if checked else unchecked_p_template))

    template_row_el = all_trs[HEADER_ROWS]

    for tr in all_trs[HEADER_ROWS:]:
        tbl_el.remove(tr)

    for row in rows_to_write:
        new_tr = _copy.deepcopy(template_row_el)
        tc_els = new_tr.findall(_qn("w:tc"))
        if len(tc_els) < 7:
            continue

        set_tc_text(tc_els[0], row["apec"])
        _set_checkbox_cell(tc_els[1], row["salinity"])
        _set_checkbox_cell(tc_els[2], row["metals"])
        _set_checkbox_cell(tc_els[3], row["phc"])
        _set_checkbox_cell(tc_els[4], row["pah"])
        set_tc_text(tc_els[5], row["other"])
        set_tc_text(tc_els[6], row["meets"])

        tbl_el.append(new_tr)

    if anchor_para_el is not None:
        anchor_para_el.getparent().remove(anchor_para_el)
    for skip_el in skipped_marker_els:
        skip_el.getparent().remove(skip_el)

    print(f"  ✓ generate_section7_1_apec_review: {len(rows_to_write)} row(s) written")
    return True


def generate_section7_2_justification(doc, wb):
    """Resolve Section 7.2's justification block between
    <INSERT_72_ JUSTIFICATION_START> and <INSERT_72_ JUSTIFICATION_END>
    (marker match ignores whitespace, so the stray space typed into the
    template marker text does not matter).

    The template block holds two mutually exclusive variants separated by
    an "OR" paragraph:
      1. "Justifications were not required for this assessment."
      2. "Below is the complete list of the justifications ..." + caption
         + Concordance table (left completely unchanged).

    Rule (pure Python, no wording judgment): look at the LAST column of the
    `Tier 1 Exceedances` sheet ("Justification Reason"). If every row is
    blank or "-", no justifications exist -> keep ONLY the first sentence.
    Otherwise -> drop the first sentence and the "OR" line, keep the rest of
    the block unchanged. Marker paragraphs are removed either way.
    """
    from docx.oxml.ns import qn as _qn

    def _norm(el):
        return "".join(t.text or "" for t in el.iter(_qn("w:t"))).replace(" ", "").strip()

    body = doc.element.body
    children = list(body)
    start_el = end_el = None
    for ch in children:
        n = _norm(ch)
        if start_el is None and "<INSERT_72_JUSTIFICATION_START>" in n:
            start_el = ch
        elif start_el is not None and "<INSERT_72_JUSTIFICATION_END>" in n:
            end_el = ch
            break
    if start_el is None or end_el is None:
        print("  \u2717 Section 7.2: <INSERT_72_ JUSTIFICATION_START>/_END markers not found")
        return False

    has_just = False
    if "Tier 1 Exceedances" in wb.sheetnames:
        rows = list(wb["Tier 1 Exceedances"].iter_rows(values_only=True))
        if rows:
            headers = list(rows[0])
            col = len(headers) - 1
            while col > 0 and headers[col] in (None, ""):
                col -= 1
            for r in rows[1:]:
                if r and col < len(r):
                    v = r[col]
                    if v is not None and str(v).strip() not in ("", "-"):
                        has_just = True
                        break

    si, ei = children.index(start_el), children.index(end_el)
    inner = children[si + 1:ei]
    first = next((e for e in inner if _norm(e).startswith("Justificationswerenotrequired")), None)
    or_el = next((e for e in inner if _norm(e).upper() == "OR"), None)

    if has_just:
        for e in (first, or_el):
            if e is not None:
                body.remove(e)
        outcome = "justifications present -> kept list/table, removed 'not required' sentence and OR"
    else:
        for e in inner:
            if e is not first:
                body.remove(e)
        outcome = "no justifications -> kept only 'not required' sentence"
    body.remove(start_el)
    body.remove(end_el)
    print(f"  \u2713 generate_section7_2_justification: {outcome}")
    return True


def generate_section3_3_tier1_background(doc, wb):
    """Section 3.3 "Tier 1 with Background" (markers <INSERT_33_START>/<INSERT_33_END>,
    table anchor <INSERT_33_TABLE>). The START marker sits ABOVE the Heading 2 so the
    whole subsection (heading, intro sentence, caption, table) is removed when it does
    not apply.

    Applies only if the Excel `Guidelines` sheet's "Tier 1 with Background" row has at
    least one value (user decision 2026-10-01). One table row per parameter that has a
    value: Media = Soil | Parameter = column header | Tier 1 = "Limiting Tier 1 Guideline"
    row value | Tier 1 with Background = that row's value | Reference = left as the
    template's own text. If none, the whole block between the markers is deleted.
    """
    import copy as _copy
    from docx.oxml.ns import qn as _qn
    from apply_operations import op_replace_between, op_strip_markers, _locate_table_by_anchor

    START, END, ANCHOR = "<INSERT_33_START>", "<INSERT_33_END>", "<INSERT_33_TABLE>"

    def _fmt(v):
        if v is None:
            return ""
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f"{v:g}"
        return str(v).strip()

    rows = []
    if "Guidelines" in wb.sheetnames:
        grid = list(wb["Guidelines"].iter_rows(values_only=True))
        if grid:
            header = grid[0]
            by_label = {str(r[0]).strip(): r for r in grid[1:] if r and r[0] is not None}
            bg = by_label.get("Tier 1 with Background")
            t1 = by_label.get("Limiting Tier 1 Guideline")
            if bg is not None:
                for ci, name in enumerate(header):
                    if ci == 0 or name is None:
                        continue
                    v = bg[ci] if ci < len(bg) else None
                    if v is None or str(v).strip() == "":
                        continue
                    t1v = t1[ci] if (t1 is not None and ci < len(t1)) else None
                    rows.append(["Soil", str(name).strip(), _fmt(t1v), _fmt(v)])

    if not rows:
        ok = op_replace_between(doc, {"start_placeholder": START, "end_placeholder": END, "blocks": []})
        print("  \u2713 generate_section3_3: no 'Tier 1 with Background' values -> subsection removed")
        return ok

    table, anchor_para_el, skipped = _locate_table_by_anchor(doc, ANCHOR)
    if table is None:
        print(f"  \u2717 Section 3.3: anchor '{ANCHOR}' not found")
        return False
    tbl_el = table._tbl
    trs = tbl_el.findall(_qn("w:tr"))
    if len(trs) < 2:
        print("  \u2717 Section 3.3: table has no template data row to clone")
        return False
    template_row = trs[1]
    for tr in trs[1:]:
        tbl_el.remove(tr)
    for vals in rows:
        new_tr = _copy.deepcopy(template_row)
        tcs = new_tr.findall(_qn("w:tc"))
        for tc, v in zip(tcs[:4], vals):   # Reference column (5th) left as in the template
            set_tc_text(tc, v)
        tbl_el.append(new_tr)
    if anchor_para_el is not None:
        anchor_para_el.getparent().remove(anchor_para_el)
    for el in skipped:
        el.getparent().remove(el)
    op_strip_markers(doc, {"start_placeholder": START, "end_placeholder": END})
    print(f"  \u2713 generate_section3_3: {len(rows)} row(s) written ({', '.join(r[1] for r in rows)})")
    return True


def generate_section7_2_residual_table(doc, wb):
    """Fill Section 7.2's Residual Site Exceedances table (<INSERT_72_RESIDUAL_TABLE>)
    from the `Tier 1 Exceedances` sheet. Pure Python, no wording judgment.

    Rows: every sheet row where `Justified (Yes/No)` != "Yes", EXCLUDING
    Background rows and rows with no APEC ("-" / blank) -- i.e. only rows
    tied to a named APEC (user decision 2026-09-30). Sheet order is kept.
    DWDA-Char / DWDA-Delineation are shown as "DWDA", matching the rest of
    the report.

    Columns (template order): Location (Sample ID) | Depth (m) | APEC |
    Parameter | Value | Guideline (= `Limiting Guideline`) | Chloride (mg/L)
    | Section | Figure | Table. The last three are not in the sheet and are
    written as "XX" placeholders for the practitioner. Only the last three
    columns are red (placeholders to update); the rest is normal text. The
    note under the table is rewritten to say so.

    If no qualifying rows exist, the table/marker are left in place (warning).
    """
    import copy as _copy
    from docx.oxml.ns import qn as _qn
    from apply_operations import _locate_table_by_anchor

    ANCHOR = "<INSERT_72_RESIDUAL_TABLE>"
    HEADER_ROWS = 1

    if "Tier 1 Exceedances" not in wb.sheetnames:
        print("  \u26a0 Section 7.2 table: 'Tier 1 Exceedances' sheet not found")
        return False
    ws = wb["Tier 1 Exceedances"]
    headers = [c.value for c in ws[1]]
    need = ["Sample ID", "Depth (m)", "APEC", "Parameter", "Value",
            "Limiting Guideline", "Chloride (mg/L)", "Justified (Yes/No)"]
    missing = [h for h in need if h not in headers]
    if missing:
        print(f"  \u2717 Section 7.2 table: sheet missing column(s) {missing}")
        return False
    idx = {h: i for i, h in enumerate(headers) if h}

    def _fmt(v):
        if v is None:
            return ""
        if isinstance(v, bool):
            return str(v)
        if isinstance(v, (int, float)):
            return f"{v:g}"
        return str(v).strip()

    data_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[idx["Sample ID"]] in (None, ""):
            continue
        if str(row[idx["Justified (Yes/No)"]]).strip().lower() == "yes":
            continue
        apec = row[idx["APEC"]]
        apec = "" if apec is None else str(apec).strip()
        if apec in ("", "-") or apec.lower() == "background":
            continue
        if apec.lower().startswith("dwda"):
            apec = "DWDA"
        data_rows.append([
            _fmt(row[idx["Sample ID"]]), _fmt(row[idx["Depth (m)"]]), apec,
            _fmt(row[idx["Parameter"]]), _fmt(row[idx["Value"]]),
            _fmt(row[idx["Limiting Guideline"]]), _fmt(row[idx["Chloride (mg/L)"]]),
            "XX", "XX", "XX",
        ])

    if not data_rows:
        print(f"  \u26a0 Section 7.2 table: no non-justified named-APEC exceedances -- leaving {ANCHOR} and template table in place for manual review")
        return False

    table, anchor_para_el, skipped_marker_els = _locate_table_by_anchor(doc, ANCHOR)
    if table is None:
        print(f"  \u2717 Section 7.2 table: anchor '{ANCHOR}' not found")
        return False

    tbl_el = table._tbl
    all_trs = tbl_el.findall(_qn("w:tr"))
    if len(all_trs) <= HEADER_ROWS:
        print(f"  \u2717 Section 7.2 table: no template data row to clone")
        return False
    template_row_el = all_trs[HEADER_ROWS]
    for tr in all_trs[HEADER_ROWS:]:
        tbl_el.remove(tr)

    for vals in data_rows:
        new_tr = _copy.deepcopy(template_row_el)
        tcs = new_tr.findall(_qn("w:tc"))
        if len(tcs) < len(vals):
            continue
        for ci, (tc, v) in enumerate(zip(tcs, vals)):
            set_tc_text(tc, v)
            if ci < 7:
                continue  # data columns keep the template's normal (black) text
            for r in tc.iter(_qn("w:r")):  # Section/Figure/Table placeholders -> red
                rPr = r.find(_qn("w:rPr"))
                if rPr is None:
                    rPr = etree.SubElement(r, _qn("w:rPr"))
                    r.insert(0, rPr)
                for old in rPr.findall(_qn("w:color")):
                    rPr.remove(old)
                color = etree.SubElement(rPr, _qn("w:color"))
                color.set(_qn("w:val"), "FF0000")
        tbl_el.append(new_tr)

    if anchor_para_el is not None:
        anchor_para_el.getparent().remove(anchor_para_el)
    for skip_el in skipped_marker_els:
        skip_el.getparent().remove(skip_el)

    # Replace the template note (it says non-justified rows are red, which is
    # no longer how this table is formatted) with one that matches.
    nxt = tbl_el.getnext()
    while nxt is not None and not nxt.tag.endswith("}p"):
        nxt = nxt.getnext()
    if nxt is not None:
        ts = nxt.findall(".//" + _qn("w:t"))
        full = "".join(t.text or "" for t in ts)
        if full.strip().startswith("Note: Non-justified exceedances"):
            ts[0].text = ("Note: All exceedances listed are non-justified. The Section, Figure, and Table "
                          "columns (red text) are placeholders and must be updated.")
            for t in ts[1:]:
                t.text = ""

    print(f"  \u2713 generate_section7_2_residual_table: {len(data_rows)} row(s) written")
    return True


def _format_borehole_id_range_list(borehole_ids):
    """Format a list of borehole IDs into "BH26-19, BH26-22 to BH26-24"
    prose: group by ID prefix, compress contiguous numeric runs (2+
    consecutive numbers, same prefix) into "X to Y", leave singletons
    as-is, join groups with ", " (no "and" before the last group --
    matches the only example available in the template; revisit if a
    3+-group case ever shows different phrasing).
    """
    import re

    parsed = []
    for bid in borehole_ids:
        m = re.match(r"^(.*?)(\d+)$", bid)
        if m:
            parsed.append((m.group(1), int(m.group(2)), bid))
        else:
            parsed.append((bid, None, bid))

    parsed_sorted = sorted(parsed, key=lambda t: (t[0], t[1] if t[1] is not None else -1))

    groups = []
    current = []
    for prefix, num, orig in parsed_sorted:
        if num is None:
            if current:
                groups.append(current)
                current = []
            groups.append([(prefix, num, orig)])
            continue
        if current and current[-1][0] == prefix and current[-1][1] == num - 1:
            current.append((prefix, num, orig))
        else:
            if current:
                groups.append(current)
            current = [(prefix, num, orig)]
    if current:
        groups.append(current)

    def _fmt_group(g):
        if len(g) == 1:
            return g[0][2]
        return f"{g[0][2]} to {g[-1][2]}"

    return ", ".join(_fmt_group(g) for g in groups)


def _join_with_and(items):
    """"A" / "A and B" / "A, B, and C" -- standard Oxford-comma prose join."""
    items = list(items)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


_RATING_ORDER = ["Good", "Fair", "Poor", "Very Poor", "Unsuitable"]


def _rating_rank(cat):
    return _RATING_ORDER.index(cat) if cat in _RATING_ORDER else 999


def _background_ecsar_rows(ecsar_data):
    """Shared "which rows are background" filter -- the same logic
    generate_section3_2_scarg() uses, factored out so both sections read
    the Background group the same way and can never drift out of sync
    with each other again (see the Comments/APEC column-name incident).
    """
    return [row for row in (ecsar_data or []) if row.get("Comments") == "Background"]


def _background_all_good(ecsar_data):
    """True if every background sample's EC and SAR category is 'Good'."""
    bg_rows = _background_ecsar_rows(ecsar_data)
    if not bg_rows:
        return False
    return all(
        row.get("EC Category") == "Good" and row.get("SAR Category") == "Good"
        for row in bg_rows
    )


def _parse_wellbore_depth_m(raw):
    """Parse a leading numeric value (metres) out of `abadata.wellbore_depth`
    (e.g. "571 m" -> 571.0). Returns None if it can't find a number.
    """
    import re
    if raw is None:
        return None
    m = re.match(r"\s*([\d,]+(?:\.\d+)?)", str(raw))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _dwda_required_sample_count(wellbore_depth_m):
    """AER (2014) representative-sample count for the DWDA soil-waste mix
    zone, by wellbore depth: <1500 m -> 3, 1500-2500 m -> 4, >2500 m -> 5.
    Returns None if wellbore_depth_m is None (can't determine).
    """
    if wellbore_depth_m is None:
        return None
    if wellbore_depth_m < 1500:
        return 3
    if wellbore_depth_m <= 2500:
        return 4
    return 5


def _panel_labels_from_flags(panel):
    """Turn one `Borehole Rationale` row's {"salinity": bool, "metals": bool,
    "phc": bool, "pah": bool, "other": str|None} flags into the ordered
    parameter-panel label list ("Salinity", "Tier 1 regulated metals",
    "PHCs", "PAHs", plus a free-text `other` if present). Returns None if
    `panel` is falsy (no matching Borehole Rationale row). Shared by the
    generic per-APEC panel lookup and DWDA's characterization-row lookup
    (see _dwda_char_delin_boreholes()) so both always render panel labels
    identically — same "shared boolean/filter" principle as
    _build_apec_payload_entry() itself.
    """
    if not panel:
        return None
    labels = [
        label for flag, label in [
            (panel["salinity"], "Salinity"),
            (panel["metals"], "Tier 1 regulated metals"),
            (panel["phc"], "PHCs"),
            (panel["pah"], "PAHs"),
        ] if flag
    ]
    if panel["other"]:
        labels.append(panel["other"])
    return labels


def _build_apec_payload_entry(area, ecsar_rows, exc_rows, panel_by_apec, cat_order, chloride_guideline_mg_l, background_chloride_mg_kg_max):
    """Build one EC_SAR_DATA_FOR_CLAUDE entry for a single APEC area, from
    its own `EC & SAR Rating Categories` rows and `Tier 1 Exceedances` rows.
    Shared by the generic per-APEC loop (Section 4.2.2+) and the DWDA
    special-case (Section 4.2's DWDA subsection) so both always compute
    EC/SAR/chloride/exceedances the same way — see prompts/s4_2_2_apecs.md
    for the full field reference and wording rules that consume this shape.
    """
    sample_ids = sorted(set(r.get("Sample ID") for r in ecsar_rows if r.get("Sample ID")))
    ec_cats = sorted(set(r.get("EC Category") for r in ecsar_rows if r.get("EC Category")), key=lambda c: cat_order.get(c, 99))
    sar_cats = sorted(set(r.get("SAR Category") for r in ecsar_rows if r.get("SAR Category")), key=lambda c: cat_order.get(c, 99))
    cl_kg = [r.get("Chloride (mg/kg)") for r in ecsar_rows if r.get("Chloride (mg/kg)") is not None]
    cl_l = [r.get("Chloride (mg/L)") for r in ecsar_rows if r.get("Chloride (mg/L)") is not None]

    # ── Per-borehole chloride depth series, for vertical delineation ──
    borehole_depth_series = defaultdict(list)
    for r in ecsar_rows:
        sid, z = r.get("Sample ID"), r.get("Z")
        if sid and z is not None:
            borehole_depth_series[sid].append({
                "depth_m": z,
                "chloride_mg_l": r.get("Chloride (mg/L)"),
                "chloride_mg_kg": r.get("Chloride (mg/kg)"),
            })
    for sid in borehole_depth_series:
        borehole_depth_series[sid].sort(key=lambda d: d["depth_m"])

    delineation = []
    for sid, series in borehole_depth_series.items():
        exceeding = [d for d in series if isinstance(d["chloride_mg_l"], (int, float)) and d["chloride_mg_l"] > chloride_guideline_mg_l]
        if not exceeding:
            continue
        deepest = series[-1]
        deepest_exceeds = isinstance(deepest["chloride_mg_l"], (int, float)) and deepest["chloride_mg_l"] > chloride_guideline_mg_l
        delineation.append({
            "sample_id": sid,
            "max_chloride_mg_l": max(d["chloride_mg_l"] for d in exceeding),
            "deepest_depth_m": deepest["depth_m"],
            "deepest_chloride_mg_l": deepest["chloride_mg_l"],
            "vertical_closure_achieved": not deepest_exceeds,
        })
    delineation.sort(key=lambda d: -d["max_chloride_mg_l"])

    def _exc_rows_for(parameter_name, _exc_rows=exc_rows):
        return [
            {
                "sample_id": r.get("Sample ID"),
                "depth_m": r.get("Depth (m)"),
                "value": r.get("Value"),
                "justified": r.get("Justified (Yes/No)"),
                "justification_reason": r.get("Justification Reason"),
            }
            for r in _exc_rows
            if r.get("Parameter") == parameter_name
        ]

    ph_exceedances = _exc_rows_for("pH")
    ec_exceedances = _exc_rows_for("EC (dS/m)")
    sar_exceedances = _exc_rows_for("SAR")

    non_salinity = [
        {
            "parameter": r.get("Parameter"),
            "chemical_group": r.get("Chemical Group"),
            "sample_id": r.get("Sample ID"),
            "depth_m": r.get("Depth (m)"),
            "value": r.get("Value"),
            "justified": r.get("Justified (Yes/No)"),
            "justification_reason": r.get("Justification Reason"),
        }
        for r in exc_rows
        if r.get("Chemical Group") not in ("Salinity", "Chloride")
    ]

    panel = panel_by_apec.get(area)
    parameter_panel = _panel_labels_from_flags(panel)

    return {
        "area": area,
        "sample_ids": sample_ids,
        "num_samples": len(ecsar_rows),
        "parameter_panel": parameter_panel,
        "ec_categories": ec_cats,
        "sar_categories": sar_cats,
        "ec_exceedances": ec_exceedances,
        "sar_exceedances": sar_exceedances,
        "ph_exceedances": ph_exceedances,
        "chloride_mg_l": {"min": min(cl_l), "max": max(cl_l)} if cl_l else None,
        "chloride_mg_kg": {"min": min(cl_kg), "max": max(cl_kg)} if cl_kg else None,
        "chloride_guideline_mg_l": chloride_guideline_mg_l,
        "background_chloride_mg_kg_max": background_chloride_mg_kg_max,
        "chloride_vertical_delineation": delineation,
        "non_salinity_exceedances": non_salinity,
    }


def _borehole_rationale_by_apec(wb):
    """Read the `Borehole Rationale` Excel sheet into {apec_name: {"boreholes":
    [str, ...], "salinity": bool, "metals": bool, "phc": bool, "pah": bool,
    "other": str|None}}, keyed by the sheet's own `APEC` column — same
    sheet and same column already used by generate_section4_1_borehole_rationale(),
    so Section 4.2's "analyzed for some or all of the following" panel list
    always agrees with Section 4.1's table. `boreholes` is the row's own
    comma-separated borehole-ID list, parsed and stripped — used directly
    by generic APEC areas' Section 4.1 table row, and by DWDA's
    characterization/delineation split (see _dwda_char_delin_boreholes()),
    which is the only caller that needs the raw list rather than just the
    yes/no flags.

    Returns {} if the sheet is missing (caller falls back to leaving the
    panel list for manual completion).
    """
    if "Borehole Rationale" not in wb.sheetnames:
        return {}
    ws = wb["Borehole Rationale"]
    result = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        boreholes_raw, apec, salinity, metals, phc, pah, other = (list(row) + [None] * 7)[:7]
        if not apec:
            continue
        boreholes = [b.strip() for b in str(boreholes_raw).split(",") if b.strip()] if boreholes_raw else []
        result[apec] = {
            "boreholes": boreholes,
            "salinity": str(salinity).strip().lower() == "yes",
            "metals": str(metals).strip().lower() == "yes",
            "phc": str(phc).strip().lower() == "yes",
            "pah": str(pah).strip().lower() == "yes",
            "other": other if other else None,
        }
    return result


def _dwda_char_delin_boreholes(panel_by_apec):
    """Split DWDA's boreholes into characterization vs. delineation groups.

    Unlike every other APEC (one `Borehole Rationale` row per area), DWDA is
    split into two rows — one for the characterization boreholes (the ones
    the AER-required parameter panel applies to) and one for the
    delineation boreholes advanced afterward to confirm the waste-mix
    zone's extent — keyed by an APEC column value starting with "DWDA-Char"
    or "DWDA-Delin" (case-insensitive; also matches the longer
    "DWDA-Characterization"/"DWDA-Delineation" spellings some workbooks
    use). See prompts/s4_2_dwda.md for how these feed the Summary of
    Results intro sentences.

    Returns {"characterization_boreholes": [...], "delineation_boreholes":
    [...], "panel": {...}|None} — `panel` is the characterization row's
    flags dict (pass to _panel_labels_from_flags() for the label list),
    `None` if no matching "DWDA-Char..." row was found. Both borehole lists
    are `[]` if their row isn't present.
    """
    char_boreholes, delin_boreholes, panel = [], [], None
    for apec, info in panel_by_apec.items():
        key = str(apec).strip().lower()
        if key.startswith("dwda-char"):
            char_boreholes = info.get("boreholes", [])
            panel = info
        elif key.startswith("dwda-delin"):
            delin_boreholes = info.get("boreholes", [])
    return {
        "characterization_boreholes": char_boreholes,
        "delineation_boreholes": delin_boreholes,
        "panel": panel,
    }


def _dwda_impact_depth_range(wb, borehole_id):
    """Look up a borehole's waste-mix-zone impact depth range from the
    `Borehole_Characteristics` sheet's `Top of Impact`/`Bottom of Impact`
    columns (keyed by `Location`). Used for the DWDA "waste-mix-zone
    identification bullet" in prompts/s4_2_dwda.md's step 8 — this was
    previously (wrongly) documented as a field/visual observation with no
    analytical source; it's actually a plain lookup in this sheet, caught
    only by checking the real Excel data, not by trusting the earlier
    (unverified) prompt-file claim.

    Returns (top_of_impact_m, bottom_of_impact_m), both None if the sheet
    is missing, the borehole ID isn't found, or the impact-depth cells are
    blank for that row.
    """
    if "Borehole_Characteristics" not in wb.sheetnames:
        return None, None
    ws = wb["Borehole_Characteristics"]
    headers = [c.value for c in ws[1]]
    if "Location" not in headers or "Top of Impact" not in headers or "Bottom of Impact" not in headers:
        return None, None
    idx = {h: i for i, h in enumerate(headers) if h}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[idx["Location"]] == borehole_id:
            top = row[idx["Top of Impact"]]
            bottom = row[idx["Bottom of Impact"]]
            return top, bottom
    return None, None


def generate_section4_2_1_background(doc, ecsar_data):
    """Fill Section 4.2.1's Background subsection
    (<INSERT_421_START>/<INSERT_421_END>).

    Per user decision:
    - Opening paragraph branches on whether any background chloride sample
      exceeded the Tier 1 screening value of 100 mg/L (data-driven).
    - "Subsequently, BHxx-xx was excluded as a background location..." is
      ALWAYS skipped/manual -- never generated here, regardless of data.
    - "For this assessment, the background evaluation and guidelines are
      considered preliminary..." is ALWAYS included, unconditionally.
    - The "FOR T1 with BG" pH bullet is left exactly as the template's own
      placeholder text -- copied through verbatim, not computed.
    - The closing paragraph reuses the same all_good boolean already
      computed for the SCARG intro (generate_section3_2_scarg), via the
      shared _background_all_good() helper, so the two sections can't
      disagree with each other.

    Number formatting follows the project's standing "always numeral"
    rule (exec_summary.md) throughout, including the "N locations"
    exceedance count -- NOT prompts/s4_2_2_apecs.md's separate "spell out
    1-12" convention, since that rule belongs to a different placeholder.
    Flag if this section should follow the other rule instead.

    Args:
        doc:        python-docx Document object
        ecsar_data: list of dict rows from `EC & SAR Rating Categories`
                    (already normalised -- same object passed to
                    generate_section3_2_scarg)

    Returns:
        True if filled; False on a structural/data error (marker left in
        place for manual review either way).
    """
    from apply_operations import op_replace_between

    START = "<INSERT_421_START>"
    END = "<INSERT_421_END>"

    bg_rows = _background_ecsar_rows(ecsar_data)
    if not bg_rows:
        print(f"  ⚠ Section 4.2.1: no Background rows in EC & SAR Rating Categories — leaving {START}/{END} in place for manual review")
        return False

    borehole_ids = sorted(set(r.get("Sample ID") for r in bg_rows if r.get("Sample ID")))
    n_boreholes = len(borehole_ids)
    borehole_list_str = _format_borehole_id_range_list(borehole_ids)
    n_samples = len(bg_rows)

    # ── Chloride exceedance check (Tier 1 screening value: 100 mg/L) ────────
    exceeding_rows = [r for r in bg_rows if isinstance(r.get("Chloride (mg/L)"), (int, float)) and r["Chloride (mg/L)"] > 100]
    exceeding_ids = sorted(set(r.get("Sample ID") for r in exceeding_rows if r.get("Sample ID")))

    if not exceeding_ids:
        para1_text = (
            f"{n_boreholes} boreholes ({borehole_list_str}) were advanced in undisturbed areas away "
            f"from former facility locations and known contaminant sources to characterize background "
            f"conditions and delineate site impacts. {n_samples} samples were analyzed for salinity."
        )
    else:
        n_exceeding = len(exceeding_ids)
        exceeding_list_str = _join_with_and(exceeding_ids)
        location_word = "location" if n_exceeding == 1 else "locations"
        para1_text = (
            f"{n_boreholes} background boreholes ({borehole_list_str}) were advanced in undisturbed "
            f"locations away from former facility locations and known contaminant sources to "
            f"characterize background conditions and delineate site impacts. At {n_exceeding} "
            f"{location_word} ({exceeding_list_str}), chloride concentrations exceeding the Tier 1 "
            f"screening value of 100 mg/L were identified, and an evaluation and justification of the "
            f"elevated background chloride is provided in Section 5."
        )

    preliminary_text = (
        "For this assessment, the background evaluation and guidelines are considered preliminary "
        "until further investigation is conducted."
    )

    # ── Summary of Results bullets ──────────────────────────────────────────
    ec_cats = sorted(set(r.get("EC Category") for r in bg_rows if r.get("EC Category")), key=_rating_rank)
    sar_cats = sorted(set(r.get("SAR Category") for r in bg_rows if r.get("SAR Category")), key=_rating_rank)

    blocks = [
        {"style": "body", "text": para1_text},
        {"style": "body", "text": preliminary_text},
        {"style": "body", "bold": True, "text": "Summary of Results"},
    ]

    if len(ec_cats) == 1 and ec_cats == sar_cats:
        blocks.append({
            "style": "bullet",
            "runs": [
                {"text": "Both EC and SAR were in the "},
                {"text": ec_cats[0], "bold": True},
                {"text": " soil rating category."},
            ],
        })
    else:
        if len(ec_cats) <= 1:
            ec_text = [
                {"text": "EC values were within the "},
                {"text": ec_cats[0] if ec_cats else "XX", "bold": True},
                {"text": " soil rating category."},
            ]
        else:
            ec_text = [
                {"text": "EC values ranged from the "},
                {"text": ec_cats[0], "bold": True},
                {"text": " to "},
                {"text": ec_cats[-1], "bold": True},
                {"text": " soil rating categories."},
            ]
        blocks.append({"style": "bullet", "runs": ec_text})

        if len(sar_cats) <= 1:
            sar_text = [
                {"text": "SAR values were within the "},
                {"text": sar_cats[0] if sar_cats else "XX", "bold": True},
                {"text": " SCARG soil rating category."},
            ]
        else:
            sar_text = [
                {"text": "SAR values ranged from the "},
                {"text": sar_cats[0], "bold": True},
                {"text": " to "},
                {"text": sar_cats[-1], "bold": True},
                {"text": " SCARG soil rating category."},
            ]
        blocks.append({"style": "bullet", "runs": sar_text})

    cl_l_vals = [r.get("Chloride (mg/L)") for r in bg_rows if isinstance(r.get("Chloride (mg/L)"), (int, float))]
    cl_kg_vals = [r.get("Chloride (mg/kg)") for r in bg_rows if isinstance(r.get("Chloride (mg/kg)"), (int, float))]
    if cl_l_vals and cl_kg_vals:
        if min(cl_l_vals) == max(cl_l_vals) and min(cl_kg_vals) == max(cl_kg_vals):
            cl_text = f"The chloride concentration was {cl_l_vals[0]:g} mg/L ({cl_kg_vals[0]:g} mg/kg)."
        else:
            cl_text = (
                f"Chloride concentrations ranged from {min(cl_l_vals):g} to {max(cl_l_vals):g} mg/L "
                f"({min(cl_kg_vals):g} to {max(cl_kg_vals):g} mg/kg)."
            )
        blocks.append({"style": "bullet", "text": cl_text})

    # ── "FOR T1 with BG" -- copied through verbatim, not computed ──────────
    blocks.append({"style": "body", "text": "FOR T1 with BG"})
    blocks.append({
        "style": "bullet",
        "text": (
            "Naturally elevated soil pH, to a maximum of 8.7, was identified in BH25-03 at multiple "
            "depth increments. As such, the maximum background was applied as the Tier 1 with "
            "Background guideline (Section 3.3)."
        ),
    })

    # ── Closing paragraph -- reuses the SCARG intro's all_good boolean ──────
    if _background_all_good(ecsar_data):
        closing_text = (
            "As all background samples were within the Good soil category for both EC and SAR, "
            "the default guidelines were applied to all characterization samples and depths."
        )
    else:
        closing_text = (
            "EC and SAR guidelines were applied at depth-based intervals, as outlined in Section 3.2 "
            "and Appendix E, to account for soil salinity concentrations that vary with depth."
        )
    blocks.append({"style": "body", "text": closing_text})

    ok = op_replace_between(doc, {
        "start_placeholder": START,
        "end_placeholder": END,
        "blocks": blocks,
    })
    if ok:
        print(f"  ✓ generate_section4_2_1_background: {n_boreholes} background boreholes, {n_samples} samples, {len(exceeding_ids)} chloride exceedance(s)")
    return ok

def generate_section2_1(doc, site_facts, site_lsd=None):
    """Fill Section 2.1 (Facility Information): delete whichever of the
    Wellsite/Facility template blocks doesn't apply, and fill the table
    cells for the one that survives.

    This is pure Python, not an LLM-authored operation (see the deleted
    prompts/s2_1_facility.md — its logic moved here): site type is a
    deterministic lookup already resolved into site_facts["site_type"]
    (derived from ABAData's license_status), and every field populated
    here is a raw fact already sitting in site_facts.json's `abadata`
    block from the unified extraction pass — no wording judgment.

    Args:
        doc:         python-docx Document object
        site_facts:  dict loaded from site_facts.json (this run's cache)
        site_lsd:    the single reconciled LLD/LSD value derived by Q0 (see
                     prompts/intake_quiz.md Q0) — when given, this is what
                     goes in the "Legal Land Description" table cell,
                     NOT the raw abadata.legal_land_description. Q0
                     reconciles that field against the borehole logs and
                     the Phase 1 ESA and may not agree with ABAData's own
                     value verbatim; the cache keeps ABAData's raw value
                     unchanged (extraction never "corrects" what a source
                     document said), but the report itself should show one
                     single, reconciled LLD everywhere, not two different
                     ones depending on which section you're reading. Falls
                     back to abadata.legal_land_description only if this
                     is None (e.g. Q0 wasn't run).

    Returns:
        True on success, False on a structural error (markers/table not
        found as expected).
    """
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    body = doc.element.body

    def _find_by_text(marker):
        for child in list(body):
            texts = "".join(t.text or "" for t in child.findall(f".//{{{NS}}}t"))
            if marker in texts:
                return child
        return None

    def _delete_block(start_marker, end_marker):
        """Remove the markers and everything between them (the whole block)."""
        start_el = _find_by_text(start_marker)
        end_el = _find_by_text(end_marker)
        if start_el is None or end_el is None:
            print(f"  ✗ '{start_marker}'/'{end_marker}' not found in document")
            return False
        bc = list(body)
        start_idx = bc.index(start_el)
        end_idx = bc.index(end_el)
        if end_idx < start_idx:
            print(f"  ✗ {end_marker} appears before {start_marker} in document — skipping")
            return False
        from apply_operations import rescue_orphan_bookmarks
        rescue_orphan_bookmarks(bc[start_idx:end_idx + 1], end_el.getnext())
        for el in bc[start_idx:end_idx + 1]:
            body.remove(el)
        return True

    def _strip_markers(start_marker, end_marker):
        """Remove only the two marker paragraphs, keeping everything between
        them (the block that's being kept — its wrapper is invisible template
        scaffolding, not real content)."""
        start_el = _find_by_text(start_marker)
        end_el = _find_by_text(end_marker)
        if start_el is None or end_el is None:
            print(f"  ✗ '{start_marker}'/'{end_marker}' not found in document")
            return False
        from apply_operations import rescue_orphan_bookmarks
        rescue_orphan_bookmarks([start_el], start_el.getnext())
        rescue_orphan_bookmarks([end_el], end_el.getnext())
        body.remove(start_el)
        body.remove(end_el)
        return True

    site_type = (site_facts or {}).get("site_type", "wellsite")

    if site_type == "facility":
        ok = _delete_block("<INSERT_WELLSITE_START>", "<INSERT_WELLSITE_END>")
        ok = _strip_markers("<INSERT_FACILITY_START>", "<INSERT_FACILITY_END>") and ok
        print("  ℹ site_type=facility — deleted Wellsite block. This skill's field "
              "mapping for the Facility table isn't implemented yet (see "
              "prompts/site_facts_cache.md note) — its cells are left as template "
              "placeholders for manual completion.")
        return ok

    # wellsite (default)
    if not _delete_block("<INSERT_FACILITY_START>", "<INSERT_FACILITY_END>"):
        return False
    if not _strip_markers("<INSERT_WELLSITE_START>", "<INSERT_WELLSITE_END>"):
        return False

    abadata = (site_facts or {}).get("abadata", {})
    reconciled_lsd = site_lsd or abadata.get("legal_land_description", "")
    # Labels match `Automation Template_20260924.docx` (2-col, "Well Name",
    # "License Status" and "Total crude oil/bitumen production" rows) — the
    # only template this script loads (see `template_docx` in main()). The
    # old 4-col template's retired spellings ("Site Name", "Total Gas
    # Production", "Total Water Production") were dropped from this dict
    # since that template is no longer opened by the script and those keys
    # only ever produced noisy "not found" messages.
    cells_spec = {
        "Well Name": abadata.get("site_name", ""),
        "Legal Land Description": reconciled_lsd,
        "Licensee": abadata.get("licensee", ""),
        "License No.": abadata.get("license_no", ""),
        "License Status": abadata.get("license_status", ""),
        "Spud Date": abadata.get("spud_date", ""),
        "Abandonment Date": abadata.get("abandonment_date", ""),
        "Wellbore Depth": abadata.get("wellbore_depth", ""),
        "Total gas production": abadata.get("total_gas_production", ""),
        "Total water production": abadata.get("total_water_production", ""),
        "Total crude oil/bitumen production": abadata.get("total_oil_production", ""),
        "Associated Spills": abadata.get("associated_spills_text", ""),
    }

    from docx.oxml.ns import qn as _qn
    from docx.table import Table as _Table

    anchor = "<INSERT_WELLSITE_TABLE>"
    target_table = None
    anchor_para_el = None
    body_children = list(body)
    for i, child in enumerate(body_children):
        if not child.tag.endswith("}p"):
            continue
        para_text = "".join(r.text or "" for r in child.findall(".//" + _qn("w:t")))
        if anchor not in para_text:
            continue
        for j in range(i + 1, len(body_children)):
            sibling = body_children[j]
            if sibling.tag.endswith("}tbl"):
                target_table = _Table(sibling, doc)
                if para_text.strip().startswith("<") and para_text.strip().endswith(">"):
                    anchor_para_el = child
                break
            if sibling.tag.endswith("}p"):
                sib_text = "".join(r.text or "" for r in sibling.findall(".//" + _qn("w:t")))
                if sib_text.strip():
                    break
        if target_table:
            break

    if target_table is None:
        print(f"  ✗ No table found for anchor '{anchor}'")
        return False

    label_to_cell = {}
    for row in target_table.rows:
        cells = row.cells
        for i in range(len(cells) - 1):
            label = cells[i].text.strip()
            next_text = cells[i + 1].text.strip()
            if label and label != next_text:
                if label not in label_to_cell:
                    label_to_cell[label] = cells[i + 1]

    replaced, missing = [], []
    for label, text in cells_spec.items():
        if label in label_to_cell:
            set_tc_text(label_to_cell[label]._tc, text)
            replaced.append(label)
        else:
            missing.append(label)

    if anchor_para_el is not None:
        body.remove(anchor_para_el)

    print(f"  ✓ generate_section2_1: {len(replaced)} cell(s) updated ({', '.join(replaced)})")
    if missing:
        print(f"  ✗ Labels not found: {', '.join(missing)}")

    return True


def generate_section2_6(doc, site_facts):
    """Fill Section 2.6 (Soil Characteristics): Texture and Stratigraphy are
    both already-authored outputs of the unified extraction pass (Step 1c)
    — site_facts.json's `borehole_logs.analysis.texture_overall`/
    `.stratigraphy`. This section applies no judgment of its own beyond
    copying those two values into the table (see the deleted
    prompts/s2_6_soil_char.md — its own docstring already said as much:
    "applies no judgment of its own beyond formatting"), so it runs here in
    Python rather than through Claude in Step 3, same reasoning as
    generate_section2_1.

    Args:
        doc:         python-docx Document object
        site_facts:  dict loaded from site_facts.json (this run's cache)
    """
    from apply_operations import op_replace_table_cells

    analysis = (site_facts or {}).get("borehole_logs", {}).get("analysis") or {}
    if not analysis:
        print("  ⚠ Section 2.6: no borehole_logs.analysis in site_facts.json — leaving <INSERT_26_TABLE> in place for manual review")
        return False

    texture = analysis.get("texture_overall") or ""
    stratigraphy = analysis.get("stratigraphy") or ""

    ok = op_replace_table_cells(doc, {
        "table_anchor": "<INSERT_26_TABLE>",
        "cells": [
            {"label": "Texture",      "text": texture},
            {"label": "Stratigraphy", "text": stratigraphy},
        ],
    })
    if ok:
        print(f"  ✓ generate_section2_6: Texture={texture!r}")
    return ok


# ── 16-point compass conversion, shared by Section 2.5 (Receptor Distances)
# and prompts/s5_2_transport.md's background-borehole directions — keep the
# two consistent if either ever changes.
_COMPASS_16 = ["north", "north-northeast", "northeast", "east-northeast", "east",
               "east-southeast", "southeast", "south-southeast", "south",
               "south-southwest", "southwest", "west-southwest", "west",
               "west-northwest", "northwest", "north-northwest"]

def _bearing_to_compass(deg):
    """Convert a 0-360 degree bearing to the nearest 16-point compass word."""
    idx = int((deg + 11.25) % 360 // 22.5)
    return _COMPASS_16[idx]


def generate_section2_3(doc, site_facts, apec_payload, dwda_payload):
    """Fill Section 2.3 (Site Characteristics and Contaminant Sources),
    <INSERT_23_TABLE>. Previously a Claude-authored prompt-file section
    (prompts/s2_3_1_site_char.md) — converted to Python because every field
    is either a verbatim/formatted lookup from site_facts.json or a
    deterministic rollup rule; none of it needs real judgment (see the
    retired prompt file's own "judgment applied to cached facts" framing,
    which overstated what these fields actually require).

    The template's real table has 7 rows — Site Location, Current Land Use,
    Future Land Use, Adjacent Land Use More Sensitive, Current
    Infrastructure, APECs, CoPCs — not the 6 the retired prompt file
    described (Location/Land Use/Topography/AECs/Initial COPCs/Remaining
    COCs), which had never actually been run against the live template
    before that mismatch was caught. Future Land Use, Adjacent Land Use
    More Sensitive, and Current Infrastructure have no site_facts.json
    source and are left untouched (whatever the template already has).

    Land Use rollup rule (phase1_esa.land_use_north/_south/_east/_west):
    - all four "Agriculture"   -> "Agricultural"
    - any one "Industrial"     -> "Industrial"
    - all four "Natural Area"  -> "Natural Area"
    - anything else (mixed)    -> comma-separated list of the distinct
      values present (e.g. "Agriculture, Industrial") — enter both/all
      rather than picking one, per standing decision; this is a
      deterministic fallback, not a judgment call.

    Args:
        doc:           python-docx Document object
        site_facts:    dict loaded from site_facts.json (this run's cache)
        apec_payload:  the ec_sar_data list (excel_data.json) — non-background
                       APEC areas, for the APECs cell
        dwda_payload:  the dwda_data dict/None (excel_data.json) — appends
                       "DWDA" to the APECs cell when a sump was found
    """
    from apply_operations import op_replace_table_cells

    pv = (site_facts or {}).get("phaseview") or {}
    p1 = (site_facts or {}).get("phase1_esa") or {}
    ab = (site_facts or {}).get("abadata") or {}

    if not pv or not p1:
        print("  ⚠ Section 2.3: missing phaseview/phase1_esa in site_facts.json — leaving <INSERT_23_TABLE> in place for manual review")
        return False

    km = pv.get("nearest_settlement_distance_km")
    name = pv.get("nearest_settlement_name")
    municipality = pv.get("municipality")
    location = f"Approximately {km} km from {name}, {municipality} (Figure XX)." if (km is not None and name and municipality) else ""

    directions = [p1.get("land_use_north"), p1.get("land_use_south"), p1.get("land_use_east"), p1.get("land_use_west")]
    dset = set(d for d in directions if d)
    if dset == {"Agriculture"}:
        land_use = "Agricultural"
    elif "Industrial" in dset:
        land_use = "Industrial"
    elif dset == {"Natural Area"}:
        land_use = "Natural Area"
    elif dset:
        land_use = ", ".join(sorted(dset))
    else:
        land_use = ""

    aecs = [e["area"] for e in (apec_payload or [])]
    if dwda_payload:
        aecs.append("DWDA")
    aecs_text = ", ".join(aecs)

    copcs = ab.get("initial_copcs") or ""

    ok = op_replace_table_cells(doc, {
        "table_anchor": "<INSERT_23_TABLE>",
        "cells": [
            {"label": "Site Location",   "text": location},
            {"label": "Current Land Use", "text": land_use},
            {"label": "APECs",           "text": aecs_text},
            {"label": "CoPCs",           "text": copcs},
        ],
    })
    if ok:
        print(f"  \u2713 generate_section2_3: Land Use={land_use!r}, APECs={aecs_text!r}")
    return ok


def generate_section2_4(doc, site_facts):
    """Fill Section 2.4 (Regional Information), <INSERT_24_TABLE>.
    Previously a Claude-authored prompt-file section
    (prompts/s2_3_2_regional.md) — converted to Python because every field
    is a verbatim lookup or a fixed "{a}. {b}" concatenation of
    site_facts.json fields; no judgment involved.

    Args:
        doc:         python-docx Document object
        site_facts:  dict loaded from site_facts.json (this run's cache)
    """
    from apply_operations import op_replace_table_cells

    pv = (site_facts or {}).get("phaseview") or {}
    ab = (site_facts or {}).get("abadata") or {}

    if not pv:
        print("  ⚠ Section 2.4: missing phaseview in site_facts.json — leaving <INSERT_24_TABLE> in place for manual review")
        return False

    raw_subregion = pv.get("natural_subregion_name") or ""
    full_text = pv.get("natural_subregion_full_text") or ""
    if " - " in raw_subregion:
        region, subregion = raw_subregion.split(" - ", 1)
        natural_subregion = f"{subregion} Subregion of the {region} Natural Region. {full_text}"
    else:
        natural_subregion = f"{raw_subregion}. {full_text}" if raw_subregion else full_text

    landscape = ab.get("landscape") or ""
    soil_types = pv.get("soil_description_text") or ""

    genesis = pv.get("surface_geology_genesis") or ""
    highlights = pv.get("surface_geology_highlights_text") or ""
    surface_geology = f"{genesis}. {highlights}" if genesis else highlights

    bedrock_geology = pv.get("surface_geology_bedrock") or ""

    ok = op_replace_table_cells(doc, {
        "table_anchor": "<INSERT_24_TABLE>",
        "cells": [
            {"label": "Natural Subregion", "text": natural_subregion},
            {"label": "Landscape",         "text": landscape},
            {"label": "Soil Types",        "text": soil_types},
            {"label": "Surface Geology",   "text": surface_geology},
            {"label": "Bedrock Geology",   "text": bedrock_geology},
        ],
    })
    if ok:
        print(f"  \u2713 generate_section2_4: Natural Subregion={natural_subregion[:60]!r}...")
    return ok


def generate_section2_5(doc, site_facts):
    """Fill Section 2.5 (Receptor Distances), <INSERT_25_TABLE>. Previously
    a Claude-authored prompt-file section
    (prompts/s2_5_receptor_distances.md) — converted to Python because the
    only non-trivial step (bearing degrees -> compass direction) is a fixed
    16-point lookup table, not a judgment call; the rest is string
    formatting and existence checks. Dugout is never touched — no
    dugout_* field exists in the cache, so it's omitted from the `cells`
    array entirely (same as the retired prompt file specified).

    Args:
        doc:         python-docx Document object
        site_facts:  dict loaded from site_facts.json (this run's cache)
    """
    from apply_operations import op_replace_table_cells

    pv = (site_facts or {}).get("phaseview") or {}
    if not pv:
        print("  ⚠ Section 2.5: missing phaseview in site_facts.json — leaving <INSERT_25_TABLE> in place for manual review")
        return False

    sw_dist = pv.get("surface_water_nearest_distance")
    sw_bearing = pv.get("surface_water_nearest_bearing_deg")
    surface_water = f"{sw_dist} {_bearing_to_compass(sw_bearing)}" if (sw_dist and sw_bearing is not None) else ""

    wells = pv.get("water_wells_filtered") or []
    none_found_text = pv.get("water_wells_none_found_text")
    if wells:
        water_well = "\n".join(
            f"{w['distance']} {_bearing_to_compass(w['bearing_deg'])} (Well ID: {w['well_id']})"
            for w in wells
        )
    elif none_found_text:
        water_well = none_found_text
    else:
        water_well = "No domestic, livestock, or unknown-use water wells identified within the search radius."

    bldg_dist = pv.get("building_nearest_distance")
    bldg_bearing = pv.get("building_nearest_bearing_deg")
    building = f"{bldg_dist} {_bearing_to_compass(bldg_bearing)}" if (bldg_dist and bldg_bearing is not None) else ""

    ok = op_replace_table_cells(doc, {
        "table_anchor": "<INSERT_25_TABLE>",
        "cells": [
            {"label": "Surface Water",                "text": surface_water},
            {"label": "Water Well (Domestic/Stock)",  "text": water_well},
            {"label": "Building or Residential Area", "text": building},
        ],
    })
    if ok:
        print(f"  \u2713 generate_section2_5: Surface Water={surface_water!r}, Building={building!r}")
    return ok


def generate_section2_7(doc, site_facts):
    """Fill Section 2.7 (Groundwater Characteristics): Water Table and
    Domestic Use Aquifer each get a fixed "{value} mbgs" suffix, and
    Comments is copied verbatim — all three already-authored outputs of the
    unified extraction pass (Step 1c), site_facts.json's
    `borehole_logs.analysis` block. No wording judgment of its own (see the
    deleted prompts/s2_7_groundwater_char.md), so this runs here in Python
    rather than through Claude in Step 3, same reasoning as
    generate_section2_1/generate_section2_6. Separate table from Section
    5.2 (Contaminant Transport Mechanisms) — unaffected by this function.

    Note: the shallow-DUA caveat (when dua_depth_m < 6 m) belongs in the
    practitioner's own review notes (`borehole_logs.analysis.review_notes
    .judgment_calls`, populated by the Step 1c extraction pass), never in
    this table's Comments cell — this function doesn't read or write that
    field either way, exactly as the retired prompt file specified.

    Args:
        doc:         python-docx Document object
        site_facts:  dict loaded from site_facts.json (this run's cache)
    """
    from apply_operations import op_replace_table_cells

    analysis = (site_facts or {}).get("borehole_logs", {}).get("analysis") or {}
    if not analysis:
        print("  ⚠ Section 2.7: no borehole_logs.analysis in site_facts.json — leaving <INSERT_27_TABLE> in place for manual review")
        return False

    def _mbgs(key):
        val = analysis.get(key)
        return f"{val} mbgs" if val is not None else ""

    water_table = _mbgs("water_table_depth_m")
    dua         = _mbgs("dua_depth_m")
    comments    = analysis.get("groundwater_comments") or ""

    ok = op_replace_table_cells(doc, {
        "table_anchor": "<INSERT_27_TABLE>",
        "cells": [
            {"label": "Water Table",          "text": water_table},
            {"label": "Domestic Use Aquifer", "text": dua},
            {"label": "Comments",             "text": comments},
        ],
    })
    if ok:
        print(f"  ✓ generate_section2_7: Water Table={water_table!r}, DUA={dua!r}")
    return ok


# ── Fixed layout of the two "ALL CoPCs" exposure tables in the template.
# Row/col are 0-indexed against each table's own <w:tr>/<w:tc> order; row 0
# is the header, and rows not listed here are the merged "Human"/
# "Ecological"/"Other" group-header rows, which are never touched. This is
# static template content, not per-site data — if the template's exposure
# tables are ever edited, these two dicts need updating to match (see the
# git history of the deleted prompts/s2_8_exposure.md for where this came
# from originally).
_EXPOSURE_TABLE_ROWS = {
    "AG_ALL": {
        2:  "PHC, PAH, other organics, metals",
        3:  "PHC, PAH, other organics",
        4:  "PHC, PAH, other organics, boron, chloride*",
        6:  "EC, SAR, pH, PHC, PAH, other organics, metals, chloride*",
        7:  "Metals, ethylene glycol",
        8:  "PHC, PAH, metals",
        9:  "PHC, PAH, barium",
        10: "PHC, PAH, other organics, boron, chloride*",
        11: "PHC, boron, chloride*",
        12: "PHC, boron",
        13: "Boron, chloride*",
        15: "PHC, methanol, chloride*",
    },
    "NATURAL_ALL": {
        2:  "PHC, PAH, other organics, boron, chloride*",
        4:  "EC, SAR, pH, PHC, PAH, other organics, metals, chloride*",
        5:  "Metals",
        6:  "PHC, PAH, metals",
        7:  "PHC, PAH, barium",
        8:  "PHC, PAH, other organics, boron, chloride*",
        9:  "PHC, boron",
        11: "PHC, methanol, chloride*",
    },
}

# author-note text, and the footnote's "before" bound, for each of the four
# candidate tables — also fixed template layout.
_EXPOSURE_TABLE_META = {
    "AG_STANDARD": (
        "Agricultural – Standard CoPCs – feel free to keep this, even if the site only has salinity data",
        "<INSERT_28_AG_ALL_TABLE>",
    ),
    "AG_ALL": (
        "Agricultural – ALL CoPCs",
        "<INSERT_28_NATURAL_STD_TABLE>",
    ),
    "NATURAL_STD": (
        "Natural Area land use – Standard CoPCs – feel free to keep this as a default for any site that doesn’t have PAHs, other organics, etc.",
        "<INSERT_28_NATURAL_ALL_TABLE>",
    ),
    "NATURAL_ALL": (
        "Natural Area land use – All CoPCs",
        "Guideline Selection",
    ),
}

_EXPOSURE_TABLE_MARKERS = {
    "AG_STANDARD": "<INSERT_28_AG_STANDARD_TABLE>",
    "AG_ALL":      "<INSERT_28_AG_ALL_TABLE>",
    "NATURAL_STD": "<INSERT_28_NATURAL_STD_TABLE>",
    "NATURAL_ALL": "<INSERT_28_NATURAL_ALL_TABLE>",
}

_EXPOSURE_FOOTNOTE = (
    "*Although there is no specific guideline for soil chloride, it is a "
    "potential CoPC for the above pathways."
)


def generate_section2_8(doc, site_summary):
    """Fill Section 2.8 (Exposure Pathway Evaluation): pick the Agricultural
    or Natural Area "ALL CoPCs" template table by the Excel `Site Summary`
    sheet's Land Use column, delete the other three candidate tables,
    rewrite the intro sentence, and trim the surviving table's CoPC column
    to whatever the same sheet's COPCs column says was actually measured.

    This is pure Python, not an LLM-authored operation (see the deleted
    prompts/s2_8_exposure.md — its logic moved here, same reasoning as
    generate_section2_1's docstring): the land-use bucket is a
    case-insensitive string match, the CoPC filter is a case-insensitive
    set-membership check, and both "ALL" tables' row layouts are fixed
    template content — no wording judgment anywhere in this section.

    Args:
        doc:          python-docx Document object
        site_summary: the `site_summary_payload` dict this run already
                       built from the Excel `Site Summary` sheet (same
                       dict printed as SITE_SUMMARY_DATA_FOR_CLAUDE) —
                       {"land_use", "texture", "strata", "copcs_raw", "copcs"}
                       or None if that sheet wasn't found.

    Rows are never dropped and Comments are never reworded just because a
    row's CoPC list comes out empty (e.g. a salinity-only site leaves many
    rows blank while Comment still reads "Operable") — that's expected and
    intentional, confirmed with the report author.
    """
    from apply_operations import (
        op_delete_paragraph,
        op_delete_table,
        op_replace_between,
        op_set_table_cells_by_position,
    )

    if not site_summary or not site_summary.get("land_use"):
        print("  ⚠ Section 2.8: no 'Site Summary' sheet data — leaving <INSERT_28_*> placeholders in place for manual review")
        return False

    land_use_raw = str(site_summary["land_use"])
    land_use_lower = land_use_raw.lower()
    if "agri" in land_use_lower:
        bucket = "AG_ALL"
    elif "natural" in land_use_lower:
        bucket = "NATURAL_ALL"
    else:
        print(f"  ⚠ Section 2.8: Land Use {land_use_raw!r} doesn't match Agricultural or Natural Area — leaving <INSERT_28_*> placeholders in place for manual review")
        return False

    measured = {c.strip().lower() for c in (site_summary.get("copcs") or []) if c.strip()}

    def _filter_copcs(cell_text):
        terms = [t.strip() for t in cell_text.split(",") if t.strip()]
        kept = [t for t in terms if t.rstrip("*").strip().lower() in measured]
        return ", ".join(kept)

    # Delete the three tables that didn't survive, always in the same
    # (note → footnote → table) order so the footnote deletion can still
    # use the still-present marker as its "after" bound.
    for key, (note_text, footnote_before) in _EXPOSURE_TABLE_META.items():
        if key == bucket:
            continue
        op_delete_paragraph(doc, {"text": note_text})
        op_delete_paragraph(doc, {
            "text": _EXPOSURE_FOOTNOTE,
            "after": _EXPOSURE_TABLE_MARKERS[key],
            "before": footnote_before,
        })
        op_delete_table(doc, {"placeholder": _EXPOSURE_TABLE_MARKERS[key]})

    # Survivor: drop its own author-note paragraph, then fill its CoPC column.
    op_delete_paragraph(doc, {"text": _EXPOSURE_TABLE_META[bucket][0]})
    cells = [
        {"row": row, "col": 1, "text": _filter_copcs(text)}
        for row, text in sorted(_EXPOSURE_TABLE_ROWS[bucket].items())
    ]
    op_set_table_cells_by_position(doc, {
        "table_anchor": _EXPOSURE_TABLE_MARKERS[bucket],
        "cells": cells,
    })

    # Intro sentence
    land_use_word = "agricultural" if bucket == "AG_ALL" else "natural area"
    op_replace_between(doc, {
        "start_placeholder": "<INSERT_28_INTRO_START>",
        "end_placeholder": "<INSERT_28_INTRO_END>",
        "blocks": [{
            "style": "body",
            "text": f"The following shows the relevant exposure pathways and receptors for {land_use_word} land use, using Tier 1.",
        }],
    })

    print(f"  ✓ generate_section2_8: Land Use {land_use_raw!r} -> kept {bucket}, CoPCs measured = {sorted(measured)}")
    return True



# ── 8-point compass bucket for Section 4.3's lateral chloride-delineation
# directions — reuses the same centroid+bearing math as Section 5.2
# (prompts/s5_2_transport.md) and the 16-point helper above, just bucketed
# coarser because the template's own example language only ever names
# cardinal/intercardinal directions ("west and south", "east and north"),
# never a finer point like "SSE".
_COMPASS_8 = ["north", "northeast", "east", "southeast",
              "south", "southwest", "west", "northwest"]

def _bearing_to_compass8(deg):
    idx = int((deg + 22.5) % 360 // 45)
    return _COMPASS_8[idx]


def compute_chloride_delineation_data(wb, site_facts):
    """Section 4.3 (Tier 1 Chloride Delineation) data, computed mechanically
    per Hex's methodology notes (see prompts/s4_3_chloride.md). Evaluates
    the site's impacted (non-Background, non-Unassigned) boreholes as one
    group against Background boreholes, since the template's own example
    language treats chloride delineation as a site-wide narrative, not a
    per-APEC one (Section 4.2's per-APEC prompt already covers per-area
    salinity/other-chemical narratives separately).

    Returns a dict with:
      samples_collected, all_below_100, max_cl_mg_l, max_cl_borehole,
      max_cl_depth_m, vertical_status, vertical_overrides,
      vertical_unresolved, lateral_status (dict of 8 directions ->
      {"status", "borehole", "cl_mg_l", "depth_m"}), background_elevated
    Returns None if the workbook has no 'EC & SAR Rating Categories' or
    'Borehole_Characteristics' sheet (nothing to compute).
    """
    if "EC & SAR Rating Categories" not in wb.sheetnames or "Borehole_Characteristics" not in wb.sheetnames:
        return None

    ecsar_ws = wb["EC & SAR Rating Categories"]
    ecsar_rows = list(ecsar_ws.iter_rows(values_only=True))[1:]
    # bh_id -> list of (depth_m, apec, cl_mg_l)
    profile = {}
    apec_of = {}
    for row in ecsar_rows:
        if not row or row[0] is None:
            continue
        bh_id, depth, apec = row[0], row[1], row[2]
        cl_mg_l = row[6] if len(row) > 6 else None
        if depth is None or cl_mg_l is None:
            continue
        profile.setdefault(bh_id, []).append((float(depth), float(cl_mg_l)))
        if apec:
            apec_of[bh_id] = apec

    bc_ws = wb["Borehole_Characteristics"]
    bc_rows = list(bc_ws.iter_rows(values_only=True))
    bc_header = bc_rows[0]
    bc_by_bh = {}
    for row in bc_rows[1:]:
        d = dict(zip(bc_header, row))
        loc = d.get("Location")
        if loc:
            bc_by_bh[loc] = d

    # Coordinates from site_facts.json (already extracted from the log PDFs)
    coords = {}
    for bh in site_facts.get("borehole_logs", {}).get("boreholes", []):
        bid = bh.get("borehole_id")
        e, n = bh.get("easting"), bh.get("northing")
        if bid and e is not None and n is not None:
            coords[bid] = (float(e), float(n))

    impacted = sorted(bh for bh, apec in apec_of.items()
                       if apec and apec.lower() not in ("background", "unassigned"))
    background = sorted(bh for bh, apec in apec_of.items() if apec and apec.lower() == "background")

    if not impacted:
        return {
            "samples_collected": False, "all_below_100": None,
            "max_cl_mg_l": None, "max_cl_borehole": None, "max_cl_depth_m": None,
            "vertical_status": "no_data", "vertical_overrides": [], "vertical_unresolved": [],
            "lateral_status": {}, "background_elevated": False,
        }

    # ── Worst case across the impacted group
    worst_bh, worst_depth, worst_cl = None, None, -1.0
    for bh in impacted:
        for depth, cl in profile.get(bh, []):
            if cl > worst_cl:
                worst_bh, worst_depth, worst_cl = bh, depth, cl
    all_below_100 = worst_cl < 100.0

    # ── Vertical: per-borehole closure, with nearest-neighbor override
    DEPTH_TOL = 1.0  # mbgs, per standing decision — no separate proximity
                      # threshold; always compare against the nearest other
                      # impacted borehole (never asks a human to confirm)
    failing = [bh for bh in impacted
               if str(bc_by_bh.get(bh, {}).get("Deep Vertical Closure", "")).strip().lower() == "no"]
    overrides, unresolved = [], []
    for fbh in failing:
        if fbh not in coords:
            unresolved.append(fbh)
            continue
        fe, fn = coords[fbh]
        f_top = bc_by_bh.get(fbh, {}).get("Bottom of Impact")
        f_cl_at_top = None
        if f_top is not None:
            for depth, cl in profile.get(fbh, []):
                if abs(depth - float(f_top)) <= DEPTH_TOL:
                    f_cl_at_top = cl if f_cl_at_top is None else max(f_cl_at_top, cl)
        candidates = [bh for bh in impacted if bh != fbh and bh in coords]
        candidates.sort(key=lambda bh: (coords[bh][0]-fe)**2 + (coords[bh][1]-fn)**2)
        resolved = False
        for cbh in candidates:
            c_closure_ok = str(bc_by_bh.get(cbh, {}).get("Deep Vertical Closure", "")).strip().lower() == "yes"                 or bc_by_bh.get(cbh, {}).get("Top of Impact") is None
            if not c_closure_ok:
                continue
            comp_cl = None
            if f_top is not None:
                for depth, cl in profile.get(cbh, []):
                    if abs(depth - float(f_top)) <= DEPTH_TOL:
                        comp_cl = cl if comp_cl is None else max(comp_cl, cl)
            if f_cl_at_top is None or comp_cl is None:
                continue
            dist = ((coords[cbh][0]-fe)**2 + (coords[cbh][1]-fn)**2) ** 0.5
            if comp_cl >= f_cl_at_top:
                overrides.append({
                    "failing_borehole": fbh, "failing_depth_m": f_top, "failing_cl_mg_l": f_cl_at_top,
                    "comparison_borehole": cbh, "comparison_cl_mg_l": comp_cl, "distance_m": round(dist, 1),
                })
                resolved = True
            break  # only ever try the single nearest candidate — no threshold, no human check
        if not resolved:
            unresolved.append(fbh)

    if not failing:
        vertical_status = "achieved"
    elif not unresolved:
        vertical_status = "achieved_with_override"
    else:
        vertical_status = "not_achieved"

    # ── Lateral: centroid of impacted boreholes, background boreholes bucketed to 8 directions
    lateral_status = {}
    if background and any(bh in coords for bh in impacted):
        xs = [coords[bh][0] for bh in impacted if bh in coords]
        ys = [coords[bh][1] for bh in impacted if bh in coords]
        cx, cy = sum(xs)/len(xs), sum(ys)/len(ys)
        import math as _math
        by_direction = {}
        for bh in background:
            if bh not in coords:
                continue
            e, n = coords[bh]
            angle = _math.degrees(_math.atan2(e - cx, n - cy)) % 360
            direction = _bearing_to_compass8(angle)
            by_direction.setdefault(direction, []).append(bh)
        for direction, bhs in by_direction.items():
            best_bh, best_cl, best_depth = None, None, None
            for bh in bhs:
                for depth, cl in profile.get(bh, []):
                    if worst_depth is None or abs(depth - worst_depth) <= DEPTH_TOL:
                        if best_cl is None or cl > best_cl:
                            best_bh, best_cl, best_depth = bh, cl, depth
            if best_cl is None:
                continue
            lateral_status[direction] = {
                "status": "achieved" if best_cl < 100.0 else "not_achieved",
                "borehole": best_bh, "cl_mg_l": best_cl, "depth_m": best_depth,
            }
        for d in _COMPASS_8:
            lateral_status.setdefault(d, {"status": "no_coverage", "borehole": None, "cl_mg_l": None, "depth_m": None})

    background_elevated = any(v["status"] == "not_achieved" for v in lateral_status.values())

    return {
        "samples_collected": True,
        "all_below_100": all_below_100,
        "max_cl_mg_l": worst_cl, "max_cl_borehole": worst_bh, "max_cl_depth_m": worst_depth,
        "vertical_status": vertical_status,
        "vertical_overrides": overrides,
        "vertical_unresolved": unresolved,
        "lateral_status": lateral_status,
        "background_elevated": background_elevated,
    }



# ── Section 5 intro (Background Chloride) — pure Python ─────────────────────
# Converted from the retired prompts/s5_intro.md: borehole lists and chloride
# figures are lookups on the Excel workbook; the wording is fixed. Section 5
# only exists when Background samples exceed 100 mg/L (see
# remove_section5_if_no_bg_chloride), so only the "exceedances exist" wording
# is written here. Excluded Background boreholes are always called out in
# their own sentence with a reason placeholder for the practitioner.

def _natural_key(sample_id):
    import re
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(sample_id))]


def _section5_data(wb):
    """Read the background / excluded-background facts for Section 5's intro
    (also written to excel_data.json for Sections 5.1-5.3)."""
    def _rows(name):
        if name not in wb.sheetnames:
            return []
        rows = list(wb[name].iter_rows(values_only=True))
        if not rows:
            return []
        hdr = list(rows[0])
        return [dict(zip(hdr, r)) for r in rows[1:]]

    def _num(v):
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    ecsar = _rows("EC & SAR Rating Categories")
    apec_key = lambda r: r.get("APEC") if "APEC" in r else r.get("Comments")
    bg_ids = sorted({r["Sample ID"] for r in ecsar if apec_key(r) == "Background" and r.get("Sample ID")}, key=_natural_key)
    ex_ids = sorted({r["Sample ID"] for r in ecsar if apec_key(r) == "Excluded Background" and r.get("Sample ID")}, key=_natural_key)

    seen, exc = set(), []
    for r in _rows("Tier 1 Exceedances"):
        if r.get("APEC") == "Background" and r.get("Chemical Group") == "Chloride":
            k = (r.get("Sample ID"), r.get("Depth (m)"))
            if k not in seen:
                seen.add(k)
                exc.append(r)
    exc_ids = sorted({r["Sample ID"] for r in exc}, key=_natural_key)
    top = sorted([r for r in exc if _num(r.get("Chloride (mg/kg)")) is not None],
                 key=lambda r: r["Chloride (mg/kg)"], reverse=True)[:2]

    excluded = []
    for bid in ex_ids:
        rows = [r for r in ecsar if r.get("Sample ID") == bid and apec_key(r) == "Excluded Background" and _num(r.get("Z")) is not None]
        hi = [(r["Z"], r["Chloride (mg/L)"]) for r in rows if _num(r.get("Chloride (mg/L)")) is not None and r["Chloride (mg/L)"] > 100]
        deepest = max(rows, key=lambda r: r["Z"]) if rows else None
        excluded.append({
            "sample_id": bid,
            "over_100_mg_l": hi,
            "max_depth_m": deepest["Z"] if deepest else None,
            "max_depth_chloride_mg_l": deepest.get("Chloride (mg/L)") if deepest else None,
        })
    return {"background_boreholes": bg_ids, "exceedance_boreholes": exc_ids,
            "top_values": [{"sample_id": r["Sample ID"], "depth_m": r.get("Depth (m)"), "chloride_mg_kg": r["Chloride (mg/kg)"]} for r in top],
            "excluded_background": excluded}


def generate_section5_intro(doc, wb):
    """Fill <INSERT_5_INTRO_START>/<INSERT_5_INTRO_END>. Returns the data dict."""
    from apply_operations import op_replace_between
    d = _section5_data(wb)
    if not d["exceedance_boreholes"]:
        print("  ✓ generate_section5_intro: no Background chloride exceedances — Section 5 will be removed")
        return d
    g = lambda v: f"{int(v):,}" if float(v).is_integer() else f"{v:,g}"
    tops = d["top_values"]
    parts = [f"{t['chloride_mg_kg']:.0f} mg/kg at {t['sample_id']} ({float(t['depth_m']):.1f} m)" for t in tops]
    if len(parts) >= 2:
        clause = f"two maximum values of {parts[0]} and {parts[1]}"
    elif parts:
        clause = f"a maximum value of {parts[0]}"
    else:
        clause = "elevated values"
    blocks = [
        {"style": "body", "text": "As noted in Section 4.2.1, boreholes were advanced in undisturbed areas, away from former facility locations and known contaminant sources, to characterize background soil chemistry and native soil profiles."},
        {"style": "body", "text": (f"Boreholes {_join_with_and(d['background_boreholes'])} were advanced near the lease boundaries, with no evidence of soil disturbance noted in the borehole logs. "
                                   f"However, chloride concentrations exceeding the Tier 1 delineation guideline of 100 mg/L were identified at {_join_with_and(d['exceedance_boreholes'])}, with {clause}.")},
        {"style": "body", "text": ("As naturally occurring chloride associated with saline lakes and seeps are well documented in the region (Last & Ginn, 2005; Kwiatkowski et al., 1996; Vance et al., 1993), "
                                   "a review of the historical activities and site-specific soil and groundwater information was completed to evaluate the elevated chloride in the outlying background locations.")},
    ]
    ex = d["excluded_background"]
    if ex:
        ids = [e["sample_id"] for e in ex]
        one = len(ids) == 1
        text = (f"{_join_with_and(ids)} {'was' if one else 'were'} also advanced as {'a background location' if one else 'background locations'} but "
                f"{'was' if one else 'were'} excluded from the background evaluation [REASON FOR EXCLUSION — PRACTITIONER TO CONFIRM].")
        for e in ex:
            who = e["sample_id"]
            if e["over_100_mg_l"]:
                hi = _join_with_and([f"{g(c)} mg/L at {g(z)} mbgs" for z, c in e["over_100_mg_l"]])
                tail = f" Chloride at {who} exceeded the 100 mg/L delineation guideline ({hi})"
                if e["max_depth_chloride_mg_l"] is not None and e["max_depth_chloride_mg_l"] > 100:
                    tail += f", and vertical delineation was not achieved at the maximum investigation depth of {g(e['max_depth_m'])} mbgs."
                else:
                    tail += f", and chloride was below 100 mg/L at the maximum investigation depth of {g(e['max_depth_m'])} mbgs."
            else:
                tail = f" Chloride at {who} was below the 100 mg/L delineation guideline at all depths."
            text += tail
        blocks.append({"style": "body", "text": text})
    ok = op_replace_between(doc, {"start_placeholder": "<INSERT_5_INTRO_START>", "end_placeholder": "<INSERT_5_INTRO_END>", "blocks": blocks})
    print(f"  {'✓' if ok else '✗'} generate_section5_intro ({len(d['background_boreholes'])} background BH, {len(ex)} excluded)")
    return d

# ── Section 1 (Introduction) and 1.1 (Objectives and Scope) — pure Python ───
# Converted from the retired prompts/s1_introduction.md and
# prompts/s1_1_objectives_scope.md: every fact is a lookup (client, site name,
# site type, surface location, fieldwork date) and the objective sentence is
# one of two fixed variants chosen by the report_type run setting.

OBJECTIVE_STANDARD = (
    "The objectives of the assessment were to characterize soil quality at the "
    "identified areas of potential environmental concern (APECs), delineate the "
    "extent of impacts for the relevant contaminants of potential concern (CoPCs), "
    "and evaluate the site for closure."
)
OBJECTIVE_PRESENCE_ABSENCE = (
    "The objective of the assessment was to investigate each area of potential "
    "environmental concern (APEC) for the presence or absence of the contaminants "
    "of potential concern (CoPCs)."
)


def _client_info(references_folder, client_name):
    """Return (short_name or None, is_owa) for client_name by scanning
    prompts/clients/*.md (same Aliases lookup as the cover page). OWA is
    detected from the client file's Short Name or the client name itself."""
    short = None
    needle = (client_name or "").strip().lower()
    clients_dir = os.path.join(references_folder, "..", "prompts", "clients")
    if needle and os.path.isdir(clients_dir):
        def _sec(text, heading):
            out, on = [], False
            for line in text.splitlines():
                t = line.strip()
                if t.lower() == f"## {heading}".lower():
                    on = True
                    continue
                if on:
                    if t.startswith("#"):
                        break
                    if t:
                        out.append(t)
            return out
        for fname in sorted(os.listdir(clients_dir)):
            if not fname.endswith(".md"):
                continue
            with open(os.path.join(clients_dir, fname), encoding="utf-8") as f:
                txt = f.read()
            aliases = [a.lower() for a in _sec(txt, "Aliases")]
            if any(needle in a or a in needle for a in aliases):
                sn = _sec(txt, "Short Name")
                short = sn[0] if sn else None
                break
    is_owa = (short == "OWA") or ("orphan well" in needle)
    return short, is_owa


def _titlecase_company(name):
    """'SANLING ENERGY LTD.' -> 'Sanling Energy Ltd.'; mixed-case names are kept."""
    if not name or name != name.upper():
        return name
    fix = {"LTD.": "Ltd.", "LTD": "Ltd", "INC.": "Inc.", "INC": "Inc", "CORP.": "Corp.",
           "CORPORATION": "Corporation", "CO.": "Co.", "LIMITED": "Limited",
           "LP": "LP", "ULC": "ULC", "LLC": "LLC"}
    return " ".join(fix.get(w) or w.capitalize() for w in name.split())


def _latest_fieldwork_date(log_sets):
    """End date of the most recent drilling event, as a single 'Month D, YYYY'."""
    import re
    from datetime import date
    months = {m: i for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"], 1)}
    ends = []
    for ls in (log_sets or []):
        raw = ls.get("drill_date_header")
        p = _parse_drill_date_header(raw)
        if p:
            ends.append(p[1])
            continue
        # Tolerant fallback: header text that isn't one clean date (e.g. extra
        # notes such as "August 03, 2026 (pages also dated August 04 and
        # August 05, 2026)"). Take the latest "Month D" mentioned, with the
        # year found in the same text.
        txt = str(raw or "")
        yr = re.findall(r"\b(20\d{2}|19\d{2})\b", txt)
        if not yr:
            continue
        for mon, day in re.findall(r"([A-Za-z]+)\s+(\d{1,2})\b", txt):
            if mon.lower() in months:
                try:
                    ends.append(date(int(yr[-1]), months[mon.lower()], int(day)))
                except ValueError:
                    pass
    if not ends:
        return "XX"
    return max(ends).strftime("%B %-d, %Y")


def build_section1_opening_sentence(site_facts, site_lsd, client_name, references_folder):
    """The one opening sentence shared (word for word) by Section 1 and the
    Executive Summary's Section 1 paragraph. Written to excel_data.json as
    `section1_opening_sentence` so the exec summary reuses it verbatim."""
    sf = site_facts or {}
    ab = sf.get("abadata") or {}
    site_name = ab.get("site_name") or "XX"
    site_type = sf.get("site_type") or "XX"
    loc = (site_lsd or ab.get("surface_location") or "XX").strip()
    if loc != "XX" and not loc.upper().endswith("M"):
        loc += "M"
    short, is_owa = _client_info(references_folder, client_name)
    tail = (f"to complete a Phase 2 Environmental Site Assessment (ESA) at the "
            f"{site_name} {site_type} at surface location {loc} (the site).")
    if is_owa:
        client = _titlecase_company(ab.get("licensee")) or "XX"
        return f"The Orphan Well Association (OWA) retained EBM Geoscience Inc. (EBM) on behalf of {client} {tail}"
    if not short:
        print(f"  ⚠ Section 1: no Short Name found for client {client_name!r} in prompts/clients/ — add one; using the bare name")
        return f"{client_name or 'XX'} retained EBM Geoscience Inc. (EBM) {tail}"
    return f"{client_name} ({short}) retained EBM Geoscience Inc. (EBM) {tail}"


def generate_section1(doc, site_facts, site_lsd, client_name, references_folder):
    """Fill <INSERT_1_START>/<INSERT_1_END>. Returns the opening sentence."""
    from apply_operations import op_replace_between
    opening = build_section1_opening_sentence(site_facts, site_lsd, client_name, references_folder)
    date = _latest_fieldwork_date(((site_facts or {}).get("borehole_logs") or {}).get("log_sets"))
    ok = op_replace_between(doc, {
        "start_placeholder": "<INSERT_1_START>",
        "end_placeholder": "<INSERT_1_END>",
        "blocks": [{"style": "body", "text": f"{opening} Fieldwork was completed on {date}."}],
    })
    print(f"  {'✓' if ok else '✗'} generate_section1 (fieldwork date: {date})")
    return opening


def generate_section1_1(doc, report_type="standard"):
    """Fill <INSERT_1_1_START>/<INSERT_1_1_END>: objective sentence (by report
    type) + the fixed scope-of-work list."""
    from apply_operations import op_replace_between
    rt = (report_type or "standard").strip().lower().replace("-", "_").replace("/", "_")
    objective = OBJECTIVE_PRESENCE_ABSENCE if rt in ("presence_absence", "presence", "p2") else OBJECTIVE_STANDARD
    blocks = [
        {"style": "body", "text": objective},
        {"style": "body", "text": "The scope of work included the following:"},
        {"style": "bullet", "text": "Review the historical investigation data."},
        {"style": "bullet", "text": "Evaluate background conditions."},
        {"style": "bullet", "text": "Evaluate each APEC for the associated CoPCs."},
        {"style": "bullet", "text": "Develop a conceptual site model (CSM)."},
        {"style": "bullet", "text": "Prepare a summary report to current regulatory standards."},
    ]
    ok = op_replace_between(doc, {
        "start_placeholder": "<INSERT_1_1_START>",
        "end_placeholder": "<INSERT_1_1_END>",
        "blocks": blocks,
    })
    print(f"  {'✓' if ok else '✗'} generate_section1_1 (report type: {rt})")
    return ok


def main(onedrive_folder, excel_file_path, output_folder=None, site_lsd=None, client_name=None, site_facts_path=None, figures_zip_path=None, report_type="standard"):
    """
    Generate the EBM report.

    Args:
        onedrive_folder: Path to folder with template, CSVs, and prompt library
        excel_file_path: Path to Excel analytical file
        output_folder: Optional path to save the output report (defaults to onedrive_folder)
    """
    if output_folder is None:
        output_folder = onedrive_folder

    print("=" * 70)
    print("EBM REPORT GENERATOR")
    print("=" * 70)

    # ── Construct paths
    template_docx = os.path.join(onedrive_folder, "Automation Template_20260924.docx")

    # site_facts.json is loaded here (early) rather than right before Section
    # 2.1 uses it, because the DWDA per-APEC payload (built further down,
    # before Section 2.1 runs) also needs it (abadata.wellbore_depth, for
    # the AER 2014 required-sample-count).
    site_facts = {}
    if site_facts_path and os.path.exists(site_facts_path):
        import json as _json2
        with open(site_facts_path) as _sf:
            site_facts = _json2.load(_sf)

    # ── Verify files exist
    for fpath, fname in [(template_docx, "Template"), (excel_file_path, "Excel file")]:
        if not os.path.exists(fpath):
            print(f"✗ {fname} not found: {fpath}")
            return False

    print(f"\n✓ All files found")
    print(f"  Template: {os.path.basename(template_docx)}")
    print(f"  Excel: {os.path.basename(excel_file_path)}")

    # ── Read Excel
    wb = openpyxl.load_workbook(excel_file_path)

    # Canonical column name mapping — handles both title-case and lowercase/underscore variants
    _col_map = {
        # EC & SAR sheet
        "comments":                      "Comments",
        "sample_id":                     "Sample ID",
        "ec_category":                   "EC Category",
        "sar_category":                  "SAR Category",
        "soluble_ions_chloride_mg_kg":   "Chloride (mg/kg)",
        "soluble_ions_chloride_mg_l":    "Chloride (mg/L)",
        # Tier 1 Exceedances sheet
        "parameter":                     "Parameter",
        "depth_(m)":                     "Depth (m)",
        "depth_m":                       "Depth (m)",
        # Map APEC column to Comments for area grouping
        "apec":                          "Comments",
    }

    def _normalise_headers(raw_headers):
        """Return canonical header names, falling back to the original if unknown."""
        result = []
        for h in raw_headers:
            key = str(h).strip().lower().replace(" ", "_") if h is not None else None
            result.append(_col_map.get(key, h))
        return result

    ws_ecsar = wb["EC & SAR Rating Categories"]
    ecsar_headers = _normalise_headers([c.value for c in next(ws_ecsar.iter_rows(min_row=1, max_row=1))])
    ecsar_data = [dict(zip(ecsar_headers, row)) for row in ws_ecsar.iter_rows(min_row=2, values_only=True)]

    # Always use Tier 1 Exceedances sheet
    exc_sheet_name = "Tier 1 Exceedances"
    ws_exc = wb[exc_sheet_name]
    exc_headers = _normalise_headers([c.value for c in next(ws_exc.iter_rows(min_row=1, max_row=1))])
    exc_data = [dict(zip(exc_headers, row)) for row in ws_exc.iter_rows(min_row=2, values_only=True)]

    print(f"  EC/SAR samples: {len(ecsar_data)}")
    print(f"  Exceedances: {len(exc_data)}")

    # ── Site Summary sheet → site_summary payload for Claude (Section 2.8
    # exposure-pathway table selection: Land Use picks Agricultural vs.
    # Natural Area, COPCs drives which CoPCs stay in the surviving table's
    # rows). Read fresh every run, same as every other sheet on this file —
    # this is analytical Excel data, not a site_facts.json field.
    site_summary_payload = None
    if "Site Summary" in wb.sheetnames:
        ws_summary = wb["Site Summary"]
        summary_headers = [c.value for c in next(ws_summary.iter_rows(min_row=1, max_row=1))]
        summary_row = next(ws_summary.iter_rows(min_row=2, max_row=2, values_only=True), None)
        if summary_row:
            summary_dict = dict(zip(summary_headers, summary_row))
            copcs_raw = summary_dict.get("COPCs")
            site_summary_payload = {
                "land_use":  summary_dict.get("Land Use"),
                "texture":   summary_dict.get("Texture"),
                "strata":    summary_dict.get("Strata"),
                "copcs_raw": copcs_raw,
                "copcs":     [c.strip() for c in str(copcs_raw or "").split(",") if c.strip()],
            }
            print(f"  Site Summary: Land Use = {site_summary_payload['land_use']!r}, COPCs = {site_summary_payload['copcs']}")
        else:
            print("  ⚠ 'Site Summary' sheet found but has no data row (row 2 is empty)")
    else:
        print("  ⚠ 'Site Summary' sheet not found in Excel file — Section 2.8 exposure table cannot be auto-selected")

    # ── Build per-APEC data payload for Claude to generate the Section 4.2
    # narrative (see prompts/s4_2_2_apecs.md). Background is excluded here —
    # it's handled separately and deterministically by
    # generate_section4_2_1_background() above.
    print(f"\n✓ Extracting per-APEC data for Claude narrative generation...")

    cat_order = {"Good": 0, "Fair": 1, "Poor": 2, "Very Poor": 3, "Unsuitable": 4}
    CHLORIDE_GUIDELINE_MG_L = 100.0

    # `Tier 1 Exceedances`'s own `APEC` column (normalised to "Comments",
    # same as `EC & SAR Rating Categories`'s) is the same underlying data
    # column as the EC & SAR sheet's — verified directly against a real
    # export: every row where both sheets have a value for the same Sample
    # ID agrees, 0 mismatches. It shows "-" only for boreholes genuinely
    # marked "Unassigned" in the `Borehole Rationale` sheet (no area yet),
    # not because the column is unreliable — those "-" rows are correctly
    # excluded below, same as they'd be excluded from any per-area section.
    # DWDA (Drilling Waste Disposal Area) gets its own dedicated marker
    # (<INSERT_42_DWDA_START>/_END) and needs extra fields (AER 2014
    # required-sample-count from wellbore depth) the generic per-APEC
    # section doesn't — see prompts/s4_2_dwda.md. In real workbooks the
    # DWDA characterization and delineation samples are themselves tagged
    # with two DIFFERENT APEC values in the data sheets ("DWDA-Char" /
    # "DWDA-Delineation", not a plain "DWDA") — confirmed against an actual
    # site workbook (output_20260929_113545.xlsx). So detection/grouping is
    # by prefix, case-insensitive ("dwda*"), not an exact "DWDA" match —
    # any such value is folded into one merged "DWDA" bucket here, so the
    # DWDA_DATA_FOR_CLAUDE payload's EC/SAR categories, chloride ranges,
    # and exceedances span both groups' samples together (the borehole-ID
    # split between the two groups is still read separately, from
    # `Borehole Rationale`'s own "DWDA-Char.../DWDA-Delin..." rows, by
    # _dwda_char_delin_boreholes() below).
    def _normalize_dwda_area(area):
        return "DWDA" if str(area).strip().lower().startswith("dwda") else area

    area_ecsar = defaultdict(list)
    for row in ecsar_data:
        area = row.get("Comments")
        if area:
            area_ecsar[_normalize_dwda_area(area)].append(row)

    area_exc = defaultdict(list)
    for row in exc_data:
        area = row.get("Comments")
        if area and area != "-":
            area_exc[_normalize_dwda_area(area)].append(row)

    areas_ordered = [
        a for a in OrderedDict.fromkeys(_normalize_dwda_area(row.get("Comments")) for row in ecsar_data if row.get("Comments"))
        if a not in ("Background", "DWDA")
    ]

    # Background chloride max (mg/kg), reused from the same rows
    # _background_ecsar_rows() already uses for Section 4.2.1/3.2, so the
    # "...or background chloride concentration of XX mg/kg" clause always
    # agrees with what Section 4.2.1 reports as background.
    bg_rows_for_guideline = _background_ecsar_rows(ecsar_data)
    bg_cl_kg_vals = [r.get("Chloride (mg/kg)") for r in bg_rows_for_guideline if isinstance(r.get("Chloride (mg/kg)"), (int, float))]
    background_chloride_mg_kg_max = max(bg_cl_kg_vals) if bg_cl_kg_vals else None

    panel_by_apec = _borehole_rationale_by_apec(wb)

    import json as _json

    apec_payload = [
        _build_apec_payload_entry(area, area_ecsar[area], area_exc.get(area, []), panel_by_apec, cat_order, CHLORIDE_GUIDELINE_MG_L, background_chloride_mg_kg_max)
        for area in areas_ordered
    ]

    print("\n" + "=" * 70)
    print("EC_SAR_DATA_FOR_CLAUDE")
    print("=" * 70)
    print(_json.dumps(apec_payload, indent=2))
    print("=" * 70)


    # ── DWDA payload (Section 4.2's DWDA subsection, prompts/s4_2_dwda.md) ──
    # DWDA's Borehole Rationale rows are split into "DWDA-Char"/"DWDA-Delin"
    # (characterization vs. delineation boreholes) rather than one plain
    # "DWDA" row like every other APEC, so _build_apec_payload_entry()'s own
    # panel_by_apec.get("DWDA") lookup below finds nothing — the real panel
    # and borehole-group lists are filled in separately afterward from
    # _dwda_char_delin_boreholes().
    # wellbore_depth_m/required_sample_count are computed unconditionally
    # (not just when a DWDA sump was actually found) because the AER
    # (2014) requirement sentence is shared verbatim by BOTH
    # prompts/s4_2_dwda.md (sump found) and prompts/s4_2_dwda_nil.md (no
    # sump found, exploratory boreholes only) — see DWDA_REQUIREMENT_DATA_FOR_CLAUDE
    # below, printed regardless of which of the two applies.
    wellbore_depth_m = _parse_wellbore_depth_m((site_facts or {}).get("abadata", {}).get("wellbore_depth"))
    required_sample_count = _dwda_required_sample_count(wellbore_depth_m)

    dwda_payload = None
    if "DWDA" in area_ecsar:
        dwda_payload = _build_apec_payload_entry("DWDA", area_ecsar["DWDA"], area_exc.get("DWDA", []), panel_by_apec, cat_order, CHLORIDE_GUIDELINE_MG_L, background_chloride_mg_kg_max)
        dwda_payload["wellbore_depth_m"] = wellbore_depth_m
        dwda_payload["required_sample_count"] = required_sample_count

        dwda_bh = _dwda_char_delin_boreholes(panel_by_apec)
        dwda_payload["parameter_panel"] = _panel_labels_from_flags(dwda_bh["panel"])
        dwda_payload["characterization_boreholes"] = dwda_bh["characterization_boreholes"]
        dwda_payload["delineation_boreholes"] = dwda_bh["delineation_boreholes"]

        # Waste-mix-zone impact depth range for the characterization
        # borehole(s) — see prompts/s4_2_dwda.md step 8. Only handles a
        # single characterization borehole cleanly (the common case); if
        # there's more than one, report each one's own range rather than
        # guessing how to combine them.
        impact_ranges = []
        for bh_id in dwda_bh["characterization_boreholes"]:
            top, bottom = _dwda_impact_depth_range(wb, bh_id)
            impact_ranges.append({"borehole_id": bh_id, "top_of_impact_m": top, "bottom_of_impact_m": bottom})
        dwda_payload["characterization_impact_depth_ranges"] = impact_ranges

    print("\n" + "=" * 70)
    print("DWDA_DATA_FOR_CLAUDE")
    print("=" * 70)
    print(_json.dumps(dwda_payload, indent=2))
    print("=" * 70)


    # ── DWDA requirement payload (shared by prompts/s4_2_dwda.md and
    # prompts/s4_2_dwda_nil.md's requirement sentence — see comment above) ──
    dwda_requirement_payload = {
        "wellbore_depth_m": wellbore_depth_m,
        "required_sample_count": required_sample_count,
    }
    print("\n" + "=" * 70)
    print("DWDA_REQUIREMENT_DATA_FOR_CLAUDE")
    print("=" * 70)
    print(_json.dumps(dwda_requirement_payload, indent=2))
    print("=" * 70)


    print("\n" + "=" * 70)
    print("SITE_SUMMARY_DATA_FOR_CLAUDE")
    print("=" * 70)
    print(_json.dumps(site_summary_payload, indent=2))
    print("=" * 70)

    # ── Single consolidated Excel-derived data file for Claude (mirrors
    # site_facts.json's "one file per source" pattern: site_facts.json holds
    # everything extracted from the PDFs/ABAData; excel_data.json holds
    # everything computed from this Excel workbook). Claude-authored
    # sections read this one file rather than scraping printed stdout/log
    # text or juggling several small files.
    chloride_delineation_payload = compute_chloride_delineation_data(wb, site_facts)
    print("\n" + "=" * 70)
    print("CHLORIDE_DELINEATION_DATA_FOR_CLAUDE")
    print("=" * 70)
    print(_json.dumps(chloride_delineation_payload, indent=2))
    print("=" * 70)

    excel_data_path = os.path.join(output_folder, "excel_data.json")
    with open(excel_data_path, "w") as _f:
        _json.dump({
            "ec_sar_data": apec_payload,
            "dwda_data": dwda_payload,
            "dwda_requirement_data": dwda_requirement_payload,
            "site_summary_data": site_summary_payload,
            "chloride_delineation_data": chloride_delineation_payload,
            "section1_opening_sentence": build_section1_opening_sentence(site_facts, site_lsd, client_name, onedrive_folder),
            "section5_data": _section5_data(wb),
        }, _f, indent=2)
    print(f"\n✓ Wrote consolidated Excel data for Claude: {excel_data_path}")


    # ── Load and edit template using python-docx
    print(f"\n✓ Loading template...")
    doc = Document(template_docx)

    # ── Apply edits using python-docx
    print(f"\n✓ Applying edits...")

    # ── Generate cover page
    # site_lsd and client_name are not derivable from the Excel file alone —
    # they come from the ABAData Word doc (Surface Location, Licensee),
    # which are extracted once into site_facts.json by the unified extraction pass
    # (see prompts/site_facts_cache.md). Pass
    # them in explicitly per run rather than hardcoding one site's values here;
    # generate_cover_page() falls back to placeholder text if neither is given.
    print(f"\n✓ Generating cover page...")
    generate_cover_page(doc, onedrive_folder, site_lsd=site_lsd, client_name=client_name)
    _ab = (site_facts or {}).get("abadata", {}) if isinstance(site_facts, dict) else {}
    generate_page_headers(doc, _ab.get("licensee", ""), site_lsd or _ab.get("legal_land_description", ""))

    # ── Sections 1 and 1.1 (pure Python)
    print(f"\n✓ Filling Sections 1 and 1.1...")
    generate_section1(doc, site_facts, site_lsd, client_name, onedrive_folder)
    generate_section1_1(doc, report_type)

    # ── Fill Section 2.1 (pure Python — see the deleted prompts/s2_1_facility.md;
    # site type + every field here is a raw fact already in site_facts.json,
    # no wording judgment involved)
    print(f"\n✓ Filling Section 2.1 Facility Information...")
    if site_facts:
        generate_section2_1(doc, site_facts, site_lsd=site_lsd)
    else:
        print("  ✗ No site_facts.json path given/found — Section 2.1 left as template placeholders")

    # ── Fill Section 2.3 (pure Python — see generate_section2_3()'s docstring;
    # converted from the retired prompts/s2_3_1_site_char.md, which had
    # drifted from the live template's real 7-row table shape)
    print(f"\n✓ Filling Section 2.3 Site Characteristics and Contaminant Sources...")
    if site_facts:
        generate_section2_3(doc, site_facts, apec_payload, dwda_payload)
    else:
        print("  ✗ No site_facts.json path given/found — Section 2.3 left as template placeholders")

    # ── Fill Section 2.4 (pure Python — see generate_section2_4()'s docstring;
    # converted from the retired prompts/s2_3_2_regional.md)
    print(f"\n✓ Filling Section 2.4 Regional Information...")
    if site_facts:
        generate_section2_4(doc, site_facts)
    else:
        print("  ✗ No site_facts.json path given/found — Section 2.4 left as template placeholders")

    # ── Fill Section 2.5 (pure Python — see generate_section2_5()'s docstring;
    # converted from the retired prompts/s2_5_receptor_distances.md)
    print(f"\n✓ Filling Section 2.5 Receptor Distances...")
    if site_facts:
        generate_section2_5(doc, site_facts)
    else:
        print("  ✗ No site_facts.json path given/found — Section 2.5 left as template placeholders")

    # ── Fill Section 2.6 (pure Python — see the deleted prompts/s2_6_soil_char.md;
    # both fields are already-authored outputs of the Step 1c extraction pass,
    # no wording judgment involved)
    print(f"\n✓ Filling Section 2.6 Soil Characteristics...")
    generate_section2_6(doc, site_facts)

    # ── Fill Section 2.7 (pure Python — see the deleted prompts/s2_7_groundwater_char.md;
    # formatting lookup only, no wording judgment involved)
    print(f"\n✓ Filling Section 2.7 Groundwater Characteristics...")
    generate_section2_7(doc, site_facts)

    # ── Fill Section 2.8 (pure Python — see the deleted prompts/s2_8_exposure.md;
    # table selection is a Land Use string match and the CoPC filter is a
    # set-membership check, no wording judgment involved)
    print(f"\n✓ Filling Section 2.8 Exposure Pathway Evaluation...")
    generate_section2_8(doc, site_summary_payload)

    # <INSERT_42_APECS_START>/_END is left in place here — Claude authors
    # the Section 4.2 (non-background APEC) narrative from the
    # EC_SAR_DATA_FOR_CLAUDE JSON printed below, per prompts/s4_2_2_apecs.md,
    # and applies it as a replace_between operation in a later step.

    # ── Fill Section 3.2 SCARG intro + guideline table (pure Python — see
    # prompts/s3_2_scarg.md; fixed-sentence if/else plus direct Excel-to-table
    # transcription, no wording judgment involved)
    print(f"\n✓ Filling Section 3.2 SCARG guidelines...")
    generate_section3_2_scarg(doc, wb, ecsar_data)

    # ── Fill Section 4.2.1 Background subsection (pure Python — mechanical
    # Excel-driven branching + wording rules; the "FOR T1 with BG" pH bullet
    # and the borehole-exclusion sentence are left as template placeholder
    # text on purpose, per user decision)
    print(f"\n✓ Filling Section 4.2.1 Background subsection...")
    generate_section4_2_1_background(doc, ecsar_data)

    # ── Fill Section 4 intro (pure Python — mechanical read/computation off
    # site_facts.json's borehole_logs block, no narrative judgment)
    print(f"\n✓ Filling Section 4 intro...")
    generate_section4_intro(doc, site_facts)

    # ── Fill Section 4.1 Borehole Rationale table (pure Python — direct
    # Excel-to-table transcription, no wording judgment)
    print(f"\n✓ Filling Section 4.1 Borehole Rationale table...")
    generate_section4_1_borehole_rationale(doc, wb)

    # ── Fill Section 7.1 APEC Review table (pure Python — direct
    # Excel-to-table transcription plus one derived Yes/No column; real
    # APECs only, Background/Unassigned excluded, DWDA-Char/Delineation
    # merged into one DWDA row — per user decision 2026-09-29)
    print(f"\n✓ Filling Section 7.1 APEC Review table...")
    generate_section7_1_apec_review(doc, wb)

    # -- Section 3.3 Tier 1 with Background (pure Python, from the Excel `Guidelines` sheet)
    print(f"\n\u2713 Filling Section 3.3 Tier 1 with Background...")
    generate_section3_3_tier1_background(doc, wb)

    # -- Section 7.2 justification block (pure Python: keep the "not
    # required" sentence if Tier 1 Exceedances' last column has no
    # justifications, else keep the list/table block -- per user 2026-09-30)
    print(f"\n\u2713 Resolving Section 7.2 justification block...")
    generate_section7_2_justification(doc, wb)

    # -- Section 7.2 residual exceedance table (pure Python, from Tier 1
    # Exceedances: non-justified, named-APEC rows only -- per user 2026-09-30)
    print(f"\n\u2713 Filling Section 7.2 residual exceedance table...")
    generate_section7_2_residual_table(doc, wb)

    # ── Generate Appendix E tables
    print(f"\n✓ Generating Appendix E depth interval tables...")
    generate_appendix_e(doc, wb)

    # ── Figures zip is an explicit, per-run argument (CLI arg 7 / the
    # figures_zip_path parameter) — never auto-picked. The figures zip is
    # NOT reliably the Excel file's own timestamp with "_figures.zip"
    # swapped in (seen in practice: excel at 113545, figures zip at
    # 152815, same run), and per standing decision this is never guessed
    # or silently chosen by mtime — always ask the user which
    # "*_figures.zip" to use for the session before invoking this script
    # (see SKILL.md Step 2). If omitted, Sections 5.3 and 4.3's figure
    # insertion are skipped entirely (non-fatal) rather than guessing.
    if figures_zip_path is None:
        print(f"  ℹ No figures_zip_path supplied — skipping Section 5.3/4.3 figure insertion")
    elif not os.path.exists(figures_zip_path):
        print(f"  ✗ figures_zip_path does not exist: {figures_zip_path} — skipping figure insertion")
        figures_zip_path = None
    else:
        print(f"  ℹ Using figures zip: {os.path.basename(figures_zip_path)}")

    # ── Insert Section 5.3 chemistry footprint figures
    if figures_zip_path:
        print(f"\n✓ Inserting Section 5.3 chemistry footprint figures...")
        # figure_start=2, not the default 1: Section 4.3's "Figure 1: Soil
        # Chloride Profile" caption is static template text and always
        # claims Figure 1, so the BG_CHLORIDE figures here must start
        # numbering at 2 to avoid a duplicate "Figure 1" in the document.
        generate_section5_3_figures(doc, figures_zip_path, figure_start=2)

        # ── Insert Section 4.3's chloride delineation profile figure(s) at
        # <INSERT_43_NA_PROFILE> (see prompts/s4_3_chloride.md)
        print(f"\n✓ Inserting Section 4.3 chloride delineation profile figure(s)...")
        generate_section4_3_na_profile(doc, figures_zip_path)
    else:
        print(f"\n  ℹ Skipping Section 5.3/4.3 figure insertion (no figures_zip_path)")

    # ── Fill Section 5.4 background borehole sentence (pure Python — see
    # prompts/s5_4_conclusion.md; fixed template wording, only the borehole
    # list is site-specific)
    print(f"\n✓ Filling Section 5.4 background borehole sentence...")
    _s5 = generate_section5_intro(doc, wb)
    generate_section5_4_background(doc, ecsar_data)

    # ── Save output
    print(f"\n✓ Saving document...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_docx = os.path.join(output_folder, f"EBM_Report_{timestamp}.docx")
    remove_section5_if_no_bg_chloride(doc, wb)
    doc.save(output_docx)

    print(f"\n" + "=" * 70)
    print(f"✓ SUCCESS")
    print(f"=" * 70)
    print(f"\nReport created: {output_docx}")
    print(f"File size: {os.path.getsize(output_docx)} bytes")

    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python generate_ebm_report.py <references_folder> <excel_file> [output_folder] [site_lsd] [client_name] [site_facts_json] [figures_zip_file] [report_type: standard|presence_absence]")
        print("  site_lsd and client_name are read from the ABAData Word doc (Surface")
        print("  Location, Licensee) — pass them in per run rather than relying")
        print("  on a hardcoded default; omitted values fall back to placeholder text")
        print("  on the cover page.")
        print("  site_facts_json is this site's site_facts.json (see")
        print("  prompts/site_facts_cache.md) — Section 2.1 is filled from it; omit it")
        print("  and Section 2.1 is left as template placeholders.")
        print("  figures_zip_file is the *_figures.zip to use this session — always ask")
        print("  the user which one, even if only one candidate exists in the folder;")
        print("  never auto-picked by filename/mtime. Omit it to skip figure insertion.")
        sys.exit(1)

    onedrive_folder = sys.argv[1]
    excel_file = sys.argv[2]
    output_folder = sys.argv[3] if len(sys.argv) > 3 else None
    site_lsd = sys.argv[4] if len(sys.argv) > 4 else None
    client_name = sys.argv[5] if len(sys.argv) > 5 else None
    site_facts_path = sys.argv[6] if len(sys.argv) > 6 else None
    figures_zip_path = sys.argv[7] if len(sys.argv) > 7 else None
    report_type = sys.argv[8] if len(sys.argv) > 8 else "standard"

    success = main(onedrive_folder, excel_file, output_folder, site_lsd=site_lsd, client_name=client_name, site_facts_path=site_facts_path, figures_zip_path=figures_zip_path, report_type=report_type)
    sys.exit(0 if success else 1)
