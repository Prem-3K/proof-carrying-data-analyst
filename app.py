"""Proof-Carrying Data Analyst — Streamlit UI.  Run:  streamlit run app.py"""
from __future__ import annotations

import glob
import hashlib
import html
import os

import pandas as pd
import streamlit as st

from pcda.engine import CANNOT, NOT_FOUND, NOT_FOUND_SUB, Result, analyze, suggest
from pcda.loader import cross_dataset_checks, load_dataset
from pcda.starters import starter_questions
from pcda.theme import CSS, HERO

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PLACEHOLDER = "Ask a question about your data, or type a few keywords"

st.set_page_config(page_title="Proof-Carrying Data Analyst", page_icon="🛡️", layout="wide")
import streamlit as st
from pcda.theme import apply_theme

st.set_page_config(
    page_title="Proof-Carrying Data Analyst",
    page_icon="📊",
    layout="wide"
)

# Render the refreshed CSS styles and button/search interactions
apply_theme()
st.markdown(CSS, unsafe_allow_html=True)
E = html.escape

# ----------------------------------------------------------------- state
ss = st.session_state
ss.setdefault("files", {})        # name -> bytes
ss.setdefault("query", "")
ss.setdefault("run", False)
ss.setdefault("result", None)
ss.setdefault("currency", "₹")


def set_query(q: str):
    ss["query"] = q
    ss["run"] = True


def flag_run():
    ss["run"] = True


def load_samples():
    for p in sorted(glob.glob(os.path.join(HERE, "sample_data", "*.csv"))):
        with open(p, "rb") as f:
            ss["files"][os.path.basename(p)] = f.read()


def clear_all():
    ss["files"].clear()
    ss["result"] = None
    ss["query"] = ""


@st.cache_data(show_spinner=False)
def _load(name: str, data: bytes):
    return load_dataset(name, data)


# ------------------------------------------------------------------ header
st.markdown(HERO, unsafe_allow_html=True)

with st.sidebar:
    st.header("Controls")
    st.button("Load sample datasets", on_click=load_samples, use_container_width=True)
    st.button("Clear all data", on_click=clear_all, use_container_width=True)
    ss["currency"] = st.text_input("Currency symbol (display only)", value=ss["currency"], max_chars=3)
    st.caption("Used only to format money columns whose values have no currency symbol of their own.")
    st.markdown("**Statuses**\n\n- ✅ VERIFIED — code ran and an independent check agreed\n"
                f"- ⛔ {CANNOT}\n- 🔎 {NOT_FOUND}")

# ------------------------------------------------------------------ upload
st.subheader("1 · Upload data")
up = st.file_uploader("Drop one or more CSV / XLSX files", type=["csv", "xlsx", "xlsm"], accept_multiple_files=True)
errors = []
for f in up or []:
    ss["files"][f.name] = f.getvalue()

datasets = []
for name, data in ss["files"].items():
    try:
        datasets.extend(_load(name, data))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Could not read {name}: {exc}")
for e in errors:
    st.error(e)

def get_starters(datasets):
    """Questions built from THIS data and test-run through the engine (cached per file set)."""
    sig = tuple((d.name, len(d.df), tuple(d.df.columns)) for d in datasets)
    if ss.get("starter_sig") != sig:
        ss["starter_sig"] = sig
        ss["starter_qs"] = starter_questions(datasets, limit=6, currency=ss["currency"]) if datasets else []
    return ss["starter_qs"]


starters = get_starters(datasets)

# ---------------------------------------------------------------- overview
st.subheader("2 · Dataset overview")
cross_warn, _ = cross_dataset_checks(datasets) if len(datasets) > 1 else ([], [])
if not datasets:
    st.info("No data yet. Upload a CSV/XLSX file, or click **Load sample datasets** in the sidebar.")
else:
    m = st.columns(3)
    m[0].metric("Datasets", len(datasets))
    m[1].metric("Total rows", sum(len(d.df) for d in datasets))
    m[2].metric("Quality warnings", sum(len(d.warnings) for d in datasets) + len(cross_warn))
    for d in datasets:
        pill = {"Good": "p-ok", "Fair": "p-warn", "Poor": "p-bad"}[d.quality]
        with st.expander(f"📄 {d.name} — {len(d.df)} rows × {len(d.df.columns)} columns", expanded=len(datasets) <= 2):
            st.markdown(f'Data quality: <span class="pill {pill}">{d.quality}</span>', unsafe_allow_html=True)
            info = pd.DataFrame({
                "Column": d.df.columns,
                "Type": [("date" if c in d.date_cols else "time of day" if c in d.time_cols else "ID" if c in d.id_cols else str(d.df[c].dtype)) for c in d.df.columns],
                "Missing": [int(d.df[c].isna().sum()) for c in d.df.columns],
                "Example": [str(d.raw[c].dropna().iloc[0]) if d.raw[c].notna().any() else "" for c in d.df.columns],
            })
            st.dataframe(info, hide_index=True, use_container_width=True)
            st.dataframe(d.raw.head(10).astype(str), hide_index=True, use_container_width=True)
            for w in d.warnings:
                st.warning(w)
            if d.notes:   # not an expander: Streamlit forbids expanders inside expanders
                st.markdown("**ℹ️ Data profile notes** — information, not errors")
                for note in d.notes:
                    st.markdown(f"- {note}")
    for w in cross_warn:
        st.warning(w)

