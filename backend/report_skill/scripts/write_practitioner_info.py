"""Write the Practitioner Information hand-off DOCX from a small JSON file.

Usage: python3 write_practitioner_info.py <info.json> <output_folder>
See prompts/practitioner_information.md for the JSON shape.
"""
import json, os, sys
from docx import Document

HEADINGS = [("check", "1. Check / verify"), ("uncertain", "2. Uncertain"),
            ("not_found", "3. Not found / not available"), ("incomplete", "4. Incomplete")]

def main(info_path, out_dir):
    info = json.load(open(info_path, encoding="utf-8"))
    doc = Document()
    doc.add_heading("Practitioner Information", level=1)
    doc.add_paragraph(f"Site: {info.get('site', '')}    Report: {info.get('report', '')}")
    doc.add_paragraph("Hand-off notes for the practitioner. Not part of the report; do not issue with it.")
    for key, title in HEADINGS:
        doc.add_heading(title, level=2)
        items = info.get(key) or []
        if not items:
            doc.add_paragraph("None identified.")
        for it in items:
            doc.add_paragraph(it, style="List Bullet")
    site = "".join(c if c.isalnum() or c in "-_" else "_" for c in info.get("site", "site"))
    out = os.path.join(out_dir, f"Practitioner_Information_{site}.docx")
    doc.save(out)
    print("Saved:", out)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
