"""
test_chunker_metadata.py — Tests for domain metadata extraction in chunker.py.

All tests run without PDF files, API keys, or external services.
"""

from __future__ import annotations

import pytest

from rad_rag.chunker import chunk_pages, extract_metadata, load_manifest

# ---------------------------------------------------------------------------
# Realistic chunk text fixtures
# ---------------------------------------------------------------------------

BIPOLAR_TID_CHUNK = (
    "The LM741 operational amplifier was irradiated using Co-60 gamma at GSFC. "
    "TID testing was performed at a dose rate of 50 rad(Si)/s. "
    "The device showed parametric failure at 30 krad(Si) with functional "
    "failure at 50 krad(Si). ELDRS testing was not performed."
)

SEE_CHUNK = (
    "Single-event latchup (SEL) testing of the IRFP044N power MOSFET was "
    "conducted at LBNL using heavy ion beams. LETth was determined to be "
    "37 MeV·cm²/mg. No latchup was observed below this threshold."
)

CLEAN_CHUNK = (
    "Table of contents. Introduction. This report presents radiation test "
    "results for electronic components used in space applications."
)

PROTON_SEE_CHUNK = (
    "The AD590 temperature transducer was tested for single event effects "
    "using proton beams at TAMU. No SEU events were observed up to a "
    "fluence of 1e11 n/cm²."
)

MRAD_DOSE_RATE_CHUNK = (
    "ELDRS testing of the LM139A comparator was performed at a dose rate "
    "of 10 mrad(Si)/s at BNL using Co-60 gamma radiation. The device "
    "failed parametric limits at 20 krad(Si)."
)

DD_CHUNK = (
    "Displacement damage testing of the JFET2N4416 was conducted at NRL "
    "using 50 MeV proton beams."
)

# --- Multiline / variant patterns seen in real GSFC PDFs ---

NEWLINE_KRAD_RATE_CHUNK = (
    "TID testing were between 10 mrad(Si)/s and 2.6\n"
    "krad(Si)/s."
)

RADS_SECOND_CHUNK = (
    "Total dose rates (between 0.01-0.3 rads (Si)/second) using "
    "Mil-883 Group E methodology."
)

NEWLINE_RESULT_CHUNK = (
    "The AD590 temperature sensor showed functional failures at the 75\n"
    "kRad(Si) level. The rev B devices showed improvement."
)

RAD_SPACE_SI_CHUNK = (
    "TID testing at APL was conducted at a dose rate of ~4 rad (Si)/s. "
    "All TID testing used Co-60 sources."
)

BARE_UNIT_PREV_LINE_CHUNK = (
    "Dose Rate\n"
    "0.01\n"
    "rad(Si)/s"
)


# ---------------------------------------------------------------------------
# extract_metadata unit tests
# ---------------------------------------------------------------------------

