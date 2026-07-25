#!/usr/bin/env python3
"""
gui.py — APK Cleaner Web Engine v3.0
Flask Backend với Server-Sent Events (SSE) để truyền log và tiến trình realtime.
Chạy: python3 gui.py
Mở tại: http://127.0.0.1:5847
"""

import sys, os, json, threading, time, shutil, subprocess, logging
import queue as queue_mod
from pathlib import Path
from datetime import datetime

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    from flask import Flask, request, jsonify, Response, send_from_directory
except ImportError:
    print("📦  Đang cài Flask...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "-q"])
    from flask import Flask, request, jsonify, Response, send_from_directory

import config
from decompiler import check_prerequisites, check_java, check_jar, decompile_apk
from cleaner import clean_source_code
from recompiler import recompile_apk, sign_apk

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024  # 512 MB

event_queue: queue_mod.Queue = queue_mod.Queue()
pipeline_running = False
UPLOAD_DIR = config.WORKSPACE_DIR / "uploads"


class SSELogHandler(logging.Handler):
    LEVEL_MAP = {"DEBUG":"debug","INFO":"info","WARNING":"warning","ERROR":"error","CRITICAL":"error"}
    def emit(self, record):
        lvl = self.LEVEL_MAP.get(record.levelname, "info")
        event_queue.put({"type": "log", "level": lvl, "message": record.getMessage()})


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/check")
def api_check():
    java_ok = check_java()
    java_ver = ""
    if java_ok:
        try:
            r = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=5)
            first_line = (r.stderr or r.stdout).strip().splitlines()[0]
            java_ver = first_line
        except Exception:
            java_ver = "detected"

    return jsonify({
        "java":    {"ok": java_ok, "version": java_ver},
        "apktool": {"ok": config.APKTOOL_JAR.exists(), "path": str(config.APKTOOL_JAR)},
        "signer":  {"ok": config.SIGNER_JAR.exists(),  "path": str(config.SIGNER_JAR)},
    })


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "Không tìm thấy file"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "File không có tên"}), 400

    config.init_directories()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    save_path = UPLOAD_DIR / file.filename
    file.save(str(save_path))
    size = save_path.stat().st_size

    return jsonify({"path": str(save_path), "name": file.filename, "size": size})


@app.route("/api/set-path", methods=["POST"])
def api_set_path():
    data = request.json or {}
    path = Path(data.get("path", ""))
    if not path.exists():
        return jsonify({"error": f"Không tìm thấy: {path}"}), 404
    if not path.suffix.lower() == ".apk":
        return jsonify({"error": "File không phải .apk"}), 400

    size = path.stat().st_size
    return jsonify({"path": str(path), "name": path.name, "size": size})


@app.route("/api/start", methods=["POST"])
def api_start():
    global pipeline_running
    if pipeline_running:
        return jsonify({"error": "Đang xử lý, vui lòng chờ"}), 409

    data = request.json or {}
    apk_path = data.get("apkPath", "")
    options  = data.get("options", {})

    if not apk_path or not Path(apk_path).exists():
        return jsonify({"error": "File APK không hợp lệ"}), 400

    pipeline_running = True

    while not event_queue.empty():
        try:
            event_queue.get_nowait()
        except queue_mod.Empty:
            break

    thread = threading.Thread(target=_run_pipeline, args=(apk_path, options), daemon=True)
    thread.start()

    return jsonify({"ok": True})


@app.route("/api/events")
def api_events():
    def generate():
        while True:
            try:
                evt = event_queue.get(timeout=30)
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                if evt.get("type") in ("done", "fatal"):
                    break
            except queue_mod.Empty:
                yield f"data: {json.dumps({'type':'ping'})}\n\n"

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@app.route("/api/open-folder", methods=["POST"])
def api_open_folder():
    out = (request.json or {}).get("dir", str(config.OUTPUT_DIR))
    Path(out).mkdir(parents=True, exist_ok=True)
    subprocess.run(["open", out])
    return jsonify({"ok": True})


@app.route("/api/config")
def api_config():
    return jsonify({
        "outputDir": str(config.OUTPUT_DIR),
        "toolsDir":  str(config.TOOLS_DIR),
    })


