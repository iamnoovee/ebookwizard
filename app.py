import os, uuid, threading, time, subprocess, shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template

app = Flask(__name__)

BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

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
        for k in stale:
            jobs.pop(k, None)
        time.sleep(300)

threading.Thread(target=cleanup, daemon=True).start()

def do_convert(job_id, docx_path, title):
    job = jobs[job_id]
    job["status"] = "converting"

    stem     = docx_path.stem
    pdf_out  = OUTPUT_DIR / f"{stem}.pdf"
    epub_out = OUTPUT_DIR / f"{stem}.epub"
    errors   = []

    lo     = shutil.which("libreoffice") or shutil.which("soffice")
    pandoc = shutil.which("pandoc")

    # PDF
    if lo:
        r = subprocess.run(
            [lo, "--headless", "--convert-to", "pdf",
             "--outdir", str(OUTPUT_DIR), str(docx_path)],
            capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            errors.append("PDF: " + r.stderr[:200])
    else:
        errors.append("ไม่พบ LibreOffice")

    # EPUB
    if pandoc:
        r = subprocess.run(
            [pandoc, str(docx_path), "-o", str(epub_out),
             "--metadata", f"title={title}",
             "--toc", "--toc-depth=3", "--epub-chapter-level=2"],
            capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            errors.append("EPUB: " + r.stderr[:200])
    else:
        errors.append("ไม่พบ Pandoc")

    downloads = {}
    if pdf_out.exists():
        downloads["pdf"]  = f"/download/{pdf_out.name}"
    if epub_out.exists():
        downloads["epub"] = f"/download/{epub_out.name}"

    if downloads:
        job["status"]    = "done"
        job["downloads"] = downloads
        job["warnings"]  = errors
    else:
        job["status"] = "error"
        job["error"]  = " | ".join(errors) or "แปลงไม่สำเร็จ"

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

    title     = request.form.get("title", "").strip() or f.filename
    job_id    = uuid.uuid4().hex
    docx_path = UPLOAD_DIR / f"{job_id}.docx"
    f.save(docx_path)

    jobs[job_id] = {"status": "queued", "ts": time.time()}
    threading.Thread(target=do_convert, args=(job_id, docx_path, title), daemon=True).start()
    return jsonify(job_id=job_id)

@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify(error="ไม่พบ job"), 404
    return jsonify(job)

@app.route("/download/<filename>")
def download(filename):
    if not (filename.endswith(".pdf") or filename.endswith(".epub")):
        return "forbidden", 403
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
