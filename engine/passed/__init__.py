# -*- coding: utf-8 -*-
"""Passed strategies -- configurations that cleared their full
pre-registered battery and are frozen as production references.

One module per strategy, each self-contained (no experiments/
imports) and pinned to its STATUS.md verdict.  A module's frozen
numbers are a regression contract: any code change here that moves
them voids the PASS.
"""

from engine.passed.avsl_cross_s1 import evaluate, main


__all__ = ["evaluate", "main"]
