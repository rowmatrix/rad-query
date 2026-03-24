# RadQuery

**RAG-powered radiation test data intelligence for EEE parts.**

Natural-language queries over NASA NEPP, ESA, and JEDEC radiation test reports —
with cited answers, domain-aware caveats, and test methodology context.

```
> "What is the TID tolerance of the LM741?"

  The LM741 shows TID tolerance of 10–50 krad(Si) depending on lot and dose rate.
  ⚠ ELDRS risk: bipolar linear IC — high-dose-rate test results may not hold
    at mission-relevant rates (< 10 mrad/s). See NEPP TM-2003-211285, p. 14.
```

---

## Why this exists

Radiation test data for EEE parts is scattered across hundreds of PDFs on
NASA NEPP, GSFC REAG, COSMIAC, and ESA ESCIES. Existing tools return structured
lookup tables. RadQuery returns *interpretive answers* — surfacing the dose-rate
context, ELDRS flags, lot-variability warnings, and methodology caveats that
determine whether a test result is actually valid for your mission.

The question "is this 100 krad rating valid for my low dose rate GEO mission?"
requires reading test methodology. RadQuery does that.

---

## Demo

> 🚧 Demo GIF coming after Phase 1 milestone — check back soon.

<!-- INSERT DEMO GIF HERE -->

---

## Features

- **Natural-language queries** over a curated corpus of public radiation test reports
- **Cited answers** with source document, page reference, and report tier
- **Domain caveat engine** — five expert rules applied automatically:
  - ELDRS flag for bipolar linear ICs tested at high dose rate
  - Dose-rate surface on every TID result
  - Lot-variability warning for COSMIAC / small-sample sources
  - Parametric vs. functional failure endpoint distinction
  - Methodology tier flag (NEPP qualification-grade vs. university survey)
- **Configurable LLM backend** — OpenAI GPT-4o or Anthropic Claude via env var
- **Freemium-ready** — 10 free queries/day on public corpus

---

## Corpus (Phase 1)

| Source | Type | Access |
|---|---|---|
| [NASA NEPP](https://nepp.nasa.gov/radhome/RadDatabase/RadDataBase.html) | Radiation test reports | Public |
| [NASA GSFC REAG](https://radhome.gsfc.nasa.gov) | Test report listing | Public |
| [COSMIAC](https://cosmiac.unm.edu/thrust-areas/rha_cots_2011_0124.xlsx) | Survey results + spreadsheets | Public |
| EEE-INST-002 | NASA qualification standard | Public |
| ECSS-Q-ST-60 | ESA qualification standard | Public |

---

## Architecture

```
corpus/raw/          ← PDFs from NASA NEPP, GSFC REAG, COSMIAC
      ↓
scripts/fetch_corpus.py   ← download + manifest
      ↓
src/ingestion/
  ingest.py          ← pdfplumber (primary) / pymupdf (scanned fallback)
  chunker.py         ← chunking + domain metadata extraction
                       (part_number, test_type, dose_rate, facility, ...)
      ↓
src/retrieval/
  embedder.py        ← sentence-transformers → ChromaDB
  retriever.py       ← similarity search + metadata filters
  domain_caveats.py  ← ELDRS / dose-rate / lot-variability rule engine
      ↓
src/ui/
  app.py             ← Streamlit chat UI with citations + caveat callouts
```

---

## Quickstart

```bash
# Clone and set up environment
git clone https://github.com/rowmatrix/rad-rag.git
cd rad-rag
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure LLM backend
cp .env.example .env
# Edit .env: set OPENAI_API_KEY or ANTHROPIC_API_KEY, and LLM_BACKEND

# Download corpus (Phase 1 public sources)
python scripts/fetch_corpus.py --limit 20

# Ingest and index
python scripts/build_index.py

# Run the app
streamlit run src/ui/app.py
```

---

## Development

```bash
# Run tests (mock-based, no API keys or PDFs required)
pytest tests/ -v

# Run a single module test
pytest tests/test_chunker.py -v
```

### Environment variables

| Variable | Values | Default |
|---|---|---|
| `LLM_BACKEND` | `openai` \| `anthropic` | `openai` |
| `OPENAI_API_KEY` | your key | — |
| `ANTHROPIC_API_KEY` | your key | — |
| `CHROMA_PERSIST_DIR` | path | `chroma_db/` |
| `EMBEDDING_MODEL` | model name | `all-MiniLM-L6-v2` |

---

## Roadmap

**Phase 1 — MVP** *(in progress)*
- [x] Ingestion pipeline (pdfplumber + pymupdf fallback)
- [x] Chunker with source/page/chunk_index IDs
- [x] Configurable embedder (sentence-transformers / OpenAI)
- [x] ChromaDB vector store
- [x] Streamlit UI scaffold
- [ ] Corpus download script + manifest
- [ ] Domain metadata extraction in chunker (part_number, dose_rate, test_type)
- [ ] `domain_caveats.py` rule engine
- [ ] Citation UI in app.py
- [ ] End-to-end validation on 5 known queries

**Phase 2 — Beta**
- [ ] User-uploaded proprietary reports (zero-retention mode)
- [ ] Source credibility scores
- [ ] ELDRS / dose-rate flags surfaced in UI
- [ ] Waitlist → paid tier
- [ ] Team workspaces

**Phase 3 — Product**
- [ ] API access for BOM-level rad queries
- [ ] ObsoAlert integration
- [ ] SBIR Phase I submission

---

## Background

RadQuery is built by [Ibar Romay](https://linkedin.com/in/ibarromay) — electrical
engineer with 5 years at NASA JPL and Raytheon RTX specializing in EEE components
and radiation effects. Building at the intersection of physics, data engineering, 
and AI.

The domain expertise embedded in the caveat engine — knowing *which* caveats to
surface, *when* a dose-rate matters, and *why* a bipolar result needs an ELDRS
flag — is what separates RadQuery from a generic document-chat wrapper.

---

## License

MIT
