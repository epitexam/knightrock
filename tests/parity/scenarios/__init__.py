"""Scripted scenarios shared by the parity runner.

All scenarios are art-free: they build a programmatic level and set every
entity's animator to ``None``. They therefore run on a bare checkout (CI),
unlike the visual goldens which are gated by ``requires_assets``.
"""
