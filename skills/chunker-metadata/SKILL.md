---
name: chunker-metadata
description: >
  Adds domain metadata extraction to rad_rag/chunker.py for the RadQuery
  project. Use this skill whenever the user wants to extract part_number,
  part_type, test_type, dose_rate, test_facility, radiation_source,
  result_level, report_source, or credibility_tier from radiation test report
  chunks. Always use this skill before modifying chunker.py or writing any
  metadata extraction logic for RadQuery.
---

# Chunker Metadata Extraction Skill

You are adding domain metadata extraction to `rad_rag/chunker.py` for RadQuery.
Every chunk must carry structured metadata so the domain caveat engine
(`domain_caveats.py`) can fire ELDRS flags, dose-rate warnings, and
lot-variability alerts.

---

## Model

Use claude-opus-4-6 for this skill.

---

## Context — read first

Before writing any code, read these files in order:

1. `rad_rag/chunker.py` — current implementation
2. `TECHNICAL_SPEC.md` — required chunk output schema (Section 3.2)
3. `tests/test_rad_rag.py` — existing chunker tests to preserve
4. `data/raw/manifest.json` — source of `report_source` and `credibility_tier`

---

## Required chunk output schema

Every chunk dict must contain ALL of these fields after your changes.
Fields that cannot be extracted must be `null` — never omit, never hallucinate.

```python
{
    # Existing fields — do not change
    "source": str,           # PDF filename
    "page": int,             # 1-indexed
    "chunk_index": int,      # 0-indexed within page

    # Existing field — do not change
    "text": str,             # chunk text

    # New fields — add these
    "part_number": str | None,       # e.g. "LM741", "AD590", "IRF540"
    "part_type": str | None,         # see controlled vocabulary below
    "test_type": str | None,         # "TID" | "SEE" | "DD" | "ELDRS" | "LATCH-UP"
    "dose_rate": float | None,       # numeric value only, in rad(Si)/s
    "dose_rate_unit": str | None,    # always "rad(Si)/s" if extracted
    "test_facility": str | None,     # e.g. "GSFC", "TAMU", "LBNL", "JPL"
    "radiation_source": str | None,  # "Co-60" | "heavy ion" | "proton" | "electron"
    "result_level": float | None,    # numeric TID/LET/fluence value
    "result_unit": str | None,       # "krad(Si)" | "MeV·cm²/mg" | "n/cm²"
    "report_source": str | None,     # from manifest: "GSFC" | "JPL" | "ESCIES"
    "credibility_tier": int | None,  # from manifest: 1 | 2 | 3
}
```

---

## Controlled vocabulary

### part_type (critical for ELDRS flagging)
```python
PART_TYPES = [
    "bipolar linear",      # op-amps, comparators, voltage refs — ELDRS risk
    "bipolar digital",     # TTL logic — lower ELDRS risk than linear
    "CMOS digital",        # most logic ICs
    "CMOS linear",         # CMOS op-amps, ADCs
    "power MOSFET",
    "JFET",
    "BJT",                 # discrete bipolar transistor
    "diode",
    "voltage regulator",
    "ADC",
    "DAC",
    "FPGA",
    "SRAM",
    "DRAM",
    "Flash",
    "EEPROM",
    "microprocessor",
    "microcontroller",
    "optocoupler",
    "DC-DC converter",
    "GaAs FET",
    "SiGe HBT",
]
```

### test_type
```python
TEST_TYPES = ["TID", "SEE", "DD", "ELDRS", "LATCH-UP", "SEL", "SET", "SEU", "MBU"]
```

---

## Extraction strategy

Use a two-pass approach per chunk:

### Pass 1 — Regex extraction (fast, deterministic)

Run ALL regex patterns on `chunk["text"]` before calling any LLM.
Regex handles the majority of structured fields in radiation test reports.

