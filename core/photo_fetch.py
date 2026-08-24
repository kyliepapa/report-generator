"""
Photo fetching from the CompanyCam API.

Relocated from newreport.py with ONE behavior change, called out
explicitly: fetch_photos() used to call the bare exit() function on a
non-200 API response. In the original CLI-only script that just ended
the process; inside a Flask worker thread it silently kills the whole
web server, not just the current job. Replaced with raising a
RuntimeError, which the job runner in web/routes/ already wraps in
try/except and logs to the job's terminal output -- so a bad API
response now surfaces as a failed job instead of taking the server
down. Everything else is unchanged.
"""

import time
import requests
import core.config as config

def fetch_photos(project_id):
    all_photos = []
    page = 1
    url_base = f"https://api.companycam.com/v2/projects/{project_id}/photos"
    headers = {"Authorization": f"Bearer {config.ACCESS_TOKEN}"}
    per_page = 100

    while True:
        url = f"{url_base}?page={page}&per_page={per_page}"
        r = requests.get(url, headers=headers, timeout=15)

        if r.status_code != 200:
            print("[ERROR] API Error:", r.text)
            raise RuntimeError(f"CompanyCam API error fetching photos: {r.status_code} {r.text}")

        data = r.json()
        photos = data if isinstance(data, list) else data.get("photos", [])

        if not photos:
            break

        all_photos.extend(photos)
        print(f"[*] Fetched {len(photos)} photos on page {page}, total: {len(all_photos)}")

        if len(photos) < per_page:
            break

        page += 1

    return all_photos


def fetch_tags(photo_id, retries=3):
    url = f"https://api.companycam.com/v2/photos/{photo_id}/tags"
    headers = {"Authorization": f"Bearer {config.ACCESS_TOKEN}"}

    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=15)

            if r.status_code == 200:
                return [t["display_value"] for t in r.json()]
            else:
                print(f"[WARN] Bad response for {photo_id}: {r.status_code}")

        except Exception as e:
            print(f"[ERROR] Attempt {attempt+1} failed for {photo_id}: {e}")

        time.sleep(1)

    print(f"[FAIL] Could not fetch tags for {photo_id}")
    return []