"""Make sample circular PDFs for testing and demos of the circulars feature.

    python scripts/make_sample_circulars.py

Writes three PDFs to docs/samples/circulars/: an English text PDF, a Gujarati text PDF and a scanned
(image-only) PDF that needs OCR. Every page is stamped "SAMPLE FOR TESTING: NOT AN OFFICIAL GUJRERA
CIRCULAR". The wording is written for testing and is not taken from real GUJRERA circulars; load the real
circulars the department shares for the POC.
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz  # PyMuPDF: shapes Gujarati text with HarfBuzz

OUT = Path(__file__).resolve().parents[1] / "docs" / "samples" / "circulars"
STAMP = "SAMPLE FOR TESTING: NOT AN OFFICIAL GUJRERA CIRCULAR"
FONT = Path("C:/Windows/Fonts/Nirmala.ttc")

CIRCULARS = {
    "sample_circular_qpr_en.pdf": ("en", """
<p style="text-align:center"><b>Gujarat Real Estate Regulatory Authority (sample)</b></p>
<p>Circular No. SAMPLE/GUJRERA/2025/07</p>
<p>Date: 15/07/2025</p>
<p><b>Subject: Filing of quarterly progress reports by promoters</b></p>
<p>1. Every promoter of an ongoing registered project shall upload the quarterly progress report within
fifteen days after the end of each quarter, as required under Section 11 of the RERA Act, 2016.</p>
<p>2. The report shall state the percentage of construction completed, the number of units booked, the
approvals received and the amount withdrawn from the designated project account.</p>
<p>3. Where the quarterly progress report is not filed within the time allowed, a late fee shall be payable
and the delay shall be shown on the public page of the project.</p>
<p>4. Allottees may view the quarterly progress reports of a project on the public portal.</p>
"""),
    "sample_paripatra_advertisement_gu.pdf": ("gu", """
<p style="text-align:center"><b>ગુજરાત રિયલ એસ્ટેટ નિયમનકારી સત્તામંડળ (નમૂનો)</b></p>
<p>પરિપત્ર ક્રમાંક: SAMPLE/GUJRERA/2025/09</p>
<p>તારીખ: 02/09/2025</p>
<p><b>વિષય: જાહેરાતમાં RERA નોંધણી નંબર અને QR કોડ દર્શાવવા બાબત</b></p>
<p>1. નોંધાયેલા પ્રોજેક્ટની દરેક જાહેરાતમાં પ્રમોટરે પ્રોજેક્ટનો GUJRERA નોંધણી નંબર સ્પષ્ટ રીતે દર્શાવવાનો રહેશે.</p>
<p>2. છાપેલી જાહેરાત, હોર્ડિંગ અને સોશિયલ મીડિયા પરની જાહેરાતમાં પ્રોજેક્ટના પાનાનો QR કોડ પણ દર્શાવવાનો રહેશે.</p>
<p>3. નોંધણી નંબર વગરની અથવા ખોટા નંબરવાળી જાહેરાત RERA કાયદાની કલમ 3 અને 59 હેઠળ કાર્યવાહીને પાત્ર રહેશે.</p>
<p>4. નાગરિકો આવી જાહેરાતની જાણ સત્તામંડળને કરી શકે છે.</p>
"""),
    "sample_circular_extension_scanned.pdf": ("en", """
<p style="text-align:center"><b>Gujarat Real Estate Regulatory Authority (sample)</b></p>
<p>Circular No. SAMPLE/GUJRERA/2025/11</p>
<p>Date: 20/11/2025</p>
<p><b>Subject: Applications for extension of project registration</b></p>
<p>1. A promoter seeking extension of registration under Section 6 shall apply at least three months before
the registration expires.</p>
<p>2. The application shall give the reasons for the delay, the revised completion date and the consent of
the association of allottees where required.</p>
<p>3. Projects whose registration has expired without an extension application shall be listed for action
under Section 7.</p>
"""),
}


def _page(doc: fitz.Document, html: str) -> fitz.Page:
    page = doc.new_page(width=595, height=842)
    css = "* {font-family: sans-serif; font-size: 12pt; line-height: 1.5}"
    if FONT.exists():
        css = "@font-face {font-family: nirmala; src: url(Nirmala.ttc);} * {font-family: nirmala; font-size: 12pt; line-height: 1.5}"
        arch = fitz.Archive(str(FONT.parent))
        page.insert_htmlbox(fitz.Rect(60, 70, 535, 780), html, css=css, archive=arch)
    else:
        page.insert_htmlbox(fitz.Rect(60, 70, 535, 780), html, css=css)
    page.insert_text((60, 40), STAMP, fontsize=9, color=(0.75, 0.1, 0.1))
    page.insert_text((60, 815), STAMP, fontsize=9, color=(0.75, 0.1, 0.1))
    return page


def make(out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for name, (_lang, html) in CIRCULARS.items():
        doc = fitz.open()
        _page(doc, html)
        path = out / name
        if "scanned" in name:  # an image-only PDF, as a scanner makes: needs OCR
            pix = doc[0].get_pixmap(dpi=200, colorspace=fitz.csGRAY)
            scan = fitz.open()
            p = scan.new_page(width=595, height=842)
            p.insert_image(p.rect, stream=pix.tobytes("png"))
            scan.save(path, garbage=4, deflate=True)
            scan.close()
        else:
            doc.subset_fonts()  # embed only the glyphs used, not the whole font
            doc.save(path, garbage=4, deflate=True)
        doc.close()
        made.append(path)
    return made


if __name__ == "__main__":
    for p in make(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT):
        print(p)