# ------------------------------------------------------------------ search
st.subheader("3 · Ask or search")
placeholder = ("e.g. " + ", ".join(f"'{x}'" for x in starters[:3])) if starters else DEFAULT_PLACEHOLDER
st.text_input("Search", key="query", placeholder=placeholder, label_visibility="collapsed", on_change=flag_run)
st.caption("You can type a full question or just keywords.")

if datasets and ss["query"].strip():
    sugg = suggest(ss["query"], datasets, limit=6)
    if sugg:
        st.caption("Suggestions")
        cols = st.columns(len(sugg))
        for i, s in enumerate(sugg):
            cols[i].button(s["label"], key=f"sg{i}_{s['query']}", on_click=set_query, args=(s["query"],), use_container_width=True)

if not ss["query"].strip() and datasets and starters:
    st.caption("Try (generated from your file's own columns and values, each one test-run before being shown):")
    cols = st.columns(len(starters))
    for i, qx in enumerate(starters):
        cols[i].button(qx, key=f"ex{i}", on_click=set_query, args=(qx,), use_container_width=True)

go = st.button("🔍 Analyze", type="primary")
if go or ss["run"]:
    ss["run"] = False
    if not datasets:
        st.warning("Upload a dataset first.")
    elif not ss["query"].strip():
        st.warning("Type a question or some keywords first.")
    else:
        with st.status("Analyzing…", expanded=True) as status:
            st.write("🔎 Inspecting datasets and matching your words to columns and values")
            res: Result = analyze(ss["query"], datasets, ss["currency"])
            for s in res.steps[1:]:
                st.write("• " + s)
            status.update(label={"answer": "Analysis complete", "suggest": "Possible typo found", "clarify": "Need a little more detail",
                                 "ask_target": "Match found — what do you want to know?", "not_found": "Data not found",
                                 "cannot": "Cannot reliably determine"}[res.kind], state="complete")
        ss["result"] = res

# ----------------------------------------------------------------- results
def option_buttons(options, prefix):
    if not options:
        return
    per_row = 4
    for r0 in range(0, len(options), per_row):
        chunk = options[r0:r0 + per_row]
        cols = st.columns(per_row)
        for i, o in enumerate(chunk):
            cols[i].button(o["label"], key=f"{prefix}_{r0 + i}_{o['query']}", on_click=set_query, args=(o["query"],), use_container_width=True)


