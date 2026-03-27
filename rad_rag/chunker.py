"""
chunker.py — Split page text into overlapping chunks for embedding.

Chunks preserve metadata so every piece can be traced back to its
source document and page number — essential for citation in the UI.

Phase 1 adds domain metadata extraction: part_number, test_type,
dose_rate, test_facility, radiation_source, result_level, and
manifest-sourced report_source / credibility_tier.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Sequence

# ---------------------------------------------------------------------------
# Controlled vocabularies (from TECHNICAL_SPEC.md / SKILL.md)
# ---------------------------------------------------------------------------

PART_TYPES = [
    "bipolar linear",
    "bipolar digital",
    "CMOS digital",
    "CMOS linear",
    "power MOSFET",
    "JFET",
    "BJT",
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

TEST_TYPES = ["TID", "SEE", "DD", "ELDRS", "LATCH-UP", "SEL", "SET", "SEU", "MBU"]

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

PART_NUMBER_PATTERN = re.compile(
    r"\b("
    r"[A-Z]{2,5}\d{3,6}[A-Z]{0,3}"      # e.g. LM741, AD590, IRF540N
    r"|[A-Z]{1,3}\d{2,4}-\d{2,4}"        # e.g. OP-27, LT-1028
    r"|[A-Z]{2,4}\d{4}[A-Z]{2}"          # e.g. AD7524KN
    r"|[A-Z]{2,5}\d{3,6}[A-Z]?\d{0,2}"   # e.g. IRFP044N
    r")\b"
)

# TID result levels — "50 krad", "100 krad(Si)", "10 Mrad", "500 rad"
TID_RESULT_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*(krad(?:\(Si\))?|Mrad|rad(?:\(Si\))?)\b",
    re.IGNORECASE,
)

# Dose rate — "50 rad/s", "10 mrad/s", "0.01 rad(Si)/s"
DOSE_RATE_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*(mrad(?:\(Si\))?/s|krad(?:\(Si\))?/s|rad(?:\(Si\))?/s)",
    re.IGNORECASE,
)

# Test type keywords
TID_PATTERN = re.compile(r"\bTID\b|total ionizing dose", re.IGNORECASE)
SEE_PATTERN = re.compile(r"\bSEE\b|single.event effect", re.IGNORECASE)
SEL_PATTERN = re.compile(r"\bSEL\b|single.event latchup", re.IGNORECASE)
SET_PATTERN = re.compile(r"\bSET\b|single.event transient", re.IGNORECASE)
SEU_PATTERN = re.compile(r"\bSEU\b|single.event upset", re.IGNORECASE)
DD_PATTERN = re.compile(r"\bDD\b|displacement damage", re.IGNORECASE)
# ELDRS — match the keyword but exclude negated contexts ("not performed", "was not")
ELDRS_PATTERN = re.compile(r"\bELDRS\b|enhanced low.dose.rate", re.IGNORECASE)
ELDRS_NEGATION = re.compile(r"ELDRS\s+(?:testing\s+)?(?:was\s+)?not\s+performed", re.IGNORECASE)
LATCHUP_PATTERN = re.compile(r"\blatch-?up\b", re.IGNORECASE)

# Radiation source
CO60_PATTERN = re.compile(r"Co-?60|cobalt.60|gamma.(?:ray|irrad)", re.IGNORECASE)
PROTON_PATTERN = re.compile(r"\bproton\b", re.IGNORECASE)
HI_PATTERN = re.compile(r"heavy.ion|heavy ion", re.IGNORECASE)
ELECTRON_PATTERN = re.compile(r"\belectron\b", re.IGNORECASE)

# Test facilities
FACILITY_PATTERN = re.compile(
    r"\b(GSFC|TAMU|LBNL|JPL|NRL|AFRL|BNL|TRIUMF|PSI|RADEF|IU[Cc]F|NSRL)\b"
)

# LET threshold — "37 MeV·cm²/mg", "37 MeV-cm2/mg"
LET_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*MeV[·\-\s]cm[²2]/mg",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Manifest loader
# ---------------------------------------------------------------------------

def load_manifest(manifest_path: str = "data/raw/manifest.json") -> dict[str, dict]:
    """Return a lookup dict: {filename: {report_source, credibility_tier, ...}}"""
    path = Path(manifest_path)
    if not path.exists():
        return {}
    with open(path) as f:
        entries = json.load(f)
    return {e["filename"]: e for e in entries}


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def _extract_test_type(text: str) -> str | None:
    """Detect radiation test type from chunk text."""
    if ELDRS_PATTERN.search(text) and not ELDRS_NEGATION.search(text):
        return "ELDRS"
    if SEL_PATTERN.search(text):
        return "SEL"
    if SET_PATTERN.search(text):
        return "SET"
    if SEU_PATTERN.search(text):
        return "SEU"
    if SEE_PATTERN.search(text):
        return "SEE"
    if DD_PATTERN.search(text):
        return "DD"
    if TID_PATTERN.search(text):
        return "TID"
    if LATCHUP_PATTERN.search(text):
        return "LATCH-UP"
    return None


def _normalize_dose_rate(value: float, unit: str) -> float:
    """Normalize dose rate to rad(Si)/s."""
    unit_lower = unit.lower().split("/")[0]  # e.g. "mrad(si)" or "krad"
    if unit_lower.startswith("m"):
        return value / 1000.0
    if unit_lower.startswith("k"):
        return value * 1000.0
    return value  # already rad/s


def _normalize_result_level(value: float, unit: str) -> tuple[float, str]:
    """Normalize result level to krad(Si). Returns (value, unit_string)."""
    unit_lower = unit.lower().replace("(si)", "")
    if unit_lower == "mrad":
        return value * 1000.0, "krad(Si)"
    if unit_lower == "rad":
        return value / 1000.0, "krad(Si)"
    if unit_lower == "krad":
        return value, "krad(Si)"
    return value, "krad(Si)"


def _extract_radiation_source(text: str) -> str | None:
    if CO60_PATTERN.search(text):
        return "Co-60"
    if HI_PATTERN.search(text):
        return "heavy ion"
    if PROTON_PATTERN.search(text):
        return "proton"
    if ELECTRON_PATTERN.search(text):
        return "electron"
    return None


def _extract_part_type_regex(text: str) -> str | None:
    """Try to classify part type from text using keyword heuristics."""
    lower = text.lower()
    # Order matters: check specific types before generic ones
    if re.search(r"\bop[\s-]?amp\b|operational amplifier|\blinear\b.*\bbipolar\b|\bbipolar\b.*\blinear\b", lower):
        return "bipolar linear"
    if re.search(r"\bpower mosfet\b", lower):
        return "power MOSFET"
    if re.search(r"\bdc-dc converter\b|dc.to.dc\b", lower):
        return "DC-DC converter"
    if re.search(r"\boptocoupler\b|opto-coupler\b", lower):
        return "optocoupler"
    if re.search(r"\bsige hbt\b", lower):
        return "SiGe HBT"
    if re.search(r"\bgaas fet\b", lower):
        return "GaAs FET"
    if re.search(r"\bfpga\b", lower):
        return "FPGA"
    if re.search(r"\bsram\b", lower):
        return "SRAM"
    if re.search(r"\bdram\b", lower):
        return "DRAM"
    if re.search(r"\bflash\b.*\bmemory\b|\bflash\b.*\beepr", lower):
        return "Flash"
    if re.search(r"\beeprom\b", lower):
        return "EEPROM"
    if re.search(r"\badc\b|analog.to.digital", lower):
        return "ADC"
    if re.search(r"\bdac\b|digital.to.analog", lower):
        return "DAC"
    if re.search(r"\bvoltage regulator\b|\bldo\b|\bvreg\b", lower):
        return "voltage regulator"
    if re.search(r"\bmicrocontroller\b|\bmcu\b", lower):
        return "microcontroller"
    if re.search(r"\bmicroprocessor\b|\bcpu\b", lower):
        return "microprocessor"
    if re.search(r"\bjfet\b", lower):
        return "JFET"
    if re.search(r"\bbjt\b", lower):
        return "BJT"
    if re.search(r"\bdiode\b", lower):
        return "diode"
    if re.search(r"\bcmos\b.*\bdigital\b|\bdigital\b.*\bcmos\b", lower):
        return "CMOS digital"
    if re.search(r"\bcmos\b.*\blinear\b|\blinear\b.*\bcmos\b|\bcmos\b.*\bop[\s-]?amp", lower):
        return "CMOS linear"
    return None


def _extract_part_type_llm(chunk_text: str, part_number: str) -> str | None:
    """Use Claude Haiku to classify part type. Degrades gracefully."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    if len(chunk_text.strip()) < 50:
        return None

    try:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Classify this EEE component into exactly one category.\n"
                        f"Part: {part_number}\n"
                        f"Context: {chunk_text[:300]}\n\n"
                        f"Categories: {', '.join(PART_TYPES)}\n\n"
                        f"Reply with ONLY the category name, nothing else. "
                        f"If uncertain, reply: null"
                    ),
                }
            ],
        )
        result = response.content[0].text.strip()
        return result if result in PART_TYPES else None
    except Exception:
        return None


