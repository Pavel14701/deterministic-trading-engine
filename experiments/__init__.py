"""Reproducible experiments (moved out of ``scripts/``).

Track packages: ``loaders``, ``carry``, ``avsl``, ``ob``, ``panel``.
Each module is runnable: ``python -m experiments.<track>.<name>``.
Every experiment pins its data variant, encoding and metrics; results
land in ``runs/`` and are logged in ``STATUS.md``.

Repo root, shared by every module (import from here so modules stay
depth-independent): ``from experiments import REPO``.
"""

from experiments._repo import REPO  # noqa: F401

