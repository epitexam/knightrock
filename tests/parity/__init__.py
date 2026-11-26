"""Temporary parity suite for the parallel modularisation migration.

Every scenario in this package can be run against the legacy implementation
and against the candidate implementation. The runner compares canonical
digests; the legacy result is always the control. This package is removed
once the candidate becomes the reference implementation (ADR 0001).
"""