def emit(etype, **data):
    event_queue.put({"type": etype, **data})


def _run_pipeline(apk_path: str, options: dict):
    global pipeline_running

    logger = logging.getLogger("apk_cleaner")
    sse_handler = SSELogHandler()
    sse_handler.setLevel(logging.DEBUG)
    logger.addHandler(sse_handler)

    try:
        config.init_directories()
        apk     = Path(apk_path)
        out_dir = Path(options.get("outputDir") or str(config.OUTPUT_DIR))
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp     = config.TEMP_DIR
        rb      = config.REBUILT_APK

        # Step 0: Prerequisites
        emit("step", index=0, state="running", label="Kiểm tra công cụ")
        emit("log", level="info", message="Đang kiểm tra Java, APKTool, Signer...")
        time.sleep(0.3)

        if not check_prerequisites():
            emit("step", index=0, state="error")
            emit("fatal", message="Thiếu các công cụ trong thư mục tools/ hoặc thiếu Java!")
            return

        emit("log", level="success", message="✓ Tất cả công cụ sẵn sàng")
        emit("step", index=0, state="done")

        # Step 1: Decompile
        emit("step", index=1, state="running", label="Giải nén APK")
        emit("log", level="info", message=f"Đang giải nén {apk.name} ({apk.stat().st_size/1024/1024:.1f} MB)...")

        try:
            ok = decompile_apk(apk, tmp)
        except FileNotFoundError as e:
            emit("step", index=1, state="error")
            emit("fatal", message=str(e))
            return
        if not ok:
            emit("step", index=1, state="error")
            emit("fatal", message="Giải nén APK thất bại! File có thể bị protected.")
            return

        smali_count = len(list(tmp.rglob("*.smali")))
        xml_count   = len(list(tmp.rglob("*.xml")))
        emit("log", level="success", message=f"✓ Giải nén xong: {smali_count} Smali, {xml_count} XML")
        emit("step", index=1, state="done")

        # Step 2: Clean
        emit("step", index=2, state="running", label="Xoá quảng cáo")
        emit("log", level="info", message="Đang quét và xoá quảng cáo + chặn Play Store...")

        report = clean_source_code(tmp, dry_run=False)

        emit("log", level="success",
             message=(f"✓ Đã block {report['ads_methods_blocked']} ads methods, "
                      f"{report['store_redirects_blocked']} redirects, "
                      f"{report['xml_entries_removed']} XML entries"))
        emit("step", index=2, state="done")

        # Step 3: Recompile + Sign
        emit("step", index=3, state="running", label="Đóng gói & Ký số")
        emit("log", level="info", message="Đang đóng gói lại APK...")

        if not recompile_apk(tmp, rb):
            emit("step", index=3, state="error")
            emit("fatal", message="Đóng gói thất bại! Kiểm tra log chi tiết.")
            return

        emit("log", level="info", message="Đang ký số APK...")

        ks_path = options.get("keystore")
        signed  = sign_apk(
            rb, out_dir,
            keystore=Path(ks_path) if ks_path else None,
        )
        if not signed:
            emit("step", index=3, state="error")
            emit("fatal", message="Ký số thất bại!")
            return

        emit("log", level="success", message=f"✓ APK đã ký: {Path(signed).name}")
        emit("step", index=3, state="done")

        # Cleanup
        try:
            shutil.rmtree(tmp, ignore_errors=True)
            rb.unlink(missing_ok=True)
        except Exception:
            pass

        emit("done",
             report=report,
             outputFile=str(signed),
             outputDir=str(out_dir),
             fileName=Path(signed).name)

    except Exception as e:
        emit("log", level="error", message=f"Lỗi: {e}")
        emit("fatal", message=f"Lỗi không mong đợi: {e}")
    finally:
        pipeline_running = False
        logger.removeHandler(sse_handler)


if __name__ == "__main__":
    config.init_directories()
    port = 5847
    
    log_setup = logging.getLogger("apk_cleaner")
    if not log_setup.handlers:
        from logger import setup_logger
        setup_logger(config.LOG_DIR, verbose=True)

    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
