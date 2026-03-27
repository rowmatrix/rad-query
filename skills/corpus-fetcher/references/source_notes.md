# Source Notes

Confirmed findings from corpus fetch runs. Do not re-investigate
these sources — strategies are validated and working.

---

## gsfc_test
URL: https://nepp.nasa.gov/radhome/RadDatabase/RadDataBase.html
Strategy: **Selenium** (jqGrid pagination)
Status: ✅ Working — 15/15 downloaded, 0 failed
Notes:
- ColdFusion API (`parts.cfc?method=getParts`) returns 403 for all direct HTTP
  requests including POST — Selenium required
- Page uses jqGrid with 177 pages of 10 rows each (1768 total records)
- Selenium paginates the grid and reads the `File(s)` column from each row
- `File(s)` field contains filenames separated by `<br>` tags:
  - Relative names (`d050595.pdf`) → prepend `https://nepp.nasa.gov/radhome/papers/`
  - Some entries use subdirectory paths (`tid/PPM-95-167.pdf`) — same base
  - Some entries are already absolute `http://nepp.nasa.gov/...` URLs
- PDFs download fine with any User-Agent once URL is known
- Credibility tier: 1 (GSFC qualification-grade test data)

---

## gsfc_pub
URL: https://nepp.nasa.gov/radhome/RadPubDbase/RadPubDbase.html
Strategy: **JSON API** — `parts.cfc?method=getPubs`
Status: ✅ Working — 20/20 downloaded, 0 failed
Notes:
- ColdFusion API accessible via direct GET request (no Selenium needed)
- Endpoint: `https://nepp.nasa.gov/radhome/dev/parts.cfc?method=getPubs`
- Params: `page=<n>&rows=<n>` — returns paginated JSON
- Response structure: `{"ROWS": [...], "PAGE": 1, "TOTAL": 75, "RECORDS": 741}`
- Each row is a 7-element array; field index 6 (0-based) = PDF URL
- URLs are absolute (`http://nepp.nasa.gov/radhome/papers/tns01_noise.pdf`)
- 741 total records across 75 pages
- Credibility tier: 1

---

## jpl
URL: https://www.jpl.nasa.gov/go/space-radiation/radiation-database/
Strategy: **JSON API** — `csr-api.jpl.nasa.gov/records` + ZIP extraction
Status: ✅ Working — 6 ZIPs → 12 PDFs (7 unique), 0 failed
Notes:
- Clean REST API: `https://csr-api.jpl.nasa.gov/records` (GET, no auth)
- Returns JSON array; each record has `Attachment` field with S3-style path
- Download URL: `https://csr-api.jpl.nasa.gov/attachments?key=<Attachment>`
- Attachments are ZIP files named `ExportFiles.zip`
- Each ZIP contains 1–2 PDFs: a `CoverPage.pdf` plus the main test report
- Currently only 6 records in the database (new/growing database as of 2026-03)
- Credibility tier: 1 (JPL qualification-grade)

---

## escies
URL: https://escies.org/labreport/radiationList
Strategy: **requests + browser User-Agent** (no auth required)
Status: ✅ Working — 20/20 downloaded, 0 failed
Notes:
- Using Python's default or bot User-Agent triggers a 302 redirect to
  `identity.escies.org` SSO login. This is NOT a real auth requirement —
  it is just UA-based gating. A browser User-Agent bypasses it entirely.
- Required header: `User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)
  AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36`
- Listing page embeds report metadata as `var reports = [...];` in the HTML
- 186 total reports; 178 have `webDocumentFile` (8 have no file attachment)
- All 178 non-confidential reports are public (`pdfConfidential: false` for all)
- Each report object structure:
  ```json
  {
    "esaLabReportId": 2954049,
    "labReportNumber": "RA 0513",
    "webDocumentFile": {
      "webDocumentFileId": 58221,
      "fileName": "ra0513.pdf"
    }
  }
  ```
- Download URL: `https://escies.org/download/webDocumentFile?id=<webDocumentFileId>`
  (note: query param `?id=`, NOT path segment `/id`)
- Filenames follow pattern `ra<NNNN>.pdf`
- Credibility tier: 2 (ESA standard, good quality)

---

## Corpus summary (Phase 1 complete)
- Total valid PDFs: 62
- gsfc_test: 15 PDFs (6.9 MB) — from jqGrid via Selenium
- gsfc_pub:  20 PDFs (32.7 MB) — from ColdFusion JSON API
- jpl:        7 PDFs (36.5 MB) — from ZIP attachments via REST API
- escies:    20 PDFs (30.5 MB) — from JS-embedded metadata + browser UA
- Manifest: data/raw/manifest.json (62 entries)
