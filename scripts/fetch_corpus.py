#!/usr/bin/env python3
"""RadQuery Corpus Downloader

Downloads radiation test report PDFs from public NASA, JPL, and ESA sources.

Source strategies:
  gsfc_test — Selenium (jqGrid pagination). ColdFusion API at parts.cfc?method=getParts
              returns 403 for direct HTTP calls; must load the page in a browser and
              paginate the jqGrid to extract File(s) field per row. PDFs served from
              https://nepp.nasa.gov/radhome/papers/<filename> or as absolute URLs.
  gsfc_pub  — JSON API (GET). ColdFusion endpoint parts.cfc?method=getPubs returns
              paginated JSON; field index 6 is the PDF URL.
  jpl       — JSON API (GET). https://csr-api.jpl.nasa.gov/records returns a JSON
              list; each record has an Attachment field pointing to a ZIP at
              csr-api.jpl.nasa.gov/attachments?key=<path>. ZIPs contain PDF reports.
  escies    — requests + browser User-Agent. The listing page at
              https://escies.org/labreport/radiationList embeds 186 report records
              as a JS variable `reports`. Each record has a webDocumentFile.webDocumentFileId
              field. PDF download URL: https://escies.org/download/webDocumentFile?id=<id>
              Returns HTTP 200 + application/pdf when using a real browser User-Agent.
              Using Python's default UA triggers a 302 SSO redirect — no auth required.
"""

import os
import re
import io
import time
import json
import shutil
import zipfile
import argparse
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin
from tqdm import tqdm

# Resolve paths relative to this script, not cwd
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent / "data" / "raw"
# Full browser UA — required for ESCIES (bot/simple UA triggers 302 SSO redirect)
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
RATE_LIMIT_SECS = 1.5

SOURCES = {
    "gsfc_test": {
        "url": "https://nepp.nasa.gov/radhome/RadDatabase/RadDataBase.html",
        "credibility_tier": 1,
        "report_source": "GSFC",
        "strategy": "selenium",
    },
    "gsfc_pub": {
        "url": "https://nepp.nasa.gov/radhome/RadPubDbase/RadPubDbase.html",
        "credibility_tier": 1,
        "report_source": "GSFC",
        "strategy": "json_api",
    },
    "jpl": {
        "url": "https://www.jpl.nasa.gov/go/space-radiation/radiation-database/",
        "credibility_tier": 1,
        "report_source": "JPL",
        "strategy": "json_api",
    },
    "escies": {
        "url": "https://escies.org/labreport/radiationList",
        "credibility_tier": 2,
        "report_source": "ESCIES",
        "strategy": "js_embedded",
    },
}

# ---------------------------------------------------------------------------
# Directory & manifest helpers
# ---------------------------------------------------------------------------

def setup_directories():
    for source in SOURCES:
        (BASE_DIR / source).mkdir(parents=True, exist_ok=True)


def load_manifest():
    manifest_path = BASE_DIR / "manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_manifest(data):
    manifest_path = BASE_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(data, indent=4))


# ---------------------------------------------------------------------------
# Per-source link fetchers
# ---------------------------------------------------------------------------