```python
import re

# Part numbers — radiation test reports use consistent formats
PART_NUMBER_PATTERN = re.compile(
    r'\b('
    r'[A-Z]{2,5}\d{3,6}[A-Z]{0,3}'   # e.g. LM741, AD590, IRF540N
    r'|[A-Z]{1,3}\d{2,4}-\d{2,4}'    # e.g. OP-27, LT-1028
    r'|[A-Z]{2,4}\d{4}[A-Z]{2}'      # e.g. AD7524KN
    r')\b'
)

# TID result levels — "50 krad", "100 krad(Si)", "10 Mrad"
TID_RESULT_PATTERN = re.compile(
    r'(\d+\.?\d*)\s*(k?rad(?:\(Si\))?|Mrad)',
    re.IGNORECASE
)

# Dose rate — "50 rad/s", "10 mrad/s", "0.01 rad(Si)/s"
DOSE_RATE_PATTERN = re.compile(
    r'(\d+\.?\d*)\s*(m?rad(?:\(Si\))?/s)',
    re.IGNORECASE
)

# Test type keywords
TID_PATTERN = re.compile(r'\bTID\b|total ionizing dose', re.IGNORECASE)
SEE_PATTERN = re.compile(r'\bSEE\b|single.event effect', re.IGNORECASE)
SEL_PATTERN = re.compile(r'\bSEL\b|single.event latchup', re.IGNORECASE)
DD_PATTERN  = re.compile(r'\bDD\b|displacement damage', re.IGNORECASE)
ELDRS_PATTERN = re.compile(r'\bELDRS\b|enhanced low.dose.rate', re.IGNORECASE)

# Radiation source
CO60_PATTERN   = re.compile(r'Co-?60|cobalt.60', re.IGNORECASE)
PROTON_PATTERN = re.compile(r'\bproton\b', re.IGNORECASE)
HI_PATTERN     = re.compile(r'heavy.ion|heavy ion', re.IGNORECASE)

# Test facilities
FACILITY_PATTERN = re.compile(
    r'\b(GSFC|TAMU|LBNL|JPL|NRL|AFRL|BNL|TRIUMF|PSI|RADEF)\b'
)
```

**Dose rate normalization:** Always normalize to rad(Si)/s:
- `50 mrad/s` → `0.05`
- `10 krad/s` → `10000.0`
- `50 rad/s` → `50.0`

**result_level normalization:** Always store in krad(Si):
- `50 krad` → `50.0`
- `1 Mrad` → `1000.0`
- `500 rad` → `0.5`

### Pass 2 — LLM extraction (for part_type only)

Only call the LLM for `part_type` — it requires semantic understanding of
device descriptions that regex cannot reliably handle.

**Only call LLM if:**
- `part_number` was found in Pass 1, AND
- `part_type` is still `None` after regex, AND
- chunk text contains device description language

**LLM call — keep it cheap and fast:**
```python
import anthropic

def extract_part_type_llm(chunk_text: str, part_number: str) -> str | None:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",   # cheapest model — classification only
        max_tokens=20,
        messages=[{
            "role": "user",
            "content": (
                f"Classify this EEE component into exactly one category.\n"
                f"Part: {part_number}\n"
                f"Context: {chunk_text[:300]}\n\n"
                f"Categories: {', '.join(PART_TYPES)}\n\n"
                f"Reply with ONLY the category name, nothing else. "
                f"If uncertain, reply: null"
            )
        }]
    )
    result = response.content[0].text.strip()
    return result if result in PART_TYPES else None
```

**LLM call guard — do NOT call LLM if:**
- `ANTHROPIC_API_KEY` is not set (degrade gracefully, leave `part_type=None`)
- chunk text is under 50 characters
- No `part_number` was found (nothing to classify)

---

## manifest.json integration

`report_source` and `credibility_tier` come from the manifest, not from
chunk text. Load the manifest once at the start and pass source metadata
into `chunk_pages()`.

```python
import json
from pathlib import Path

def load_manifest(manifest_path="data/raw/manifest.json") -> dict[str, dict]:
    """Return a lookup dict: {filename: {report_source, credibility_tier}}"""
    path = Path(manifest_path)
    if not path.exists():
        return {}
    with open(path) as f:
        entries = json.load(f)
    return {e["filename"]: e for e in entries}
```

