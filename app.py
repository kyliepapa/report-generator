from flask import Flask, render_template, request, send_from_directory, url_for, Response, jsonify
import os
import time

import threading
job_lock = threading.Lock()

from newreport import (
    fetch_photos,
    fetch_tags,
    build_unit_bathroom_map,
    organize_photos,
    build_pdf_context,
    get_sort_key,
    set_inputs,
    configure_sorting,
    configure_bathrooms,
    analyze_missing_photos,
    determine_html_method,
)

from pdf_generator import generate_pdf_report

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
REPORTS_DIR = os.path.join(STATIC_DIR, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/generate_stream')
def generate_stream():
    if not job_lock.acquire(blocking=False):
        return Response(
            "data: ⏳ Another report is currently being generated. Please wait and try again in a few minutes.\n\n",
            mimetype='text/event-stream'
        )

    project_id   = request.args.get('project_id')
    project_name = request.args.get('project_name', '').strip() or project_id
    multi_bath   = request.args.get('multi_bath')
    label_format = request.args.get('label_format')
    bath_names   = request.args.get('bath_names', '').split(',')

    def generate():
        try:
            yield "data: 🔌 Connected...\n\n"

            last_heartbeat = time.time()

            def heartbeat():
                nonlocal last_heartbeat
                if time.time() - last_heartbeat > 5:
                    last_heartbeat = time.time()
                    return "data: ⏳ still working...\n\n"
                return None

            # --- Setup ---
            yield "data: ⚙️ Configuring inputs...\n\n"
            set_inputs(project_id, multi_bath, label_format, bath_names, project_name)

            yield "data: ⚙️ Setting sorting...\n\n"
            configure_sorting()

            yield "data: ⚙️ Configuring bathrooms...\n\n"
            configure_bathrooms()

            # --- Fetch Photos ---
            yield "data: 📥 Fetching photos...\n\n"
            photos = fetch_photos()
            yield f"data: ✅ {len(photos)} photos fetched\n\n"

            # --- Tagging ---
            yield "data: 🏷 Tagging photos...\n\n"

            total = len(photos)
            last_update = time.time()

            for i, photo in enumerate(photos):
                try:
                    photo["tag_names"] = fetch_tags(photo["id"])
                except Exception as e:
                    photo["tag_names"] = []
                    yield f"data: ⚠️ Failed to fetch tags for photo {photo['id']}\n\n"

                # ⏱ Send update every ~2 seconds
                now = time.time()
                if now - last_update > 2:
                    yield f"data: 🏷 Tagging: {i+1}/{total} photos\n\n"
                    last_update = now

                # ❤️ Keep connection alive
                hb = heartbeat()
                if hb:
                    yield hb

                # 🧘 Prevent API overload (important!)
                time.sleep(0.05)

            yield f"data: 🏷 Tagging complete ({total}/{total})\n\n"

            # --- Organizing ---
            yield "data: 📦 Building unit map...\n\n"
            unit_bath_map = build_unit_bathroom_map(photos)

            yield "data: 🔄 Sorting photos...\n\n"
            photos.sort(key=lambda p: get_sort_key(p, unit_bath_map))

            yield "data: 🧩 Structuring data...\n\n"
            structured = organize_photos(photos, unit_bath_map)

            # --- Missing Analysis ---
            yield "data: 🔍 Analyzing missing photos...\n\n"
            missing = analyze_missing_photos(structured)

            missing_before = missing.get("BEFORE", [])
            missing_after  = missing.get("AFTER", [])

            yield f"data: 📊 Missing BEFORE: {len(missing_before)}\n\n"
            yield f"data: 📊 Missing AFTER: {len(missing_after)}\n\n"

            if missing_before:
                yield "data: 🔴 Units missing BEFORE:\n\n"
                for loc in missing_before:
                    yield f"data:    • {loc}\n\n"

            if missing_after:
                yield "data: 🟡 Units missing AFTER:\n\n"
                for loc in missing_after:
                    yield f"data:    • {loc}\n\n"

            # --- HTML Generation ---
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

    return Response(generate(), mimetype='text/event-stream')


@app.route('/report')
def open_report():
    return send_from_directory(STATIC_DIR, 'report.html')


@app.route('/reports/<filename>')
def download_report(filename):
    return send_from_directory(REPORTS_DIR, filename)


@app.route("/generate_pdf")
def generate_pdf():
    try:
        print("[PDF] Starting PDF generation...")

        project_id   = request.args.get("project_id")
        project_name = request.args.get("project_name", "").strip() or project_id
        multi        = request.args.get("multi_bath")
        label_format = request.args.get("label_format")
        baths        = request.args.get("bath_names", "").split(",")

        set_inputs(project_id, multi, label_format, baths, project_name)
        configure_sorting()
        configure_bathrooms()

        photos = fetch_photos()
        print(f"[PDF] Photos fetched: {len(photos)}")

        for i, photo in enumerate(photos):
            photo["tag_names"] = fetch_tags(photo["id"])
            if i % 10 == 0:
                print(f"[PDF] Tags fetched: {i}/{len(photos)}")

        unit_bath_map = build_unit_bathroom_map(photos)
        photos.sort(key=lambda p: get_sort_key(p, unit_bath_map))
        structured = organize_photos(photos, unit_bath_map)

        context = build_pdf_context(structured, photos)
        context["structured"] = structured

        filename = generate_pdf_report(context)

        print(f"[PDF] Saved: {filename}")
        return jsonify({"status": "success", "filename": filename})

    except Exception as e:
        import traceback
        print("[PDF ERROR]", traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/generate_pdf_stream")
def generate_pdf_stream():
    if not job_lock.acquire(blocking=False):
        return Response(
            "data: ⏳ Another report is currently being generated. Please wait and try again in a few minutes.\n\n",
            mimetype='text/event-stream'
        )

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

            # STEP 1: Fetch photos
            yield "data: 📥 Fetching photos...\n\n"
            photos = fetch_photos()
            total = len(photos)
            yield f"data: ✅ {total} photos fetched\n\n"

            # STEP 2: Fetch tags (SAFE loop)
            yield "data: 🏷 Fetching tags...\n\n"
            for i, photo in enumerate(photos):
                try:
                    photo["tag_names"] = fetch_tags(photo["id"])
                except:
                    photo["tag_names"] = []

                if i % 5 == 0 and i > 0:
                    yield f"data: 🏷 Progress: {i}/{total}\n\n"

            yield f"data: 🏷 Tagging complete ({total}/{total})\n\n"

            # STEP 3: Organize
            yield "data: 🧩 Organizing photos...\n\n"
            unit_bath_map = build_unit_bathroom_map(photos)
            photos.sort(key=lambda p: get_sort_key(p, unit_bath_map))
            structured = organize_photos(photos, unit_bath_map)

            # STEP 4: Generate PDF
            yield "data: 🏗 Building PDF...\n\n"
            context = build_pdf_context(structured, photos)
            context["structured"] = structured

            filename = generate_pdf_report(context)

            yield "data: ✅ PDF ready!\n\n"
            yield f"data: 📁 File: {filename}\n\n"
            yield "event: complete\ndata: success\n\n"

        except Exception as e:
            import traceback
            yield f"data: ❌ ERROR: {str(e)}\n\n"
            yield f"data: {traceback.format_exc()}\n\n"
            yield "event: error\ndata: failed\n\n"

        finally:
            job_lock.release()

    return Response(generate(), mimetype='text/event-stream')



if __name__ == '__main__':
    app.run(debug=True)