def records_table(recs, title="SOURCE RECORD"):
    if recs:
        st.markdown(f'<div class="lbl">{title}{"S" if len(recs) > 1 else ""}</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(recs), hide_index=True, use_container_width=True)


def agent_panel(res: Result):
    if not res.trace:
        return
    with st.expander("🧠 Agent reasoning — how this answer was reached", expanded=True):
        done = res.kind == "answer" and bool(res.verification_passed)
        for i, t in enumerate(res.trace):
            items = "".join(f"<li>{E(l).replace('**', '')}</li>" for l in t["lines"])
            end = " end" if (done and i == len(res.trace) - 1) else ""
            st.markdown(f'<div class="ag{end}" style="--i:{i}"><b class="s">{E(t["step"])}</b><ul>{items}</ul></div>', unsafe_allow_html=True)
        st.caption("Rule-based and deterministic: the same question on the same data always gives the same reasoning and answer.")


def can_answer_instead():
    if starters:
        st.markdown("**Here is what I can answer from this file:**")
        cols = st.columns(len(starters))
        for i, qx in enumerate(starters):
            cols[i].button(qx, key=f"alt{i}_{qx}", on_click=set_query, args=(qx,), use_container_width=True)


def render(res: Result):
    st.subheader("4 · Result")
    if res.kind == "not_found":
        st.markdown(f'<div class="card bad"><span class="stamp bad-s">NOT IN THE DATA</span><div class="nf">{NOT_FOUND}</div><p>{E(NOT_FOUND_SUB)}</p></div>', unsafe_allow_html=True)
        if res.reasons:
            st.markdown("**Reason**")
            for r in res.reasons:
                st.markdown(f"- {r}")
        can_answer_instead()
    elif res.kind == "cannot":
        st.markdown(f'<div class="card warn"><span class="stamp warn-s">WITHHELD</span><div class="nf" style="color:#FFB547">{CANNOT}</div><p>{E(res.message)}</p></div>', unsafe_allow_html=True)
        for r in res.reasons:
            st.markdown(f"- {r}")
    elif res.kind == "answer":
        lines = "".join(f'<div class="lbl">{E(l)}</div><div class="big">{E(v)}</div>' for l, v in res.answer_lines)
        st.markdown(f'<div class="card ok"><span class="stamp ok-s">✓ VERIFIED</span><h3>{E(res.headline)}</h3>{lines}<p class="small">{E(res.message)}</p></div>', unsafe_allow_html=True)
        if res.group_table:
            st.dataframe(pd.DataFrame(res.group_table), hide_index=True, use_container_width=True)
        if res.n_matches > 1 and res.source_records:
            st.caption(f"{res.n_matches} matching records (showing up to 25)")
        records_table(res.source_records)
        v = "".join(f"<div>{E(c)}</div>" for c in res.verification_checks)
        st.markdown(f'<div class="card info"><h3>Verification</h3>'
                    f'<div>✓ Code executed successfully</div>{v}</div>', unsafe_allow_html=True)
    elif res.kind == "suggest":
        st.markdown(f'<div class="card warn"><span class="stamp warn-s">DID YOU MEAN?</span><h3>{E(res.headline)}</h3><p>{E(res.message).replace(chr(10), "<br>")}</p></div>', unsafe_allow_html=True)
        pv = res.preview
        if pv and pv.kind in ("answer", "ask_target", "clarify") and pv.source_records:
            st.markdown("**Matching record found**")
            records_table(pv.source_records[:5])
            if pv.kind == "answer":
                st.caption("Preview only — click the button below to confirm the correction and get the verified answer.")
        option_buttons(res.options, "fix")
    elif res.kind == "clarify":
        st.markdown(f'<div class="card info"><span class="stamp info-s">YOUR CALL</span><h3>{E(res.headline)}</h3><p>{E(res.message)}</p></div>', unsafe_allow_html=True)
        records_table(res.source_records)
        option_buttons(res.options, "cl")
    elif res.kind == "ask_target":
        st.markdown(f'<div class="card info"><span class="stamp info-s">YOUR CALL</span><h3>{E(res.headline)}</h3><p>{E(res.message)}</p></div>', unsafe_allow_html=True)
        records_table(res.source_records)
        option_buttons(res.options, "tg")

    agent_panel(res)

    # ---------------- trust report
    st.subheader("5 · Trust Report")
    ran = res.code_executed
    ver = "Yes" if res.verification_passed else ("No" if res.verification_passed is False else "N/A (no calculation)")
    cls = {"VERIFIED": "p-ok"}.get(res.overall, "p-bad" if res.overall in (NOT_FOUND, "CANNOT RELIABLY DETERMINE") else "p-info")
    warns = res.warnings
    assum = res.assumptions
    def tile(k, v, extra=""):
        return f'<div class="tile{extra}"><div class="k">{E(k)}</div><div class="v">{v}</div></div>'
    st.markdown('<div class="tiles">'
                + tile("Dataset", E(res.dataset or "—"))
                + tile("Data quality", E(res.data_quality))
                + tile("Warnings", str(len(warns)))
                + tile("Assumptions", "<br>".join(E(a) for a in assum) if assum else "None")
                + tile("Code executed", "Yes" if ran else "No")
                + tile("Verification passed", ver)
                + tile("Overall status", f'<span class="pill {cls}">{E(res.overall)}</span>', " final" if res.overall == "VERIFIED" else "")
                + '</div>', unsafe_allow_html=True)
    if res.interpretation and res.kind != "not_found":
        with st.expander("How the question was interpreted"):
            st.json(res.interpretation)

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Generated Python code**")
        if res.code:
            st.code(res.code, language="python")
            st.caption("Copy into a file next to your data and run it — it reproduces the answer.")
        else:
            st.info("No code was generated because no calculation was performed.")
    with c2:
        st.markdown("**Warnings & errors**")
        if res.exec_error:
            st.error(res.exec_error)
        if not warns and not res.exec_error:
            st.success("No warnings.")
        for w in warns:
            st.warning(w)


if ss["result"] is not None:
    render(ss["result"])
