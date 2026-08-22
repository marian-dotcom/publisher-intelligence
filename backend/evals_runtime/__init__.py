"""Replaceable Inspect AI eval runtime (ADR-129).

This package is the ONLY place allowed to import inspect_ai. Publisher
Intelligence app code must never import it; a boundary test enforces this.
EVALS.md remains the contract for corpus, gold, scorers semantics, hard-fail,
holdout and release decisions.
"""
