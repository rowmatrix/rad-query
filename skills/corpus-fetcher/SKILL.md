---
name: corpus-fetcher
description: >
  Fetches, investigates, and downloads radiation test report PDFs for the
  RadQuery corpus from NASA GSFC, JPL, and ESCIES sources. Use this skill
  whenever the user wants to build or update the corpus, run fetch_corpus.py,
  investigate why a source returned 0 PDFs, fix scraper selectors, handle
  JS-rendered pages, or download radiation test data from any of the four
  configured sources. Always use this skill before writing or modifying any
  corpus download script.
---

# Corpus Fetcher Skill

You are building the RadQuery corpus — a collection of radiation test report
PDFs from public NASA, JPL, and ESA sources. Your job is to investigate each
source, figure out the correct download strategy, write or fix fetch_corpus.py,
and confirm PDFs are successfully downloaded into data/raw/.

---

## Model

Always use claude-opus-4-6 (claude-opus-4-6) for this skill. If you are running
as a subagent or via `claude -p`, pass `--model claude-opus-4-6`.

---

## Sources

| Key          | URL                                                                 | Type              | Credibility |
|--------------|---------------------------------------------------------------------|-------------------|-------------|
| gsfc_test    | https://nepp.nasa.gov/radhome/RadDatabase/RadDataBase.html          | Static HTML       | tier 1      |
| gsfc_pub     | https://nepp.nasa.gov/radhome/RadPubDbase/RadPubDbase.html          | Static HTML       | tier 1      |
| jpl          | https://www.jpl.nasa.gov/go/space-radiation/radiation-database/     | Likely JS-rendered| tier 1      |
| escies       | https://escies.org/labreport/radiationList                          | Likely JS-rendered| tier 2      |

---

## Step-by-step workflow

### Step 1 — Investigate each source

For every source that returned 0 PDFs, fetch the raw HTML and diagnose:

```python
import requests
from bs4 import BeautifulSoup

url = "<source_url>"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
print("Status:", r.status_code)
print("Length:", len(r.text))
# Look for: <a href="...pdf">, JS fetch calls, iframes, redirects
print(r.text[:5000])
```

Diagnose based on what you find:

- **Direct PDF links in HTML** → update BeautifulSoup selector in fetch_corpus.py
- **Links use relative paths** → use `urljoin(base_url, href)`
- **Links hidden in JS / loaded via fetch/XHR** → use Selenium or find the API endpoint
- **Page is a search form** → find the underlying API call in browser DevTools (Network tab) and call it directly with requests
- **Login wall / redirect** → document it; skip for MVP and note in README
- **Returns HTML "error" with 200 status** → check Content-Type header, validate response

### Step 2 — Find the real download endpoint for JS-rendered sources

For JPL and ESCIES, look for an underlying API:

```python
# Check response headers and content type
print(r.headers.get("Content-Type"))

# Search for API hints in the page source
import re
api_patterns = re.findall(r'(fetch|axios|XMLHttpRequest|\.get\(|api/|/data/|\.json)', r.text)
print(api_patterns[:20])

# Look for data embedded in the page as JSON
json_blobs = re.findall(r'window\.__\w+\s*=\s*(\{.*?\});', r.text, re.DOTALL)
for blob in json_blobs[:3]:
    print(blob[:500])
```

If you find a JSON API endpoint, call it directly — this is cleaner than Selenium.

### Step 3 — Install Selenium only if necessary

If no API endpoint is found and the page is fully JS-rendered:

```bash
pip install selenium webdriver-manager
```

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

opts = Options()
opts.add_argument("--headless")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=opts
)
driver.get(url)
import time; time.sleep(3)  # wait for JS to render
html = driver.page_source
driver.quit()
soup = BeautifulSoup(html, "html.parser")
```

### Step 4 — Update fetch_corpus.py

Once you know the correct strategy per source, update `scripts/fetch_corpus.py`:

- Each source gets its own `fetch_links_<source>(url)` function if strategies differ
- Keep the shared `download_file()` and manifest logic unchanged
- Add `credibility_tier` and `report_source` to every manifest entry:

```python
SOURCES = {
    "gsfc_test": {
        "url": "https://nepp.nasa.gov/radhome/RadDatabase/RadDataBase.html",
        "credibility_tier": 1,
        "report_source": "GSFC",
        "strategy": "static_html",   # static_html | json_api | selenium
    },
    ...
}
```

- Manifest entry must include:
  ```json
  {
    "filename": "...",
    "source": "gsfc_test",
    "url": "...",
    "download_date": "...",
    "file_size_bytes": 12345,
    "credibility_tier": 1,
    "report_source": "GSFC"
  }
  ```

### Step 5 — Run and verify

```bash
# Smoke test each source individually
python scripts/fetch_corpus.py --source gsfc_test --limit 5
python scripts/fetch_corpus.py --source gsfc_pub --limit 5
python scripts/fetch_corpus.py --source jpl --limit 5
python scripts/fetch_corpus.py --source escies --limit 5
```

Verify downloads are real PDFs (not HTML error pages):

```python
import os
data_dir = "data/raw"
for source in ["gsfc_test", "gsfc_pub", "jpl", "escies"]:
    path = os.path.join(data_dir, source)
    if not os.path.exists(path):
        print(f"{source}: directory missing")
        continue
    files = os.listdir(path)
    print(f"{source}: {len(files)} files")
    for f in files[:3]:
        fpath = os.path.join(path, source, f)
        size = os.path.getsize(fpath)
        # Real PDFs start with %PDF
        with open(fpath, 'rb') as fh:
            header = fh.read(4)
        print(f"  {f}: {size} bytes, header={header}")
```

PDFs smaller than 10KB or not starting with `%PDF` are likely error pages — delete and investigate.

### Step 6 — Full run

Once all sources work:

```bash
python scripts/fetch_corpus.py --limit 20
```

Report the final summary table and manifest entry count.

---

## Output contract

When this skill completes successfully:

1. `scripts/fetch_corpus.py` updated with correct strategy per source
2. `data/raw/manifest.json` populated with entries for all downloaded files
3. `data/raw/<source>/` directories populated with valid PDFs
4. Summary printed: source | attempted | downloaded | failed
5. Any sources that could not be scraped (login wall, unsolvable JS) documented
   in a comment block at the top of fetch_corpus.py

---

## Known gotchas

- NASA gov sites sometimes return HTTP 200 with an HTML "access denied" page —
  always validate the `%PDF` header, not just the status code
- ESCIES requires an EU-accessible IP in some configurations — note if 403
- JPL radiation database URL may redirect; follow redirects and log the final URL
- Rate limit: always wait 1.5s between requests; NASA servers will soft-ban
  aggressive scrapers
- Don't use `data/raw/` as a relative path if running from a subdirectory —
  use `Path(__file__).parent.parent / "data" / "raw"` for robustness

---

## Reference files

- `references/source_notes.md` — detailed notes on each source's HTML structure
  (update this as you learn more about each source)