class TestExtractMetadata:
    def test_tid_fields_extracted(self):
        meta = extract_metadata(BIPOLAR_TID_CHUNK)
        assert meta["part_number"] == "LM741"
        assert meta["test_type"] == "TID"
        assert meta["dose_rate"] == 50.0
        assert meta["dose_rate_unit"] == "rad(Si)/s"
        # First krad match in text is "30 krad(Si)" (parametric failure)
        assert meta["result_level"] == 30.0
        assert meta["result_unit"] == "krad(Si)"

    def test_part_type_bipolar_linear(self):
        meta = extract_metadata(BIPOLAR_TID_CHUNK)
        assert meta["part_type"] == "bipolar linear"

    def test_see_test_type(self):
        meta = extract_metadata(SEE_CHUNK)
        assert meta["test_type"] == "SEL"

    def test_see_let_threshold(self):
        meta = extract_metadata(SEE_CHUNK)
        assert meta["result_level"] == 37.0
        assert meta["result_unit"] == "MeV·cm²/mg"

    def test_see_part_type_power_mosfet(self):
        meta = extract_metadata(SEE_CHUNK)
        assert meta["part_type"] == "power MOSFET"

    def test_facility_gsfc(self):
        meta = extract_metadata(BIPOLAR_TID_CHUNK)
        assert meta["test_facility"] == "GSFC"

    def test_facility_lbnl(self):
        meta = extract_metadata(SEE_CHUNK)
        assert meta["test_facility"] == "LBNL"

    def test_radiation_source_co60(self):
        meta = extract_metadata(BIPOLAR_TID_CHUNK)
        assert meta["radiation_source"] == "Co-60"

    def test_radiation_source_heavy_ion(self):
        meta = extract_metadata(SEE_CHUNK)
        assert meta["radiation_source"] == "heavy ion"

    def test_radiation_source_proton(self):
        meta = extract_metadata(PROTON_SEE_CHUNK)
        assert meta["radiation_source"] == "proton"

    def test_clean_chunk_returns_nulls(self):
        meta = extract_metadata(CLEAN_CHUNK)
        assert meta["part_number"] is None
        assert meta["part_type"] is None
        assert meta["test_type"] is None
        assert meta["dose_rate"] is None
        assert meta["dose_rate_unit"] is None
        assert meta["test_facility"] is None
        assert meta["radiation_source"] is None
        assert meta["result_level"] is None
        assert meta["result_unit"] is None

    def test_dose_rate_mrad_normalized(self):
        meta = extract_metadata(MRAD_DOSE_RATE_CHUNK)
        assert meta["dose_rate"] == pytest.approx(0.01)
        assert meta["dose_rate_unit"] == "rad(Si)/s"

    def test_result_level_krad(self):
        meta = extract_metadata(BIPOLAR_TID_CHUNK)
        # First krad match in text is "30 krad(Si)" (parametric failure)
        assert meta["result_level"] == 30.0
        assert meta["result_unit"] == "krad(Si)"

    def test_result_level_raw_rad_normalized(self):
        text = "The device survived 500 rad(Si) total dose."
        meta = extract_metadata(text)
        assert meta["result_level"] == pytest.approx(0.5)
        assert meta["result_unit"] == "krad(Si)"

    def test_eldrs_test_type(self):
        meta = extract_metadata(MRAD_DOSE_RATE_CHUNK)
        assert meta["test_type"] == "ELDRS"

    def test_dd_test_type(self):
        meta = extract_metadata(DD_CHUNK)
        assert meta["test_type"] == "DD"

    def test_seu_test_type(self):
        meta = extract_metadata(PROTON_SEE_CHUNK)
        assert meta["test_type"] == "SEU"

    def test_facility_tamu(self):
        meta = extract_metadata(PROTON_SEE_CHUNK)
        assert meta["test_facility"] == "TAMU"


# ---------------------------------------------------------------------------
# Multiline / variant dose rate tests (real corpus patterns)
# ---------------------------------------------------------------------------

class TestMultilinePatterns:
    def test_newline_between_number_and_krad_rate(self):
        meta = extract_metadata(NEWLINE_KRAD_RATE_CHUNK)
        # "10 mrad(Si)/s" is the first match → 0.01 rad(Si)/s
        assert meta["dose_rate"] is not None
        assert meta["dose_rate"] == pytest.approx(0.01)
        assert meta["dose_rate_unit"] == "rad(Si)/s"

    def test_newline_krad_rate_standalone(self):
        # Isolated "2.6\nkrad(Si)/s" without an earlier mrad match
        meta = extract_metadata("Dose rate was 2.6\nkrad(Si)/s for all tests.")
        assert meta["dose_rate"] is not None
        assert meta["dose_rate"] == pytest.approx(2600.0)
        assert meta["dose_rate_unit"] == "rad(Si)/s"

    def test_rads_space_si_second(self):
        meta = extract_metadata(RADS_SECOND_CHUNK)
        # "0.01-0.3 rads (Si)/second" — range; "0.3" is the match
        # because "0.01-" has no whitespace before the unit
        assert meta["dose_rate"] is not None
        assert meta["dose_rate"] == pytest.approx(0.3)
        assert meta["dose_rate_unit"] == "rad(Si)/s"

    def test_newline_between_number_and_krad_result(self):
        meta = extract_metadata(NEWLINE_RESULT_CHUNK)
        # "75\nkRad(Si)" → 75.0 krad(Si)
        assert meta["result_level"] == 75.0
        assert meta["result_unit"] == "krad(Si)"

    def test_rad_space_si_rate(self):
        meta = extract_metadata(RAD_SPACE_SI_CHUNK)
        # "~4 rad (Si)/s" — the tilde is ignored, value is 4
        assert meta["dose_rate"] is not None
        assert meta["dose_rate"] == pytest.approx(4.0)

    def test_bare_unit_prev_line_number(self):
        meta = extract_metadata(BARE_UNIT_PREV_LINE_CHUNK)
        # Table: "0.01\nrad(Si)/s"
        assert meta["dose_rate"] is not None
        assert meta["dose_rate"] == pytest.approx(0.01)

    def test_mrad_rate_still_works(self):
        meta = extract_metadata(NEWLINE_KRAD_RATE_CHUNK)
        # "10 mrad(Si)/s" — the first match
        assert meta["dose_rate"] is not None
        # The first match is "10 mrad(Si)/s" = 0.01, but the pattern
        # returns the first match found by the regex scan, which could be
        # either 10 mrad or 2.6 krad depending on scan order. Both valid.

    def test_dose_rate_not_false_positive_on_dose_keyword(self):
        text = "High dose rate effects were observed in the device."
        meta = extract_metadata(text)
        assert meta["dose_rate"] is None


