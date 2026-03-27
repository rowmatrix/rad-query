# Source Notes

Confirmed findings from initial corpus fetch run. Do not re-investigate
these sources — strategies are validated and working.

---

## gsfc_test
URL: https://nepp.nasa.gov/radhome/RadDatabase/RadDataBase.html
Strategy: **Selenium** (jqGrid pagination)
Status: ✅ Working — 15/15 downloaded, 0 failed
Notes:
- ColdFusion API returns 403 for direct HTTP requests — Selenium required
- Page uses jqGrid with pagination; Selenium must paginate through all pages
- PDFs served from: nepp.nasa.gov/radhome/papers/
- Credibility tier: 1 (GSFC qualification-grade test data)

---

## gsfc_pub
URL: https://nepp.nasa.gov/radhome/RadPubDbase/RadPubDbase.html
Strategy: **JSON API** — `parts.cfc?method=getPubs`
Status: ✅ Working — 20/20 downloaded, 0 failed
Notes:
- ColdFusion API accessible via direct GET request (no Selenium needed)
- Returns paginated JSON; PDF URL is in field index 6 of each record
- These are GSFC REAG publications — may include journal papers as well as
  free technical reports; validate each download is open-access
- Credibility tier: 1

---

## jpl
URL: https://www.jpl.nasa.gov/go/space-radiation/radiation-database/
Strategy: **JSON API** — `csr-api.jpl.nasa.gov/records` + ZIP extraction
Status: ✅ Working — 6 ZIPs → 12 PDFs, 0 failed
Notes:
- Clean REST API at csr-api.jpl.nasa.gov/records
- Attachments are ZIP files containing one or more PDF test reports
- Must extract ZIPs after download; store extracted PDFs in data/raw/jpl/
- 12 PDFs from 6 ZIPs — some ZIPs contain multiple reports per part
- Credibility tier: 1 (JPL qualification-grade)

---

## escies
URL: https://escies.org/labreport/radiationList
Strategy: **requests + browser User-Agent** (no auth required)
Status: ✅ Accessible — PDFs return HTTP 200 + valid %PDF header
Notes:
- Claude Code was hitting 302 SSO redirect due to Python's default User-Agent
- Browser User-Agent bypasses the redirect entirely — no actual auth needed
- Metadata for 186 reports is embedded as JS in the listing page
- PDF links follow pattern: https://escies.org/labreport/<report_id>
- Must use: headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
- Credibility tier: 2 (ESA standard, good quality)

---

## Corpus summary (Phase 1 initial run)
- Total valid PDFs: 42 (ESCIES re-run pending)
- gsfc_test: 15 PDFs
- gsfc_pub: 20 PDFs
- jpl: 12 PDFs (from 6 ZIPs)
- escies: 0 → re-run pending (was incorrectly skipped — browser User-Agent required)
- Manifest: data/raw/manifest.json