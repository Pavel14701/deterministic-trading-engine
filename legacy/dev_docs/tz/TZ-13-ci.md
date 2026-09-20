# TZ-13. CI (GitHub Actions)

> **Status: ✅ done** (`.github/workflows/ci.yml`: lint job (ruff + format), mypy job
> (risk/infer/ai strict), EN-only guard job, 9 pytest matrix jobs per package — main added).

## 1. Context

~2200 tests and linters exist but do not run automatically. A monorepo regression (e.g. a broken
workspace-member import) is not caught.

## 2. Requirements

1. `.github/workflows/ci.yml`: push/PR on dev/main.
2. Jobs:
   - `lint`: ruff check + ruff format --check (root).
   - `test-matrix`: a matrix over workspace members — ta, dsl, ai, infer, rag, strategies, main:
     `uv sync --package dte-<x>` → `uv run --package dte-<x> pytest <tests>`.
     ai — with a pip/uv cache for torch (or exclude the `slow` marker in CI).
3. mypy: a separate job (currently non-blocking — `continue-on-error: true` until tightened).
4. Python 3.12, ubuntu-latest; ta-lib via apt (`libta-lib`) or a wheel.

## 3. Acceptance criteria

- A green run on an empty PR without manual steps; CI time < 15 min.
- A red CI blocks merges (branch protection — configured manually on GitHub).