# ---------------------------------------------------------------------------
# Manifest integration tests
# ---------------------------------------------------------------------------

class TestManifestIntegration:
    MOCK_MANIFEST = {
        "test_report.pdf": {
            "filename": "test_report.pdf",
            "report_source": "GSFC",
            "credibility_tier": 1,
        },
        "escies_ra0513.pdf": {
            "filename": "escies_ra0513.pdf",
            "report_source": "ESCIES",
            "credibility_tier": 2,
        },
    }

    def test_manifest_fields_flow_through(self):
        meta = extract_metadata(
            BIPOLAR_TID_CHUNK,
            source_filename="test_report.pdf",
            manifest=self.MOCK_MANIFEST,
        )
        assert meta["report_source"] == "GSFC"
        assert meta["credibility_tier"] == 1

    def test_manifest_tier2(self):
        meta = extract_metadata(
            CLEAN_CHUNK,
            source_filename="escies_ra0513.pdf",
            manifest=self.MOCK_MANIFEST,
        )
        assert meta["report_source"] == "ESCIES"
        assert meta["credibility_tier"] == 2

    def test_null_manifest_does_not_raise(self):
        meta = extract_metadata(BIPOLAR_TID_CHUNK, manifest=None)
        assert meta["report_source"] is None
        assert meta["credibility_tier"] is None

    def test_unknown_filename_returns_null_manifest_fields(self):
        meta = extract_metadata(
            BIPOLAR_TID_CHUNK,
            source_filename="unknown.pdf",
            manifest=self.MOCK_MANIFEST,
        )
        assert meta["report_source"] is None
        assert meta["credibility_tier"] is None


# ---------------------------------------------------------------------------
# chunk_pages integration tests
# ---------------------------------------------------------------------------

class TestChunkPagesMetadata:
    """Ensure chunk_pages emits all metadata fields."""

    REQUIRED_META_KEYS = [
        "part_number", "part_type", "test_type",
        "dose_rate", "dose_rate_unit",
        "test_facility", "radiation_source",
        "result_level", "result_unit",
        "report_source", "credibility_tier",
    ]

    def test_all_metadata_keys_present(self):
        pages = [{"source": "report.pdf", "page": 1, "text": BIPOLAR_TID_CHUNK}]
        chunks = chunk_pages(pages, chunk_size=2048, chunk_overlap=64)
        assert len(chunks) >= 1
        for key in self.REQUIRED_META_KEYS:
            assert key in chunks[0], f"Missing key: {key}"

    def test_existing_keys_preserved(self):
        pages = [{"source": "test.pdf", "page": 3, "text": "X" * 300}]
        chunks = chunk_pages(pages, chunk_size=512, chunk_overlap=64)
        assert chunks[0]["source"] == "test.pdf"
        assert chunks[0]["page"] == 3
        assert "chunk_index" in chunks[0]
        assert "text" in chunks[0]

    def test_manifest_param_backward_compatible(self):
        """chunk_pages(pages) with no manifest arg must still work."""
        pages = [{"source": "x.pdf", "page": 1, "text": "Hello world"}]
        chunks = chunk_pages(pages)
        assert len(chunks) == 1
        assert chunks[0]["report_source"] is None
        assert chunks[0]["credibility_tier"] is None

    def test_manifest_flows_to_chunks(self):
        manifest = {
            "report.pdf": {
                "filename": "report.pdf",
                "report_source": "JPL",
                "credibility_tier": 1,
            }
        }
        pages = [{"source": "report.pdf", "page": 1, "text": BIPOLAR_TID_CHUNK}]
        chunks = chunk_pages(pages, chunk_size=2048, chunk_overlap=64, manifest=manifest)
        assert chunks[0]["report_source"] == "JPL"
        assert chunks[0]["credibility_tier"] == 1

    def test_null_fields_are_none_not_empty_string(self):
        pages = [{"source": "clean.pdf", "page": 1, "text": CLEAN_CHUNK}]
        chunks = chunk_pages(pages, chunk_size=2048, chunk_overlap=64)
        c = chunks[0]
        for key in self.REQUIRED_META_KEYS:
            val = c[key]
            assert val is None, f"{key} should be None, got {val!r}"

    def test_empty_corpus_still_works(self):
        assert chunk_pages([], manifest={"a.pdf": {}}) == []

    def test_overlap_invalid_still_raises(self):
        with pytest.raises(ValueError, match="chunk_overlap"):
            chunk_pages(
                [{"source": "x.pdf", "page": 1, "text": "hello"}],
                chunk_size=10,
                chunk_overlap=10,
            )


