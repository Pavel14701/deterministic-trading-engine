# TZ-14. Null stage: typing, linters, test hygiene, language discipline

> **Status: ✅ done — EN-only, ruff clean, mypy clean, tests green.**
> Wave 1: ruff as the single linter, root pytest config, service markers, tests "next to src",
> pandas/pandas_ta removed, warnings 1886 → 0.
> Wave 2: setup.cfg + flake8/isort eliminated; mypy `risk` strict (0); markers
> unit=241/integration=30/slow=4/deprecated=69.
> Wave 3: mypy infer → 0 (was 15); parametrize wma/hilo/midprice/midpoint.
> Wave 4: 0 Cyrillic / 0 non-ASCII in .py (127 lines, 141 files); E701 (120); B905 (40);
> RUF069 (70 noqa IEEE); F841/RUF046/RUF029 closed.
> Wave 5: E501 (73 → 0); D* docstrings (89); E741 (32); RUF059 (72); B017/B028/RUF007/RUF043/
> RUF012 (10). Ruff: 4146 → 0.
> Wave 6: mypy ai strict → 0 (was 3: Subset cast + None-union + assert); ta atrs ma_mode union →
> assert. Tests excluded from mypy (covered by pytest). Total mypy workspace: 0 errors.
> Remaining: CI TZ-13 (ruff+mypy+pytest matrix).

## 1. Context

The project was consolidated into a monorepo (TZ-00 §1.1), but code-base quality is uneven: mypy is
formally wired (`ignore_missing_imports`, no strictness), linters have a **dual configuration**
(ruff in `pyproject.toml` + flake8 in `setup.cfg` with diverging ignores), tests are a zoo: three
different `conftest.py` files with different fixtures, five `pytest.ini` with different
`addopts`/markers, varying import styles and test naming. All of this blocks TZ-02+ refactoring:
edits without typing and ordered tests cannot be safely verified.

## 2. Requirements

### 2.1. Unified language standard (blocker)

1. **Code, identifiers, docstrings, comments — English only.** Russian stays in docs (`*.md`) and
   UI/CLI user messages. The strictness motivation: Numba/LLVM and part of the toolchain silently
   degrade or crash on non-ASCII characters in sources — Cyrillic must never appear in `.py`.
2. Autofix: existing code checked — no Cyrillic in `.py`; pin it with a ruff rule
   (e.g. `RUF002/003/004` — ambiguous-unicode) in blocking mode.
3. CI gate: a grep invariant `[А-Яа-яЁё]` in `*.py` = fail (TZ-13 job).

### 2.2. Unified linter configuration

1. **Ruff is the single source of truth**; `setup.cfg` (flake8, isort, pycodestyle) is eliminated,
   flake8 deps removed from the dev group. Ruff rules widened: `E,F,Q,D,N` + `RUF002-004`
   (language) + `I` (isort replacement), `B` (bugbear).
2. mypy in stages (not "strict everything at once"): `ai` and `infer` strict first (critical
   modules), then `dsl`, then `ta`/`strategies`/`rag`/`main`. A module's lag is recorded in
   `pyproject.toml` (`[tool.mypy.<module>]`) with a planned catch-up date — "endless deferral"
   is forbidden.
3. Formatting: `ruff format` instead of isort/black; the `isort` dep is removed.

### 2.3. Test hygiene

1. Test convention: `dev_docs/testing_convention.md` (mandatory reading before touching any test).
   Existing tests are brought into line.
2. One `pytest.ini` template for all workspace members (same `addopts`, `--strict-markers`, marker
   set); only `testpaths` differs.
3. Consolidate `conftest.py`: fixtures duplicated between packages (synthetic OHLC series, mock DSL
   providers) move to a shared location, per-package `conftest.py` keeps only its own, duplicates
   removed.
4. Classify ~2200 existing tests with markers (`unit`, `integration`, `slow`, `deprecated`) —
   deprecated are marked, not removed.
5. Forbidden: tests without asserts (smoke-check via `pass`), sleep tests, network dependence
   (except `integration`-marked, skipif without a token).

### 2.4. Package verification

- `uv run --package dte-<x> pytest <tests>` — green;
- `ruff check` + `ruff format --check` — clean;
- `mypy <module>` — per the §2.2 agreed mode.

## 3. Acceptance criteria

- `setup.cfg` removed, the ruff config widened and applied to all packages.
- mypy: ai/infer strict, the rest — at least `disallow_untyped_defs` for public API
  (docstrings + annotations).
- All `pytest.ini` unified; markers classified; a classification report
  (how many unit/integration/slow/deprecated) attached to the PR.
- Cyrillic impossible in `.py`: the CI (TZ-13) check green.
- Full run: ~2200 tests green without semantic changes.