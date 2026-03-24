"""
app.py — Streamlit UI for rad-rag.

Run with:
    streamlit run app.py
"""

import streamlit as st

from rad_rag.retriever import answer

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="rad-rag",
    page_icon="☢️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar — corpus info + settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("☢️ rad-rag")
    st.caption("RAG over radiation test report corpora")
    st.markdown("---")

    n_results = st.slider(
        "Retrieved chunks", min_value=1, max_value=10, value=5,
        help="Number of document chunks to retrieve before synthesis."
    )

    st.markdown("---")
    st.markdown(
        "**Sources ingested** are stored in `data/processed/chroma/`. "
        "Run `python scripts/build_index.py` to ingest new PDFs from `data/raw/`."
    )
    st.markdown("---")
    st.caption("Built by [Ibar Romay](https://github.com/rowmatrix)")

# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------
st.header("Radiation Test Report Query")
st.markdown(
    "Ask a question about radiation effects on electronic components. "
    "Answers are grounded in ingested test reports with page-level citations."
)

example_queries = [
    "What is the TID tolerance of the LM741 op-amp?",
    "Which CMOS devices are most susceptible to SEL?",
    "What dose rate was used in the TID tests for bipolar transistors?",
    "Summarize SEE test results for GaAs FETs.",
]

st.markdown("**Example queries:**")
cols = st.columns(2)
for i, q in enumerate(example_queries):
    if cols[i % 2].button(q, key=f"example_{i}"):
        st.session_state["query"] = q

query = st.text_input(
    "Your query",
    value=st.session_state.get("query", ""),
    placeholder="e.g. What is the TID tolerance of the LM741 op-amp?",
)

run = st.button("Search", type="primary", disabled=not query.strip())

if run and query.strip():
    with st.spinner("Retrieving and synthesizing answer…"):
        try:
            result = answer(query.strip(), n_results=n_results)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error: {exc}")
            st.stop()

    st.markdown("### Answer")
    st.markdown(result["answer"])

    if result["sources"]:
        st.markdown("### Retrieved Sources")
        for i, src in enumerate(result["sources"], start=1):
            st.markdown(
                f"**[{i}]** `{src['source']}` — page {src['page']} "
                f"*(similarity distance: {src['distance']})*"
            )
