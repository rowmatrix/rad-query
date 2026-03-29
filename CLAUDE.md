# CLAUDE.md — RadQuery Agent Guidance

This file defines how Claude Code should operate on this repository.
**Read it in full at the start of every session before touching any code.**

---

## PROJECT CONTEXT

RadQuery is a RAG pipeline over public radiation test report corpora.
It answers natural-language queries about EEE part radiation tolerance
with cited, domain-aware answers.

**The domain is safety-relevant.** Radiation test data informs flight
hardware qualification decisions. Wrong answers or missing caveats can
have mission-critical consequences. Accuracy and conservative reasoning
outweigh brevity or cleverness at every tradeoff.

### Read TECHNICAL_SPEC.md First

Before implementing anything in `rad_rag/`, read `TECHNICAL_SPEC.md`
(gitignored, local only). It is the authoritative source for:
- Module contracts and function signatures
- Chunk and metadata schemas
- The five domain caveat rules
- Environment variable definitions

If `TECHNICAL_SPEC.md` is absent, **stop and ask the user** before proceeding.
Do not infer contracts from the code alone.

---

## WORKFLOW

### 1. Plan Before Any Non-Trivial Change

For ANY task involving 3+ file changes, a new module, or an architectural
decision: write a plan first. Do not write implementation code until
the plan is approved by the user.

Write the plan to `tasks/todo.md` using this format:

```
## Task: <title>
**Status**: In Progress

### Objective
<one paragraph: what problem this solves and why>

### Files Affected
- `path/to/file.py` — what changes and why

### Step-by-Step Approach
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

### Tests That Will Prove Correctness
<list the specific assertions or behaviors the tests will verify>

### Risks / Side Effects
<what could go wrong; what adjacent code might be affected>
```

After writing the plan, check in with the user. Wait for explicit approval
before writing a single line of implementation code.

### 2. Test-Driven Development (TDD) — Non-Negotiable for rad_rag/

For any new logic in `rad_rag/`:

1. **Write the failing test first.** The test must encode the behavior
   described in `TECHNICAL_SPEC.md`, not inferred from existing code.
2. **Run the test suite** to confirm the new test fails for the right reason.
3. **Implement** the minimum code to make the test pass.
4. **Run the full suite** — all tests must pass before proceeding.

```bash
# Confirm new test fails before implementation
pytest tests/ -v -k "<new_test_name>"

# Confirm no regressions after implementation
pytest tests/ -v
```

TDD is required (not optional) for:
- Any logic in `domain_caveats.py`
- Any change to metadata extraction in `chunker.py`
- Any new retrieval or filtering logic in `retriever.py`

For glue code, CLI scripts, and UI changes, test-alongside is acceptable.

### 3. Verification Standard — Never Self-Certify Without Evidence

Never mark a task complete without running the test suite and showing
output to the user. Before calling anything done, run this checklist
mentally:

- [ ] `pytest tests/ -v` passes with zero failures
- [ ] New behavior is covered by at least one test added this session
- [ ] `TECHNICAL_SPEC.md` contracts are respected (check field names,
      return types, and function signatures explicitly)
- [ ] No hardcoded paths, keys, model names, or magic numbers
- [ ] No `print()` statements in any `rad_rag/` module
- [ ] New env vars (if any) are added to `.env.example` with a comment

Ask yourself: *"Would a staff engineer approve this PR?"*
If the honest answer is "maybe not," fix it before presenting it.

### 4. Self-Correction Loop

After any correction from the user, immediately add the pattern to
`tasks/lessons.md` using this format:

```
## Lesson: <short title>
**Date**: YYYY-MM-DD
**Mistake**: <what went wrong>
**Fix**: <what the correct approach is>
**Rule**: <one-line rule to prevent recurrence>
```

Review `tasks/lessons.md` at the start of every session. If a lesson
is relevant to the current task, note it in the plan.

### 5. Autonomous Bug Fixing

When given a bug report, a failing test, or a log error: fix it.
Do not ask for step-by-step guidance. Point at the evidence, trace
the root cause, implement the fix, prove it works.

The one exception: if the fix requires changing the schema defined in
`TECHNICAL_SPEC.md`, stop and flag it. Schema changes are human decisions.

---

## ARCHITECTURE RULES

### Module Ownership — Hard Boundaries

Each module has exactly one responsibility. Do not let concerns bleed
across boundaries. If a change causes a module to reach across this
table, stop and redesign.