def fetch_links_gsfc_pub(url, limit):
    """Fetch PDF URLs from the GSFC Publications database JSON API."""
    api_url = "https://nepp.nasa.gov/radhome/dev/parts.cfc?method=getPubs"
    pdf_urls = []
    page = 1
    rows_per_page = 50

    while len(pdf_urls) < limit:
        time.sleep(RATE_LIMIT_SECS)
        try:
            r = requests.get(
                api_url,
                params={"page": page, "rows": rows_per_page},
                headers={"User-Agent": USER_AGENT},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  [Error] GSFC pub API page {page}: {e}")
            break

        rows = data.get("ROWS", [])
        if not rows:
            break

        for row in rows:
            # Field index 6 (0-based) contains the PDF URL
            if len(row) >= 7 and row[6]:
                url_val = row[6].strip()
                if url_val.lower().endswith(".pdf"):
                    pdf_urls.append(url_val)
                    if len(pdf_urls) >= limit:
                        break

        total_pages = data.get("TOTAL", 1)
        if page >= total_pages:
            break
        page += 1

    # Deduplicate while preserving order
    return list(dict.fromkeys(pdf_urls))[:limit]


def fetch_links_gsfc_test(url, limit):
    """Use Selenium to paginate the jqGrid and extract PDF URLs."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("  [Error] selenium/webdriver-manager not installed. Run: pip install selenium webdriver-manager")
        return []

    print("  Launching headless Chrome for gsfc_test...")
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts,
    )

    pdf_urls = []
    try:
        driver.get(url)
        # Wait for jqGrid to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ui-jqgrid"))
        )
        time.sleep(2)  # let data populate

        # Get total pages from the grid
        total_pages = driver.execute_script(
            "return $('#list').jqGrid('getGridParam', 'lastpage');"
        )
        print(f"  Grid has {total_pages} pages")

        for pg in range(1, total_pages + 1):
            if len(pdf_urls) >= limit:
                break

            # Navigate to page
            driver.execute_script(
                f"$('#list').jqGrid('setGridParam', {{page: {pg}}}).trigger('reloadGrid');"
            )
            time.sleep(RATE_LIMIT_SECS)

            # Extract File(s) from all visible rows
            ids = driver.execute_script("return $('#list').jqGrid('getDataIDs');")
            for row_id in ids:
                row = driver.execute_script(
                    f"return $('#list').jqGrid('getRowData', '{row_id}');"
                )
                file_field = row.get("File(s)", "")
                if not file_field:
                    continue
                parts = re.split(r"<br\s*/?>", file_field, flags=re.IGNORECASE)
                for part in parts:
                    fname = part.strip()
                    if not fname:
                        continue
                    if fname.lower().startswith("http"):
                        if fname.lower().endswith(".pdf"):
                            pdf_urls.append(fname)
                    else:
                        pdf_urls.append(
                            f"https://nepp.nasa.gov/radhome/papers/{fname}"
                        )
                    if len(pdf_urls) >= limit:
                        break
                if len(pdf_urls) >= limit:
                    break
    finally:
        driver.quit()

    return list(dict.fromkeys(pdf_urls))[:limit]


def fetch_links_jpl(url, limit):
    """Fetch attachment ZIP URLs from the JPL CSR API, each containing PDFs."""
    api_url = "https://csr-api.jpl.nasa.gov/records"
    try:
        r = requests.get(api_url, headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
        records = r.json()
    except Exception as e:
        print(f"  [Error] JPL API: {e}")
        return []

    urls = []
    for rec in records:
        attachment = rec.get("Attachment")
        if attachment:
            urls.append({
                "zip_url": f"https://csr-api.jpl.nasa.gov/attachments?key={attachment}",
                "part": rec.get("GenericPartNumber", "unknown"),
                "manufacturer": rec.get("Manufacturer", "unknown"),
            })
        if len(urls) >= limit:
            break

    return urls[:limit]


def fetch_links_escies(url, limit):
    """Extract PDF download items from ESCIES JS-embedded report metadata.

    The listing page embeds `var reports = [...]` containing report objects.
    Each with a webDocumentFile has a webDocumentFileId used to download:
        https://escies.org/download/webDocumentFile?id=<webDocumentFileId>
    A full browser User-Agent is required; bot UAs trigger a 302 SSO redirect.
    """
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  [Error] ESCIES listing fetch: {e}")
        return []

    match = re.search(r"var\s+reports\s*=\s*(\[.*?\]);", r.text, re.DOTALL)
    if not match:
        print("  [Error] Could not locate 'reports' JS variable in ESCIES page")
        return []

    reports = json.loads(match.group(1))
    items = []
    for rpt in reports:
        wdf = rpt.get("webDocumentFile")
        if not wdf:
            continue
        if rpt.get("pdfConfidential"):
            continue
        file_id = wdf.get("webDocumentFileId")
        filename = wdf.get("fileName", f"escies_{file_id}.pdf")
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        items.append({
            "url": f"https://escies.org/download/webDocumentFile?id={file_id}",
            "filename": filename,
            "lab_report_number": rpt.get("labReportNumber", ""),
        })
        if len(items) >= limit:
            break

    print(f"  Found {len(items)} downloadable reports (from {len(reports)} total)")
    return items


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def validate_pdf(filepath):
    """Check that a file starts with %PDF header and is > 10KB."""
    try:
        size = os.path.getsize(filepath)
        if size < 10240:
            return False, f"too small ({size} bytes)"
        with open(filepath, "rb") as f:
            header = f.read(4)
        if header != b"%PDF":
            return False, f"bad header {header!r}"
        return True, "ok"
    except Exception as e:
        return False, str(e)


def download_pdf(url, source_name, manifest):
    """Download a single PDF. Returns (status, file_size)."""
    filename = os.path.basename(url).split("?")[0]
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    filepath = BASE_DIR / source_name / filename

    # Idempotency
    if filepath.exists() and filepath.stat().st_size > 0:
        return "skipped", filepath.stat().st_size

    try:
        time.sleep(RATE_LIMIT_SECS)
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=30)
        r.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=16384):
                f.write(chunk)

        # Validate
        valid, reason = validate_pdf(filepath)
        if not valid:
            filepath.unlink(missing_ok=True)
            return f"failed: {reason}", 0

        file_size = filepath.stat().st_size
        manifest.append({
            "filename": filename,
            "source": source_name,
            "url": url,
            "download_date": datetime.now().isoformat(),
            "file_size_bytes": file_size,
            "credibility_tier": SOURCES[source_name]["credibility_tier"],
            "report_source": SOURCES[source_name]["report_source"],
        })
        return "downloaded", file_size

    except Exception as e:
        filepath.unlink(missing_ok=True)
        return f"failed: {e}", 0


def download_jpl_zip(zip_info, source_name, manifest):
    """Download a JPL ZIP, extract PDFs from it. Returns (status, count)."""
    zip_url = zip_info["zip_url"]
    part = zip_info["part"]

    try:
        time.sleep(RATE_LIMIT_SECS)
        r = requests.get(zip_url, headers={"User-Agent": USER_AGENT}, timeout=60)
        r.raise_for_status()

        z = zipfile.ZipFile(io.BytesIO(r.content))
        pdf_count = 0
        for name in z.namelist():
            if not name.lower().endswith(".pdf"):
                continue
            # Use just the PDF filename, avoid directory nesting
            pdf_filename = os.path.basename(name)
            if not pdf_filename:
                continue
            filepath = BASE_DIR / source_name / pdf_filename

            if filepath.exists() and filepath.stat().st_size > 0:
                pdf_count += 1
                continue

            with z.open(name) as src, open(filepath, "wb") as dst:
                shutil.copyfileobj(src, dst)

            valid, reason = validate_pdf(filepath)
            if not valid:
                filepath.unlink(missing_ok=True)
                continue

            file_size = filepath.stat().st_size
            manifest.append({
                "filename": pdf_filename,
                "source": source_name,
                "url": zip_url,
                "download_date": datetime.now().isoformat(),
                "file_size_bytes": file_size,
                "credibility_tier": SOURCES[source_name]["credibility_tier"],
                "report_source": SOURCES[source_name]["report_source"],
            })
            pdf_count += 1

        return "downloaded", pdf_count

    except Exception as e:
        return f"failed: {e}", 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_source(skey, limit, manifest, stats):
    """Fetch links and download PDFs for a single source."""
    source = SOURCES[skey]
    strategy = source["strategy"]
    url = source["url"]

    print(f"  Strategy: {strategy}")

    # --- Fetch links ---
    if skey == "gsfc_pub":
        pdf_urls = fetch_links_gsfc_pub(url, limit)
        print(f"  Found {len(pdf_urls)} PDF URLs")
        for pdf_url in tqdm(pdf_urls, desc=f"  Downloading ({skey})"):
            stats[skey]["attempted"] += 1
            status, _ = download_pdf(pdf_url, skey, manifest)
            if status == "downloaded":
                stats[skey]["downloaded"] += 1
            elif status == "skipped":
                stats[skey]["downloaded"] += 1  # already have it
            elif "failed" in status:
                stats[skey]["failed"] += 1
                tqdm.write(f"    FAIL: {os.path.basename(pdf_url)} — {status}")

    elif skey == "gsfc_test":
        pdf_urls = fetch_links_gsfc_test(url, limit)
        print(f"  Found {len(pdf_urls)} PDF URLs")
        for pdf_url in tqdm(pdf_urls, desc=f"  Downloading ({skey})"):
            stats[skey]["attempted"] += 1
            status, _ = download_pdf(pdf_url, skey, manifest)
            if status == "downloaded":
                stats[skey]["downloaded"] += 1
            elif status == "skipped":
                stats[skey]["downloaded"] += 1
            elif "failed" in status:
                stats[skey]["failed"] += 1
                tqdm.write(f"    FAIL: {os.path.basename(pdf_url)} — {status}")

    elif skey == "jpl":
        zip_items = fetch_links_jpl(url, limit)
        print(f"  Found {len(zip_items)} ZIP attachments")
        for item in tqdm(zip_items, desc=f"  Downloading ({skey})"):
            stats[skey]["attempted"] += 1
            status, count = download_jpl_zip(item, skey, manifest)
            if status == "downloaded":
                stats[skey]["downloaded"] += count
            elif "failed" in status:
                stats[skey]["failed"] += 1
                tqdm.write(f"    FAIL: {item['part']} — {status}")

    elif skey == "escies":
        items = fetch_links_escies(url, limit)
        for item in tqdm(items, desc=f"  Downloading ({skey})"):
            stats[skey]["attempted"] += 1
            pdf_url = item["url"]
            filename = item["filename"]
            filepath = BASE_DIR / skey / filename
            if filepath.exists() and filepath.stat().st_size > 0:
                stats[skey]["downloaded"] += 1
                continue
            try:
                time.sleep(RATE_LIMIT_SECS)
                r = requests.get(pdf_url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=30)
                r.raise_for_status()
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        f.write(chunk)
                valid, reason = validate_pdf(filepath)
                if not valid:
                    filepath.unlink(missing_ok=True)
                    stats[skey]["failed"] += 1
                    tqdm.write(f"    FAIL: {filename} — {reason}")
                    continue
                file_size = filepath.stat().st_size
                manifest.append({
                    "filename": filename,
                    "source": skey,
                    "url": pdf_url,
                    "download_date": datetime.now().isoformat(),
                    "file_size_bytes": file_size,
                    "credibility_tier": SOURCES[skey]["credibility_tier"],
                    "report_source": SOURCES[skey]["report_source"],
                    "lab_report_number": item.get("lab_report_number", ""),
                })
                stats[skey]["downloaded"] += 1
            except Exception as e:
                filepath.unlink(missing_ok=True)
                stats[skey]["failed"] += 1
                tqdm.write(f"    FAIL: {filename} — {e}")


def main():
    parser = argparse.ArgumentParser(description="RadQuery Corpus Downloader")
    parser.add_argument("--limit", type=int, default=20, help="Max PDFs per source")
    parser.add_argument("--source", choices=list(SOURCES.keys()), help="Target specific source")
    args = parser.parse_args()

    setup_directories()
    manifest = load_manifest()
    stats = {s: {"attempted": 0, "downloaded": 0, "failed": 0} for s in SOURCES}

    target_keys = [args.source] if args.source else list(SOURCES.keys())

    for skey in target_keys:
        print(f"\n{'='*60}")
        print(f"Source: {skey.upper()} ({SOURCES[skey]['report_source']})")
        print(f"{'='*60}")
        process_source(skey, args.limit, manifest, stats)

    save_manifest(manifest)

    # Summary
    print(f"\n{'='*60}")
    print(f"{'Source':<15} | {'Attempted':<10} | {'Downloaded':<12} | {'Failed':<8}")
    print("-" * 60)
    for src, s in stats.items():
        if s["attempted"] > 0 or not args.source:
            print(f"{src:<15} | {s['attempted']:<10} | {s['downloaded']:<12} | {s['failed']:<8}")
    print("=" * 60)
    print(f"Manifest: {BASE_DIR / 'manifest.json'} ({len(manifest)} entries)")


if __name__ == "__main__":
    main()
