# Proof-Carrying Data Analyst
*Every answer comes with executable proof.*

```bash
pip install -r requirements.txt
streamlit run app.py          # click "Load sample datasets" in the sidebar
python -m unittest discover -s tests -v   # 48 tests; also works with pytest
```

## How it works
1. **Upload** CSV / XLSX (each sheet becomes a dataset). Currency text (`₹8.50`, `$1,200`) is cleaned to numbers.
2. **Data-quality checks**: missing values, duplicate rows/IDs, invalid + ambiguous dates, mixed currencies, contradictory values across files.
3. **Schema-aware search bar**: words are mapped to columns / values from the *uploaded* data (no hard-coded schema). Every row is treated as one connected record: `Product == Notebook AND Region == North` must hold on the same row.
4. **Fuzzy matching** (typos, `desklamp`, `o1004`, `1004`, plural/singular). Typos are *suggested* with a "Use X" button, never silently applied.
5. **Pandas code** is generated from templates, executed, then **re-computed independently** with plain-Python loops. Only if both agree is the answer shown as `VERIFIED`.
6. Missing info → `DATA NOT FOUND IN THE PROVIDED DOCUMENT` with a reason. Unreliable data → `CANNOT RELIABLY DETERMINE FROM THE PROVIDED DATA`.

No LLM or API key is used: query understanding is deterministic, so results are reproducible.

## The agent loop (what happens on every question)
`Understand → Plan → Act → Verify → Decide`, shown in the **Agent reasoning** panel under each result.
1. **Understand**: map the words to this file's columns/values (and say which words matched what).
2. **Plan**: state the filter / group / aggregate it will run.
3. **Act**: generate Pandas code from a template and execute it on the original data.
4. **Verify**: recompute with independent plain-Python loops; any disagreement withholds the answer.
5. **Decide**: answer (VERIFIED), ask (ambiguous / typo), or refuse (NOT FOUND / CANNOT RELIABLY DETERMINE).

The panel is built from what the engine actually did for that question, not from a canned story.
It is an agent in the plan-act-verify sense; it is rule-based, not an LLM. That is a deliberate choice:
an LLM can invent numbers, this cannot.

## Interface
Dark theme with a verification seal that locks in on load, a verdict stamp on every result (VERIFIED / NOT IN THE DATA / WITHHELD / YOUR CALL), an agent-reasoning timeline, and Trust Report tiles. Pure CSS (`pcda/theme.py`), no JavaScript, and animations switch off when the system asks for reduced motion.

## Data-profile behaviour (no false alarms)
- Clock times (`07:00`, `9:30 PM`) are recognised as **times of day**, not calendar dates, so they are never reported as "invalid dates".
- Timestamps (`2026-09-01 10:30:00`) are read as dates.
- A column that is **mostly empty** (50%+ of rows) is shown as an information note, not an error. It becomes a warning only on an answer that actually uses that column.
- Genuine problems are still reported: invalid/ambiguous dates, duplicate rows/IDs, mixed currencies, contradictions between files, and small tables with missing values.
- The "Try" buttons and search hint are **generated from the uploaded file** and each is test-run through the engine before it is shown, so a suggestion never ends in "not found".

## Known limits
- Understands lookups, filters, date (ISO / "Sept 4"), total/average/count/min/max, and "by <column>". Not joins, "over 100"-style comparisons or multi-step questions (these return DATA NOT FOUND rather than a guess).
- Autocomplete updates when you press Enter / click Analyze (Streamlit text boxes don't emit per-keystroke events).
- Multi-dataset joins are not performed; conflicts between files are detected via a shared ID column.
