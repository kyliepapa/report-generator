from flask import Flask, render_template, request, send_from_directory, url_for, Response, jsonify, stream_with_context
import os
import time
import threading

job_lock = threading.Lock()

from newreport import (
    fetch_photos, fetch_tags, build_unit_bathroom_map, organize_photos,
    build_pdf_context, get_sort_key, set_inputs, configure_sorting,
    configure_bathrooms, analyze_missing_photos, determine_html_method,
)
from pdf_generator import generate_pdf_report

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
REPORTS_DIR = os.path.join(STATIC_DIR, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)


def sse_response(generator_func):
    """Wrap a generator in a properly-headered SSE Response."""
    resp = Response(stream_with_context(generator_func()), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'       # disables Nginx buffering
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/generate_stream')
def generate_stream():
    if not job_lock.acquire(blocking=False):
        def _busy():
            yield "data: ⏳ Another report is currently being generated. Please wait.\n\n"
        return sse_response(_busy)

    project_id   = request.args.get('project_id')
    project_name = request.args.get('project_name', '').strip() or project_id
    multi_bath   = request.args.get('multi_bath')
    label_format = request.args.get('label_format')
    bath_names   = request.args.get('bath_names', '').split(',')

    def generate():
        try:
            yield "data: 🔌 Connected...\n\n"

            last_heartbeat = [time.time()]  # use list so inner func can mutate it

            def heartbeat():
                now = time.time()
                if now - last_heartbeat[0] > 2:
                    last_heartbeat[0] = now
                    return "data: ⏳ still working...\n\n"
                return None

            yield "data: ⚙️ Configuring inputs...\n\n"
            set_inputs(project_id, multi_bath, label_format, bath_names, project_name)
            configure_sorting()
            configure_bathrooms()

            yield "data: 📥 Fetching photos...\n\n"
            photos = fetch_photos()
            yield f"data: ✅ {len(photos)} photos fetched\n\n"

            yield "data: 🏷 Tagging photos...\n\n"
            total = len(photos)
            last_update = [time.time()]

            for i, photo in enumerate(photos):
                try:
                    photo["tag_names"] = fetch_tags(photo["id"])
                except Exception:
                    photo["tag_names"] = []
                    yield f"data: ⚠️ Failed to fetch tags for photo {photo['id']}\n\n"

                now = time.time()
                if now - last_update[0] > 2:
                    yield f"data: 🏷 Tagging: {i+1}/{total} photos\n\n"
                    last_update[0] = now
                    last_heartbeat[0] = now  # reset heartbeat whenever we send a progress update
                else:
                    # Always send a keepalive — this is what prevents the 60s timeout
                    yield f"data: ⏳ {i+1}/{total}\n\n"

                time.sleep(0.05)

            yield f"data: 🏷 Tagging complete ({total}/{total})\n\n"

            yield "data: 📦 Building unit map...\n\n"
            unit_bath_map = build_unit_bathroom_map(photos)

            yield "data: 🔄 Sorting photos...\n\n"
            photos.sort(key=lambda p: get_sort_key(p, unit_bath_map))

            yield "data: 🧩 Structuring data...\n\n"
            structured = organize_photos(photos, unit_bath_map)

            yield "data: 🔍 Analyzing missing photos...\n\n"
            missing = analyze_missing_photos(structured)

            missing_before = missing.get("BEFORE", [])
            missing_after  = missing.get("AFTER", [])
            yield f"data: 📊 Missing BEFORE: {len(missing_before)}\n\n"
            yield f"data: 📊 Missing AFTER: {len(missing_after)}\n\n"

            for loc in missing_before:
                yield f"data: 🔴 {loc}\n\n"
            for loc in missing_after:
                yield f"data: 🟡 {loc}\n\n"

            yield "data: 🏗 Generating HTML report...\n\n"
            from newreport import SORT_METHOD_KEY as SMK
            html_func = determine_html_method(SMK)
            html_func(structured)

            yield "data: ✅ HTML report ready!\n\n"
            yield "event: complete\ndata: success\n\n"

        except Exception as e:
            import traceback
            yield f"data: ❌ ERROR: {str(e)}\n\n"
            yield f"data: {traceback.format_exc()}\n\n"
            yield "event: error\ndata: failed\n\n"

        finally:
            job_lock.release()

    return sse_response(generate)


@app.route('/report')
def open_report():
    return send_from_directory(STATIC_DIR, 'report.html')


@app.route('/reports/<filename>')
def download_report(filename):
    return send_from_directory(REPORTS_DIR, filename)


@app.route("/generate_pdf_stream")
def generate_pdf_stream():
    if not job_lock.acquire(blocking=False):
        def _busy():
            yield "data: ⏳ Another report is currently being generated. Please wait.\n\n"
        return sse_response(_busy)

    project_id   = request.args.get("project_id")
    project_name = request.args.get("project_name", "").strip() or project_id
    multi        = request.args.get("multi_bath")
    label_format = request.args.get("label_format")
    baths        = request.args.get("bath_names", "").split(",")

    def generate():
        try:
            yield "data: 📄 Starting PDF generation...\n\n"

            set_inputs(project_id, multi, label_format, baths, project_name)
            configure_sorting()
            configure_bathrooms()

            yield "data: 📥 Fetching photos...\n\n"
            photos = fetch_photos()
            total = len(photos)
            yield f"data: ✅ {total} photos fetched\n\n"

            yield "data: 🏷 Fetching tags...\n\n"
            for i, photo in enumerate(photos):
                try:
                    photo["tag_names"] = fetch_tags(photo["id"])
                except Exception:
                    photo["tag_names"] = []
                if i % 5 == 0 and i > 0:
                    yield f"data: 🏷 Progress: {i}/{total}\n\n"

            yield f"data: 🏷 Tagging complete ({total}/{total})\n\n"

            yield "data: 🧩 Organizing photos...\n\n"
            unit_bath_map = build_unit_bathroom_map(photos)
            photos.sort(key=lambda p: get_sort_key(p, unit_bath_map))
            structured = organize_photos(photos, unit_bath_map)

            yield "data: 🏗 Building PDF...\n\n"
            context = build_pdf_context(structured, photos)
            context["structured"] = structured
            filename = generate_pdf_report(context)

            yield "data: ✅ PDF ready!\n\n"
            yield f"event: pdfready\ndata: {filename}\n\n"
            yield "event: complete\ndata: success\n\n"

        except Exception as e:
            import traceback
            yield f"data: ❌ ERROR: {str(e)}\n\n"
            yield f"data: {traceback.format_exc()}\n\n"
            yield "event: error\ndata: failed\n\n"

        finally:
            job_lock.release()

    return sse_response(generate)


if __name__ == '__main__':
    app.run(debug=True)