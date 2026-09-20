"""Reproducible experiments (moved out of ``scripts/``).

Each module is runnable: ``python -m engine.experiments.<name>``.
Every experiment pins its data variant, encoding and metrics; results
land in ``runs/`` and are logged in ``STATUS.md``.
"""
