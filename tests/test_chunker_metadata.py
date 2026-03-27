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