| Module | Owns | Must Not |
|---|---|---|
| `ingest.py` | PDF → page dicts | Know about chunks, embeddings, or domain logic |
| `chunker.py` | Page dicts → chunk dicts + metadata extraction | Call any LLM except for `part_type` classification |
| `embedder.py` | Chunks → ChromaDB | Contain domain logic or caveat rules |
| `retriever.py` | Query → cited answer (LLM orchestration) | Contain radiation physics logic |
| `domain_caveats.py` | Radiation domain caveat rules | Perform retrieval or call ChromaDB |
| `app.py` | Streamlit UI | Contain business logic beyond calling `retriever.answer()` |

### domain_caveats.py — Implement the Spec Exactly

The five caveat rules are defined in `TECHNICAL_SPEC.md`. Implement
exactly those rules. The confidence tier system (HIGH / MEDIUM / LOW)
is specified there. Do not invent new rules or modify rule logic without
explicit user approval — but autonomous implementation and refactoring
of the *specified* rules is expected.

### Metadata Schema — Spec Is Authoritative

Chunk metadata fields must match the schema in `TECHNICAL_SPEC.md`
exactly — field names, types, and allowed values. Do not add, remove,
or rename fields without updating the spec and getting user approval first.

### Environment Variables — No Hardcoding

All configuration via env vars defined in `.env.example`. If you need
a new tunable, add it to `.env.example` with a comment before using it.
Never hardcode model names, directory paths, or numeric thresholds.

### LLM Usage Within rad_rag/

Only two modules may call an LLM:
- `chunker.py` — Claude Haiku for `part_type` classification only
- `retriever.py` — configured backend for answer synthesis

All other modules must be LLM-free and deterministic.

---

## CODING STYLE

- **Python 3.11+.** Type hints on all public functions and return values.
- **Docstrings** on every public function: Args, Returns, Raises.
- **`logging` not `print`.** Use `logger = logging.getLogger(__name__)`.
  Log at INFO for normal operations, DEBUG for internals, ERROR for failures.
- **Imports**: stdlib → third-party → local, separated by blank lines.
- **Comments**: explain *why*, never *what*. The code says what; the comment
  says why this approach was chosen over the alternative.
- **Function length**: under 40 lines. Extract helpers aggressively.
- **No temporary fixes.** Find root causes. If a real fix is too large for
  this task, flag it and document it — don't paper over it.

---

## WHAT NOT TO DO

- Do not modify `TECHNICAL_SPEC.md` — it is a human-maintained document.
- Do not commit `.env` or any file containing API keys or secrets.
- Do not add dependencies to `requirements.txt` without stating why in
  the plan and in a code comment at the import site.
- Do not use `print()` in any `rad_rag/` module.
- Do not run `scripts/fetch_corpus.py` autonomously — it makes network
  requests to rate-limited external sources.
- Do not speculate about radiation physics domain knowledge. If the
  spec is ambiguous, surface the ambiguity to the user. The cost of a
  missing caveat is higher than the cost of asking a question.
- Do not invent caveat rules not present in `TECHNICAL_SPEC.md`.

---

## COMMIT DISCIPLINE

Commits must be small and atomic — one logical change per commit.
The user should be able to `git revert` any single commit cleanly.

Commit message format:
```
<module>: <what changed and why in one line>

Optional longer body if the why needs more explanation.
```

Examples:
```
domain_caveats: implement ELDRS flag rule per TECHNICAL_SPEC §4.1
chunker: improve dose_rate regex to capture gsfc_test table context
retriever: add local backend fallback for test environments
```

Do not bundle unrelated changes in one commit. If you find yourself
writing "and also" in the commit message, split the commit.

---

## TASK TRACKING

| File | Purpose |
|---|---|
| `tasks/todo.md` | Active task plan with checkable items. One task at a time. |
| `tasks/lessons.md` | Running log of corrections and rules learned this project. |

Both files are committed to the repo. They are part of the project record,
not throwaway scratch space. Write them as if a future engineer will read them.

---

## SESSION START CHECKLIST

Run through this at the start of every session, before any planning or coding:

1. Read this file (`CLAUDE.md`) in full.
2. Read `TECHNICAL_SPEC.md` — note any contracts relevant to today's task.
3. Read `tasks/lessons.md` — flag any lessons that apply to today's work.
4. Read `tasks/todo.md` — understand current state and any open items.
5. Confirm the task scope with the user before proceeding.