Update `chunk_pages()` signature:
```python
def chunk_pages(
    pages: list[dict],
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    manifest: dict | None = None,    # add this parameter
) -> list[dict]:
```

If `manifest` is `None`, `report_source` and `credibility_tier` default to
`None` — do not raise an error. This keeps existing tests passing without
a manifest file.

---

## Implementation rules

1. **Never hallucinate metadata.** If a field cannot be extracted with
   confidence, set it to `None`. A `None` is better than a wrong value —
   wrong part_type will fire incorrect ELDRS flags.

2. **Regex first, always.** Do not call the LLM for fields that regex can
   handle. LLM calls cost money and add latency.

3. **Preserve existing behavior.** All existing tests in `tests/test_rad_rag.py`
   must still pass after your changes. Run `pytest tests/test_rad_rag.py -v`
   before and after.

4. **Backward compatible signature.** `chunk_pages(pages)` with no other args
   must still work. All new parameters must have defaults.

5. **No new required dependencies.** `anthropic` is already in
   `requirements.txt`. Do not add new packages.

---

## Tests to write

Create `tests/test_chunker_metadata.py` with these cases:

```python
# Fixture: realistic chunk text samples from radiation test reports
BIPOLAR_TID_CHUNK = """
The LM741 operational amplifier was irradiated using Co-60 gamma at GSFC.
TID testing was performed at a dose rate of 50 rad(Si)/s.
The device showed parametric failure at 30 krad(Si) with functional
failure at 50 krad(Si). ELDRS testing was not performed.
"""

SEE_CHUNK = """
Single-event latchup (SEL) testing of the IRFP044N power MOSFET was
conducted at LBNL using heavy ion beams. LETth was determined to be
37 MeV·cm²/mg. No latchup was observed below this threshold.
"""

CLEAN_CHUNK = """
Table of contents. Introduction. This report presents radiation test
results for electronic components used in space applications.
"""

def test_tid_metadata_extracted(): ...         # part_number, test_type=TID, dose_rate
def test_part_type_bipolar_linear(): ...       # LM741 → "bipolar linear"
def test_see_test_type_extracted(): ...        # SEL → test_type="SEE"
def test_facility_extracted(): ...             # GSFC, LBNL
def test_radiation_source_co60(): ...          # Co-60
def test_clean_chunk_returns_nulls(): ...      # no false positives
def test_dose_rate_normalized_to_rads(): ...   # mrad/s → rad/s conversion
def test_result_level_normalized_to_krad(): ...# krad(Si) stored correctly
def test_manifest_fields_flow_through(): ...   # report_source, credibility_tier
def test_null_manifest_does_not_raise(): ...   # graceful degradation
def test_existing_chunker_tests_pass(): ...    # run original test suite
```

---

## Completion criteria

Run this checklist before declaring done:

```bash
# 1. All existing tests still pass
pytest tests/test_rad_rag.py -v

# 2. New metadata tests pass
pytest tests/test_chunker_metadata.py -v

# 3. Smoke test on real corpus — spot-check 3 chunks per source
python -c "
from rad_rag.ingest import ingest_directory
from rad_rag.chunker import chunk_pages, load_manifest

manifest = load_manifest()
pages = ingest_directory('data/raw/gsfc_test')[:5]   # first 5 pages only
chunks = chunk_pages(pages, manifest=manifest)

# Print metadata for first chunk of each page
for c in chunks[:5]:
    print({k: v for k, v in c.items() if k != 'text'})
"

# 4. No chunk has an empty text field
# 5. null fields are null — not empty string, not 0, not False
# 6. part_type values are all from the controlled vocabulary or null
```

---

## Files to modify

- `rad_rag/chunker.py` — add metadata extraction
- `tests/test_chunker_metadata.py` — new test file (create)
- `requirements.txt` — no changes needed

## Files to NOT modify

- `rad_rag/embedder.py` — out of scope for this skill
- `rad_rag/retriever.py` — out of scope for this skill
- `rad_rag/ingest.py` — out of scope for this skill
- `tests/test_rad_rag.py` — do not modify existing tests
