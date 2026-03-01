import os, uuid, threading, time, subprocess, shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template

app = Flask(__name__)

BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
FONT_DIR   = BASE_DIR / "fonts"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
jobs = {}

def cleanup():
    while True:
        cutoff = time.time() - 3600
        for folder in (UPLOAD_DIR, OUTPUT_DIR):
            for f in folder.iterdir():
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
        stale = [k for k, v in jobs.items() if v.get("ts", 0) < cutoff]
        for k in stale: jobs.pop(k, None)
        time.sleep(300)

threading.Thread(target=cleanup, daemon=True).start()


def find_thai_font():
    """หาฟอนต์ภาษาไทยที่มีอยู่ในระบบ"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # 1. ลองใช้ฟอนต์ที่ดาวน์โหลดไว้ใน fonts/
    candidates_dir = [
        (FONT_DIR / "Sarabun-Regular.ttf", FONT_DIR / "Sarabun-Bold.ttf", FONT_DIR / "Sarabun-Italic.ttf"),
    ]
    # 2. ลองหาใน system fonts
    system_candidates = [
        ("/usr/share/fonts/truetype/tlwg/Sarabun.ttf",
         "/usr/share/fonts/truetype/tlwg/Sarabun-Bold.ttf",
         "/usr/share/fonts/truetype/tlwg/Sarabun-Oblique.ttf"),
        ("/usr/share/fonts/truetype/tlwg/Garuda.ttf",
         "/usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf",
         "/usr/share/fonts/truetype/tlwg/Garuda-Oblique.ttf"),
        ("/usr/share/fonts/truetype/tlwg/Norasi.ttf",
         "/usr/share/fonts/truetype/tlwg/Norasi-Bold.ttf",
         "/usr/share/fonts/truetype/tlwg/Norasi-Oblique.ttf"),
    ]

    all_candidates = [(Path(r), Path(b), Path(i)) for r, b, i in system_candidates]
    all_candidates = list(candidates_dir) + all_candidates

    for regular, bold, italic in all_candidates:
        if regular.exists():
            try:
                pdfmetrics.registerFont(TTFont("ThaiFont", str(regular)))
                b_path = bold if bold.exists() else regular
                i_path = italic if italic.exists() else regular
                pdfmetrics.registerFont(TTFont("ThaiFont-Bold",   str(b_path)))
                pdfmetrics.registerFont(TTFont("ThaiFont-Italic", str(i_path)))
                from reportlab.pdfbase.pdfmetrics import registerFontFamily
                registerFontFamily("ThaiFont",
                    normal="ThaiFont", bold="ThaiFont-Bold",
                    italic="ThaiFont-Italic", boldItalic="ThaiFont-Bold")
                print(f"[font] Using: {regular}")
                return "ThaiFont", "ThaiFont-Bold"
            except Exception as e:
                print(f"[font] Failed {regular}: {e}")
                continue

    print("[font] No Thai font found, using Helvetica (Thai may not render)")
    return "Helvetica", "Helvetica-Bold"


def build_pdf(docx_path, pdf_path, title, page_size="A4"):
    from docx import Document
    from reportlab.lib.pagesizes import A4, A5
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak, HRFlowable
    )
    from reportlab.platypus.tableofcontents import TableOfContents

    psize  = A4 if page_size == "A4" else A5
    pw, ph = psize

    if page_size == "A4":
        mg = 25*mm; bs = 11; h1s = 22; h2s = 16; h3s = 13
    else:
        mg = 18*mm; bs = 10; h1s = 18; h2s = 14; h3s = 12

    tf, tb = find_thai_font()

    ink  = colors.HexColor("#1c1408")
    gold = colors.HexColor("#c49a2e")
    gd   = colors.HexColor("#7a5c0f")
    sage = colors.HexColor("#5a7355")
    muted= colors.HexColor("#888888")
    rule = colors.HexColor("#e8d5a0")

    def S(name, **k): return ParagraphStyle(name, **k)

    sty = {
        "cover":     S("cover", fontName=tb, fontSize=h1s+6, textColor=ink,
                        alignment=TA_CENTER, spaceAfter=6*mm, leading=(h1s+6)*1.4),
        "cover_sub": S("csub",  fontName=tf, fontSize=bs,    textColor=muted,
                        alignment=TA_CENTER, spaceAfter=4*mm),
        "toc_title": S("toctit",fontName=tb, fontSize=h1s,   textColor=ink,
                        spaceAfter=5*mm, leading=h1s*1.4),
        "h1": S("H1", fontName=tb, fontSize=h1s, textColor=ink,
                 spaceBefore=10*mm, spaceAfter=3*mm, leading=h1s*1.4, keepWithNext=1),
        "h2": S("H2", fontName=tb, fontSize=h2s, textColor=gd,
                 spaceBefore=7*mm,  spaceAfter=2*mm, leading=h2s*1.4, keepWithNext=1),
        "h3": S("H3", fontName=tb, fontSize=h3s, textColor=sage,
                 spaceBefore=5*mm,  spaceAfter=2*mm, leading=h3s*1.4, keepWithNext=1),
        "body": S("body", fontName=tf, fontSize=bs, textColor=ink,
                   spaceAfter=3*mm, leading=bs*1.75, alignment=TA_JUSTIFY),
        "toc1": S("toc1", fontName=tb, fontSize=bs+1, textColor=ink,
                   leading=(bs+1)*1.6, leftIndent=0, spaceAfter=2*mm),
        "toc2": S("toc2", fontName=tf, fontSize=bs,   textColor=gd,
                   leading=bs*1.5,    leftIndent=6*mm, spaceAfter=1.2*mm),
        "toc3": S("toc3", fontName=tf, fontSize=bs-1, textColor=sage,
                   leading=(bs-1)*1.5, leftIndent=12*mm, spaceAfter=1*mm),
    }

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(rule); canvas.setLineWidth(0.5)
        canvas.line(mg, 15*mm, pw-mg, 15*mm)
        canvas.setFont(tf, 8); canvas.setFillColor(muted)
        if doc.page > 1:
            canvas.drawCentredString(pw/2, 10*mm, str(doc.page - 1))
        if doc.page > 2:
            canvas.setFont(tf, 7); canvas.setFillColor(gold)
            canvas.drawString(mg, ph-12*mm, title)
        canvas.restoreState()

    pdfdoc = SimpleDocTemplate(str(pdf_path), pagesize=psize,
        leftMargin=mg, rightMargin=mg, topMargin=mg, bottomMargin=20*mm,
        title=title, author="Ebook Wizard")

    toc = TableOfContents()
    toc.levelStyles = [sty["toc1"], sty["toc2"], sty["toc3"]]
    toc.dotsMinLevel = 0

    story = []

    # Cover
    story.append(Spacer(1, ph*0.22))
    story.append(HRFlowable(width="80%", thickness=2, color=gold, spaceAfter=8*mm, hAlign="CENTER"))
    story.append(Paragraph(title, sty["cover"]))
    story.append(HRFlowable(width="60%", thickness=1, color=gold, spaceBefore=4*mm, spaceAfter=8*mm, hAlign="CENTER"))
    story.append(PageBreak())

    # TOC
    story.append(Paragraph("สารบัญ", sty["toc_title"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=rule, spaceAfter=4*mm))
    story.append(toc)
    story.append(PageBreak())

    # Parse docx
    doc_word = Document(str(docx_path))

    def safe(t):
        return (t or "").strip() \
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    heading_map = {
        "Heading 1": ("h1", 1), "Heading 2": ("h2", 2), "Heading 3": ("h3", 3),
        "Title": ("h1", 1), "Subtitle": ("h2", 2),
    }

    for para in doc_word.paragraphs:
        text  = safe(para.text)
        sname = para.style.name if para.style else "Normal"

        if not text:
            story.append(Spacer(1, 2*mm))
            continue

        if sname in heading_map:
            key, level = heading_map[sname]
            anchor = f"sec_{uuid.uuid4().hex[:8]}"
            story.append(Paragraph(f'<a name="{anchor}"/>{text}', sty[key]))
            if level == 1:
                story.append(HRFlowable(width="100%", thickness=1, color=rule, spaceAfter=2*mm))
            toc.notify("TOCEntry", (level-1, text, 0, anchor))
        else:
            story.append(Paragraph(text, sty["body"]))

    pdfdoc.multiBuild(story, onFirstPage=lambda c, d: None, onLaterPages=on_page)


def build_epub(docx_path, epub_path, title):
    pandoc = shutil.which("pandoc")
    if not pandoc:
        return False, "ไม่พบ Pandoc"
    r = subprocess.run(
        [pandoc, str(docx_path), "-o", str(epub_path),
         "--metadata", f"title={title}",
         "--toc", "--toc-depth=3", "--epub-chapter-level=2"],
        capture_output=True, text=True, timeout=120)
    return (r.returncode == 0), r.stderr[:300]


def do_convert(job_id, docx_path, title, page_size, make_epub):
    job = jobs[job_id]
    job["status"] = "converting"

    stem      = docx_path.stem
    pdf_path  = OUTPUT_DIR / f"{stem}.pdf"
    epub_path = OUTPUT_DIR / f"{stem}.epub"
    errors, downloads = [], {}

    try:
        build_pdf(docx_path, pdf_path, title, page_size)
        if pdf_path.exists():
            downloads["pdf"] = f"/download/{pdf_path.name}"
    except Exception as e:
        errors.append(f"PDF: {e}")

    if make_epub:
        ok, err = build_epub(docx_path, epub_path, title)
        if ok and epub_path.exists():
            downloads["epub"] = f"/download/{epub_path.name}"
        elif err:
            errors.append(err)

    if downloads:
        job["status"] = "done"; job["downloads"] = downloads; job["warnings"] = errors
    else:
        job["status"] = "error"; job["error"] = " | ".join(errors) or "แปลงไม่สำเร็จ"


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/convert", methods=["POST"])
def convert():
    if "file" not in request.files:
        return jsonify(error="ไม่พบไฟล์"), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".docx"):
        return jsonify(error="รองรับเฉพาะ .docx"), 400
    title     = request.form.get("title","").strip() or f.filename.replace(".docx","")
    page_size = request.form.get("page_size","A4")
    make_epub = request.form.get("epub","false").lower() == "true"
    job_id    = uuid.uuid4().hex
    docx_path = UPLOAD_DIR / f"{job_id}.docx"
    f.save(docx_path)
    jobs[job_id] = {"status":"queued","ts":time.time()}
    threading.Thread(target=do_convert,
        args=(job_id, docx_path, title, page_size, make_epub), daemon=True).start()
    return jsonify(job_id=job_id)

@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job: return jsonify(error="ไม่พบ job"), 404
    return jsonify(job)

@app.route("/download/<filename>")
def download(filename):
    if not (filename.endswith(".pdf") or filename.endswith(".epub")):
        return "forbidden", 403
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