def extract_metadata(text: str, source_filename: str = "",
                     manifest: dict | None = None) -> dict:
    """Extract domain metadata from a chunk's text.

    Returns a dict with all metadata fields. Unextractable fields are None.
    """
    meta: dict = {
        "part_number": None,
        "part_type": None,
        "test_type": None,
        "dose_rate": None,
        "dose_rate_unit": None,
        "test_facility": None,
        "radiation_source": None,
        "result_level": None,
        "result_unit": None,
        "report_source": None,
        "credibility_tier": None,
    }

    # --- Pass 1: Regex extraction ---

    # Part number
    pn_match = PART_NUMBER_PATTERN.search(text)
    if pn_match:
        meta["part_number"] = pn_match.group(1)

    # Test type
    meta["test_type"] = _extract_test_type(text)

    # Dose rate
    dr_match = DOSE_RATE_PATTERN.search(text)
    if dr_match:
        raw_val = float(dr_match.group(1))
        raw_unit = dr_match.group(2)
        meta["dose_rate"] = _normalize_dose_rate(raw_val, raw_unit)
        meta["dose_rate_unit"] = "rad(Si)/s"

    # Result level — prefer LET for SEE tests, TID krad for TID tests
    let_match = LET_PATTERN.search(text)
    if let_match and meta["test_type"] in ("SEE", "SEL", "SET", "SEU", "LATCH-UP"):
        meta["result_level"] = float(let_match.group(1))
        meta["result_unit"] = "MeV·cm²/mg"
    else:
        # Collect positions of dose-rate matches to exclude them
        dr_positions = {m.start() for m in DOSE_RATE_PATTERN.finditer(text)}
        for tid_match in TID_RESULT_PATTERN.finditer(text):
            # Skip if this match overlaps with a dose-rate expression
            if tid_match.start() in dr_positions:
                continue
            # Also skip if the text right after the match contains "/s"
            end_pos = tid_match.end()
            trailing = text[end_pos:end_pos + 5]
            if re.match(r"(?:\(Si\))?/s", trailing, re.IGNORECASE):
                continue
            raw_val = float(tid_match.group(1))
            raw_unit = tid_match.group(2)
            norm_val, norm_unit = _normalize_result_level(raw_val, raw_unit)
            meta["result_level"] = norm_val
            meta["result_unit"] = norm_unit
            break

    # Radiation source
    meta["radiation_source"] = _extract_radiation_source(text)

    # Test facility
    fac_match = FACILITY_PATTERN.search(text)
    if fac_match:
        meta["test_facility"] = fac_match.group(1)

    # Part type — regex first
    meta["part_type"] = _extract_part_type_regex(text)

    # --- Pass 2: LLM extraction for part_type (if still None) ---
    if meta["part_number"] and meta["part_type"] is None:
        meta["part_type"] = _extract_part_type_llm(text, meta["part_number"])

    # --- Manifest fields ---
    if manifest and source_filename:
        entry = manifest.get(source_filename)
        if entry:
            meta["report_source"] = entry.get("report_source")
            meta["credibility_tier"] = entry.get("credibility_tier")

    return meta


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Rough sentence splitter that keeps abbreviations intact."""
    return re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())


# ---------------------------------------------------------------------------
# Main chunker
# ---------------------------------------------------------------------------

def chunk_pages(
    pages: Sequence[dict],
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    manifest: dict | None = None,
) -> list[dict]:
    """Split a list of page dicts into overlapping text chunks.

    Args:
        pages: Output of ingest.ingest_directory() or ingest.iter_pages().
        chunk_size: Target character length of each chunk.
        chunk_overlap: Number of characters shared between consecutive chunks.
        manifest: Optional dict from load_manifest() for report_source /
            credibility_tier. If None, those fields default to None.

    Returns:
        List of chunk dicts with text and domain metadata.
    """
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be less than chunk_size")

    chunks: list[dict] = []

    for page in pages:
        text = page["text"].strip()
        if not text:
            continue

        source = page["source"]
        page_num = page["page"]

        start = 0
        chunk_index = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end].strip()
            if chunk_text:
                meta = extract_metadata(chunk_text, source, manifest)
                chunk = {
                    "source": source,
                    "page": page_num,
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    **meta,
                }
                chunks.append(chunk)
            start += chunk_size - chunk_overlap
            chunk_index += 1

    return chunks