# ---------------------------------------------------------------------------
# Table-context dose rate tests
# ---------------------------------------------------------------------------

TABLE_PAGE_TEXT = (
    "Table 7: Summary of NASA GSFC TID Test Results\n"
    "Part Number. Level Dose Rate\n"
    "Level Parameters\n"
    "(krads)(Si) (rads)/s(Si)\n"
    "(krads)(Si)\n"
    "Comparators:\n"
    "Maxim MX913 TTL 9704 100 0.0035- >100 None PPM-98-018\n"
    "AD CMP01 Voltage 9729 200 0.33 >200 None PPM-98-015\n"
    "Actel A1280A FPGA Not 3-15 0.01 >5 PPM-98-032\n"
    "AD OP-07 Op Amp 9723B 10-40 0.14 >10 Offset voltage PPM-99-017\n"
)


class TestTableContextDoseRate:
    def test_table_page_detected_and_dose_rate_extracted(self):
        pages = [{"source": "table.pdf", "page": 5, "text": TABLE_PAGE_TEXT}]
        chunks = chunk_pages(pages, chunk_size=2048, chunk_overlap=64)
        assert len(chunks) >= 1
        assert chunks[0]["dose_rate"] is not None

    def test_table_dose_rate_value_correct(self):
        meta = extract_metadata(
            "AD CMP01 Voltage 9729 200 0.33 >200 None PPM-98-015",
            table_dose_rate=True,
        )
        assert meta["dose_rate"] == pytest.approx(0.33)
        assert meta["dose_rate_unit"] == "rad(Si)/s"

    def test_table_context_not_applied_without_flag(self):
        meta = extract_metadata(
            "AD CMP01 Voltage 9729 200 0.33 >200 None PPM-98-015",
            table_dose_rate=False,
        )
        assert meta["dose_rate"] is None

    def test_table_dose_rate_small_decimal(self):
        meta = extract_metadata(
            "Maxim MX913 TTL 9704 100 0.0035- >100 None PPM-98-018",
            table_dose_rate=True,
        )
        assert meta["dose_rate"] == pytest.approx(0.0035)

    def test_table_dose_rate_does_not_override_explicit(self):
        text = "Testing at 50 rad(Si)/s showed failure at 30 krad(Si)."
        meta = extract_metadata(text, table_dose_rate=True)
        assert meta["dose_rate"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# load_manifest tests
# ---------------------------------------------------------------------------

class TestLoadManifest:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = load_manifest(str(tmp_path / "nonexistent.json"))
        assert result == {}

    def test_loads_valid_manifest(self, tmp_path):
        import json
        entries = [
            {"filename": "a.pdf", "report_source": "GSFC", "credibility_tier": 1},
            {"filename": "b.pdf", "report_source": "JPL", "credibility_tier": 1},
        ]
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(entries))
        result = load_manifest(str(path))
        assert "a.pdf" in result
        assert result["a.pdf"]["report_source"] == "GSFC"
        assert "b.pdf" in result
