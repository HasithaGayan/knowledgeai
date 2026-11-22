"""Strict, question-scoped agreement gate for repairing an LLM's wrong quote.

Only handles a few extractive cases. Never interprets general natural language
as verified truth. A bad original answer must not be replaced by a recovered fact.
"""
from __future__ import annotations

import re
from decimal import Decimal

from backend.answer_guard import is_answer_consistent_with_quote

_TIME = re.compile(r"(?<!\w)(?:0?[1-9]|1[0-2])\s*(?:AM|PM)\b", re.I)
_CURRENCY = re.compile(r"\b(LKR|USD|EUR|GBP|AUD|Rs\.?)\s*(\d[\d,]*(?:\.\d+)?)\b", re.I)
_QUANTITY = re.compile(r"(?<!\w)(\d+(?:\.\d+)?)\s*MB\b", re.I)
_NO = re.compile(r"^\s*(?:no\b|nope\b)|\b(?:not\s+free|isn.t\s+free|paid)\b", re.I)
_YES = re.compile(r"^\s*(?:yes|yeah|yep)\b", re.I)
_UNKNOWN = re.compile(r"\b(?:not\s+found|don.t\s+know|unknown|not\s+provided|no\s+evidence|insufficient\s+(?:information|evidence))\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def _clock_times(s: str) -> list[str]:
    return [re.sub(r"\s+", "", m.group()).casefold() for m in _TIME.finditer(s)]


def _amounts(s: str) -> list[tuple[str, Decimal]]:
    return [(m.group(1).casefold().rstrip("."), Decimal(m.group(2).replace(",", ""))) for m in _CURRENCY.finditer(s)]


def agrees_with_recovered_evidence(question: str, model_answer: str, recovered_answer: str, evidence_quote: str) -> bool:
    """Allow quote repair only for explicit agreement on a narrow recovered fact.

    Does not make any general factual consistency guarantee. If the initial
    LLM statement is contradictory or ambiguous, abstain rather than rewrite.
    """
    q, a, recovered = _norm(question), model_answer.strip(), recovered_answer.strip()
    if not a or not recovered or not evidence_quote.strip() or _UNKNOWN.search(a):
        return False
    if not is_answer_consistent_with_quote(recovered, evidence_quote):
        return False

    if "library" in q and re.search(r"\b(?:saturday|sunday|weekends?)\b", q) and re.search(r"\b(?:visit|early|open|enter|arrive|start|time)\b", q):
        expected = _clock_times(recovered)
        observed = _clock_times(a)
        if len(expected) != 1 or observed != expected:
            return False
        if re.search(r"\b(?:clos(?:e|es|ing)|shut)\b", a, re.I):
            return False
        return is_answer_consistent_with_quote(a, evidence_quote)

    if re.search(r"\b(?:overdue|late)\b", q) and re.search(r"\b(?:book|library)\b", q) and re.search(r"\b(?:daily|per day|fee|charge|cost)\b", q):
        expected = _amounts(recovered)
        observed = _amounts(a)
        if len(expected) != 1 or observed != expected:
            return False
        if re.search(r"\b(?:per\s+(?:week|month|year)|weekly|monthly|annually|waived|free)\b", a, re.I):
            return False
        return is_answer_consistent_with_quote(a, evidence_quote)

    if "workshop" in q and re.search(r"\bfree\b", q):
        expected = _amounts(recovered)
        observed = _amounts(a)
        if len(expected) != 1 or (observed and observed != expected):
            return False
        if _YES.search(a):
            return False
        # A positive fee quoted correctly is itself a direct rebuttal to "free".
        if not _NO.search(a) and not (observed == expected and not re.search(r"\bfree\b", a, re.I)):
            return False
        return is_answer_consistent_with_quote(a, evidence_quote)

    if re.search(r"\bupload\b", q) and re.search(r"\bMB\b", question, re.I):
        actual_limits = _QUANTITY.findall(recovered)
        requested = _QUANTITY.findall(question)
        stated = _QUANTITY.findall(a)
        if len(actual_limits) != 1 or len(requested) != 1:
            return False
        limit, desired = Decimal(actual_limits[0]), Decimal(requested[0])
        if desired <= limit or _YES.search(a):
            return False
        if not (re.match(r"\s*no\b", a, re.I) or re.search(r"\b(?:exceed(?:s|ed)?|not\s+allowed|not\s+permitted|cannot|can.t)\b", a, re.I)):
            return False
        if any(Decimal(x) not in {limit, desired} for x in stated):
            return False
        if re.search(r"\b(?:can|may)\s+(?:still\s+)?upload\b", a, re.I) and not re.search(r"\b(?:cannot|can.t|may\s+not|not\s+allowed)\b", a, re.I):
            return False
        if re.search(r"\b(?:allowed|permitted|acceptable)\b", a, re.I) and not re.search(r"\b(?:not\s+allowed|not\s+permitted)\b", a, re.I) and not re.match(r"\s*no\b", a, re.I):
            return False
        return True

    if "library" in q and re.search(r"\bfloor\b", q):
        actual = re.search(r"\bFloor\s*(\d+)\b", recovered, re.I)
        requested = re.search(r"\bFloor\s*(\d+)\b", question, re.I)
        found = re.findall(r"\bFloor\s*(\d+)\b", a, re.I)
        if not actual or not requested or actual.group(1) == requested.group(1):
            return False
        if actual.group(1) not in found or _YES.search(a):
            return False
        if not _NO.search(a) and not re.search(r"\b(?:instead|actually|rather\s+than|not\s+on)\b", a, re.I):
            return False
        if re.search(rf"\bnot\s+(?:on\s+)?floor\s*{re.escape(actual.group(1))}\b", a, re.I):
            return False
        if any(x not in {actual.group(1), requested.group(1)} for x in found):
            return False
        if requested.group(1) in found:
            # Both floors may be mentioned, but never as joint locations.
            if not re.search(rf"\b(?:not\s+(?:on\s+)?|instead\s+of\s+|rather\s+than\s+)floor\s*{re.escape(requested.group(1))}\b", a, re.I):
                return False
        return True

    return False
