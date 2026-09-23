# -*- coding: utf-8 -*-
"""AVSL live-scale pilot infrastructure (STATUS prereg 2026-09-22).

``parity_check`` -- the PARITY hard gate (g1); ``pilot_tracker`` --
Phase A paper-forward bookkeeping, read-outs r1-r4, disaster brake.
Both import the frozen module ``engine.passed.avsl_cross_s1`` and
must never modify it.  Operations runbook: README.md in this dir.
"""
