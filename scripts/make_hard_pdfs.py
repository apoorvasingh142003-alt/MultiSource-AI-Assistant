"""Generate a small corpus of genuinely HARD PDFs for the Phase 1 (Docling) eval.

These are deliberately messy in the ways real client documents are, and they exercise the
robust-ingestion path + the parse-confidence signal:

  • HARD_fees_table.pdf   — a real fees/penalties TABLE (reportlab Table with a spanned
                            header) whose key fact ("early termination penalty 27%") lives
                            ONLY in a cell. Tests table-aware chunking + a cited answer.
  • HARD_multicolumn.pdf  — a two-column clause layout (the kind pypdf jumbles). A distinct
                            fact ("cure period of forty-two (42) days") sits in the flow.
  • HARD_scan.pdf         — an IMAGE-ONLY page (text rasterised to a picture, no text
                            layer). The basic parser gets no text → low/zero confidence →
                            graceful labelled degradation; Docling+OCR can still read it.

Kept OUT of the seeded demo corpus (written to data/eval_pdfs/) so demo counts and routes
don't drift. Regenerable any time.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Frame, PageTemplate, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle, BaseDocTemplate)

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "eval_pdfs"

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]
_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
FONT = "HBody"
FONT_BOLD = "HBodyBold"


def _register_fonts() -> None:
    regular = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), None)
    bold = next((p for p in _BOLD_CANDIDATES if os.path.exists(p)), None)
    if regular:
        pdfmetrics.registerFont(TTFont(FONT, regular))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, bold or regular))
    else:
        globals()["FONT"] = "Helvetica"
        globals()["FONT_BOLD"] = "Helvetica-Bold"


def _styles():
    ss = getSampleStyleSheet()
    return dict(
        title=ParagraphStyle("HT", parent=ss["Title"], fontName=FONT_BOLD, fontSize=17),
        heading=ParagraphStyle("HH", parent=ss["Heading2"], fontName=FONT_BOLD,
                               fontSize=12, spaceBefore=10),
        body=ParagraphStyle("HB", parent=ss["BodyText"], fontName=FONT, fontSize=10.5,
                            leading=15),
    )


# --------------------------------------------------------------------------- #
# 1) A fees/penalties TABLE — the key fact lives only in a cell.               #
# --------------------------------------------------------------------------- #
def make_fees_table() -> None:
    st = _styles()
    doc = SimpleDocTemplate(str(OUT_DIR / "HARD_fees_table.pdf"), pagesize=LETTER,
                            leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                            title="Zenith Logistics — Fee Schedule")
    flow = [
        Paragraph("Zenith Logistics — Master Fee Schedule (ZEN-MSA-2026)", st["title"]),
        Spacer(1, 12),
        Paragraph("The following fees and penalties apply under the Agreement. All amounts "
                  "are exclusive of tax.", st["body"]),
        Spacer(1, 10),
    ]
    data = [
        ["Fee Schedule — Penalties and Charges", "", ""],
        ["Item", "Trigger", "Amount"],
        ["Late payment fee", "Invoice unpaid after 30 days", "2.5% per month"],
        ["Service suspension", "Invoice unpaid after 45 days", "Suspension + reconnection fee"],
        ["Reconnection fee", "Restoration after suspension", "$1,250 flat"],
        ["Early termination penalty", "Termination for convenience", "27% of remaining value"],
        ["Data export fee", "Post-termination data handover", "$4,800 one-time"],
    ]
    tbl = Table(data, colWidths=[2.4 * inch, 2.6 * inch, 1.8 * inch])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTNAME", (0, 0), (-1, 1), FONT_BOLD),
        ("SPAN", (0, 0), (2, 0)),                         # merged header cell
        ("BACKGROUND", (0, 0), (2, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (2, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#e5e7eb")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
    ]))
    flow += [tbl, Spacer(1, 10),
             Paragraph("Penalties are in addition to any unpaid fees and accrued interest.",
                       st["body"])]
    doc.build(flow)


# --------------------------------------------------------------------------- #
# 2) Two-column clause layout — a distinct fact in the flowing text.           #
# --------------------------------------------------------------------------- #
def make_multicolumn() -> None:
    st = _styles()
    path = str(OUT_DIR / "HARD_multicolumn.pdf")
    doc = BaseDocTemplate(path, pagesize=LETTER,
                          leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                          topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                          title="Meridian Terms — Two Column")
    gap = 0.3 * inch
    col_w = (doc.width - gap) / 2.0
    left = Frame(doc.leftMargin, doc.bottomMargin, col_w, doc.height, id="l")
    right = Frame(doc.leftMargin + col_w + gap, doc.bottomMargin, col_w, doc.height, id="r")
    doc.addPageTemplates([PageTemplate(id="two", frames=[left, right])])

    body = st["body"]
    paras = [
        Paragraph("Meridian Data Services — General Terms (MER-GT-2026)", st["title"]),
        Spacer(1, 10),
        Paragraph("1. Term. This Agreement commences on the Effective Date and continues "
                  "for a period of thirty-six (36) months.", body),
        Paragraph("2. Breach and Cure. A party in material breach shall have a cure period "
                  "of forty-two (42) days from written notice before the other party may "
                  "terminate. This cure period is deliberately longer than the market "
                  "standard.", body),
        Paragraph("3. Service Credits. If monthly uptime falls below 99.9%, the Customer is "
                  "entitled to a service credit of five percent (5%) of the monthly fee for "
                  "each full percentage point below target.", body),
        Paragraph("4. Data Residency. All Customer data shall be stored within the European "
                  "Economic Area unless the Customer expressly authorises otherwise in "
                  "writing.", body),
        Paragraph("5. Audit. The Customer may audit the Provider's security controls once "
                  "per calendar year on thirty (30) days notice.", body),
        Paragraph("6. Governing Law. This Agreement is governed by the laws of the Republic "
                  "of Ireland.", body),
    ]
    doc.build(paras)


# --------------------------------------------------------------------------- #
# 3) Image-only "scan" — text rasterised to a picture; NO text layer.          #
# --------------------------------------------------------------------------- #
def make_scan() -> None:
    from reportlab.pdfgen import canvas as _canvas
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        print("Pillow not available — skipping HARD_scan.pdf")
        return

    # Render text onto a white raster image (like a scanned page).
    W, H = 1275, 1650  # ~150 DPI Letter
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(_FONT_CANDIDATES[0], 34)
        fb = ImageFont.truetype(_BOLD_CANDIDATES[0], 40)
    except Exception:
        font = ImageFont.load_default()
        fb = font
    lines = [
        ("SCANNED CONTRACT — Polaris Freight (POL-SC-2026)", fb, 90),
        ("", font, 160),
        ("5. Service Suspension.", fb, 210),
        ("The Provider may suspend services if an undisputed", font, 260),
        ("invoice remains unpaid for more than sixty (60) days", font, 300),
        ("after the due date, subject to five (5) business days", font, 340),
        ("written notice to the Customer.", font, 380),
        ("", font, 430),
        ("6. Early Termination.", fb, 470),
        ("An early termination penalty of thirty-three percent (33%)", font, 520),
        ("of the remaining contract value applies on termination", font, 560),
        ("for convenience.", font, 600),
    ]
    for text, f, y in lines:
        if text:
            d.text((90, y), text, fill="black", font=f)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    from reportlab.lib.utils import ImageReader
    c = _canvas.Canvas(str(OUT_DIR / "HARD_scan.pdf"), pagesize=LETTER)
    pw, ph = LETTER
    c.drawImage(ImageReader(buf), 0, 0, width=pw, height=ph)
    c.showPage()
    c.save()


def main() -> None:
    _register_fonts()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_fees_table()
    make_multicolumn()
    make_scan()
    print(f"Wrote {len(list(OUT_DIR.glob('*.pdf')))} hard PDF(s) to {OUT_DIR}")


if __name__ == "__main__":
    main()
