"""Conservative, partial checks for direct contradictions with cited evidence.

This is NOT semantic entailment or a guarantee of factual correctness.
"""
from __future__ import annotations

from decimal import Decimal
import re

_NUMBERS = re.compile(r"(?<![\w])\d[\d,]*(?:\.\d+)?(?![\w])")
_MONEY = re.compile(r"(?:\b(?:lkr|usd|eur|rs\.?|gbp|aud)\s*|\$\s*)(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
_FREE = re.compile(r"\bfree\b", re.IGNORECASE)
_FREE_CLAIMS = re.compile(r"\b(?:no\s+(?:registration\s+)?(?:fee|charge)|costs?\s+nothing|zero\s+(?:fee|charge|cost))\b", re.IGNORECASE)
_NEGATED = re.compile(r"\b(?:not|isn't|wasn't|aren't|never)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)


def _values(pattern: re.Pattern, text: str) -> set[Decimal]:
    return {Decimal(m.group(1) if m.lastindex else m.group().replace(',', ''))
            for m in pattern.finditer(text.replace(',', ''))}


def is_answer_consistent_with_quote(answer: str, quote: str) -> bool:
    """Fail closed for unsupported numbers and explicitly free-vs-paid claims.

    Other semantic contradictions may still pass: this is only one guardrail.
    """
    if not answer.strip() or not quote.strip():
        return False

    # Any numerical fact asserted in the answer must be present in its cited quote.
    if not _values(_NUMBERS, answer).issubset(_values(_NUMBERS, quote)):
        return False

    # A currency amount in the answer must be evidenced in the quoted text.
    answer_money = _values(_MONEY, answer)
    if answer_money and not answer_money.issubset(_values(_MONEY, quote)):
        return False

    # A positive quoted fee directly contradicts an assertion that the item is free.
    price_evidence = bool(re.search(r"\b(?:fee|cost|price|charge)\b", quote, re.I)) and any(
        amt > 0 for amt in _values(_MONEY, quote)
    )
    if price_evidence:
        if _FREE_CLAIMS.search(answer):
            return False
        for match in _FREE.finditer(answer):
            preceding = answer[max(0, match.start() - 35):match.start()]
            if not _NEGATED.search(preceding):
                return False
    return True
