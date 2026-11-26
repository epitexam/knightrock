"""Shared kernel: types and ports every layer may use, depending on nothing.

A module belongs here only if it has no dependency on the other packages.
The old import paths remain as re-export shims during the migration (ADR 0001).
"""
