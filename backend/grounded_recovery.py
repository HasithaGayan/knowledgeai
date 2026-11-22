"""Narrow extractive recovery for common supported document Q&A questions.

This is intentionally NOT a universal NLI / fact-checker. It only recovers a
small number of directly written, machine-verifiable facts, and returns a
literal quote. Ambiguous/conflicting matches fail closed.
"""
from __future__ import annotations

from decimal import Decimal
import re
from typing import Any

from backend.answer_guard import is_answer_consistent_with_quote

_PRICE = r"(?:LKR|USD|EUR|GBP|AUD|Rs\.?)\s*\d[\d,]*(?:\.\d+)?"
_TIME = r"(?:0?[1-9]|1[0-2])\s*(?:AM|PM)"


def _matches(q: str, words: str) -> bool:
    return bool(re.search(words, q, flags=re.IGNORECASE))


def _candidate(question: str, line: str) -> str | None:
    """Return only a direct, well-scoped answer literal to this source line."""
    q = question.strip()
    # Saturday and Sunday are weekends; don't infer other opening hours.
    if (_matches(q, r"\blibrary\b")
            and _matches(q, r"\b(?:saturday|sunday|weekends?)\b")
            and _matches(q, r"\b(?:visit|enter|open|early|time|start|arrive)\b")):
        m = re.search(rf"\bon\s+weekends?\b.*\blibrary\s+opens?\s+at\s+(?P<time>{_TIME})\b", line, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group("time")).strip()

    if (_matches(q, r"\b(?:overdue|late)\b")
            and _matches(q, r"\b(?:book|library)\b")
            and _matches(q, r"\b(?:daily|per\s+day|fee|charge|cost)\b")):
        m = re.search(rf"\b(?:overdue|late)\s+(?:fee|charge)\s+is\s+(?P<price>{_PRICE})\s+per\s+day\b", line, re.I)
        if m:
            return f"{m.group('price')} per day"

    if _matches(q, r"\bfree\b") and _matches(q, r"\bworkshop\b"):
        m = re.search(rf"\b(?:AI\s+)?workshop\s+fee\s+is\s+(?P<price>{_PRICE})\b", line, re.I)
        if m and Decimal(re.search(r"\d[\d,]*(?:\.\d+)?", m.group("price")).group().replace(",", "")) > 0:
            return f"No. The workshop fee is {m.group('price')}."

    # Only reject a requested upload when the stated quantity exceeds the
    # documented numeric maximum. Within-limit does not imply permission.
    if (_matches(q, r"\bupload\b") and _matches(q, r"\b(?:can|allow|permitted|possible)\b")
            and _matches(q, r"\bMB\b")):
        asked = re.search(r"(?<!\w)(\d+(?:\.\d+)?)\s*MB\b", q, re.I)
        limit = re.search(r"\bmaximum\s+upload\s+size\s+is\s+(\d+(?:\.\d+)?)\s*MB\b", line, re.I)
        if asked and limit and Decimal(asked.group(1)) > Decimal(limit.group(1)):
            return f"No. The maximum upload size is {limit.group(1)} MB."

    if _matches(q, r"\blibrary\b") and _matches(q, r"\bfloor\b"):
        asked = re.search(r"\bfloor\s*(\d+)\b", q, re.I)
        actual = re.search(r"\blibrary\s+is\s+located\s+on\s+Floor\s*(\d+)\b", line, re.I)
        if asked and actual and int(asked.group(1)) != int(actual.group(1)):
            return f"No. The library is located on Floor {actual.group(1)}."

    return None


def recover_grounded_answer(
    question: str, passages: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], str] | None:
    """Return (answer, passage, literal quote) when evidence is unambiguous.

    This deliberately uses only retrieved passages and never searches other
    users' workspaces, infers missing facts, or trusts an unsupported model.
    """
    candidates: list[tuple[str, dict[str, Any], str]] = []
    for passage in passages:
        for raw in str(passage["text"]).splitlines():
            quote = raw.strip()
            if not (8 <= len(quote) <= 600):
                continue
            answer = _candidate(question, quote)
            if answer and is_answer_consistent_with_quote(answer, quote):
                candidates.append((answer, passage, quote))
    if not candidates:
        return None
    # Reject contradictory source documents or multiple different values.
    values = {re.sub(r"\s+", " ", answer).casefold() for answer, _, _ in candidates}
    if len(values) != 1:
        return None
    return candidates[0]


def complete_numeric_unit(question: str, answer: str, quote: str) -> str:
    """Expand bare marks into the exact unit and period given in the quote."""
    if not re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", answer):
        return answer
    if not (_matches(question, r"\bmarks\b") and _matches(question, r"\b(?:late|day)\b")):
        return answer
    m = re.search(r"\b(?P<num>\d+(?:\.\d+)?)\s+marks\s+per\s+(?P<day>(?:calendar\s+)?day)\b", quote, re.I)
    if not m or Decimal(answer.strip()) != Decimal(m.group("num")):
        return answer
    return f"{m.group('num')} marks per {m.group('day')}"
