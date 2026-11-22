"""Conservative alignment of AI answers with literal source evidence.

This is NOT a natural-language fact checker. It can recover a full written date
from a retrieved passage if a small LLM provided the correct answer but cited
an unrelated passage. Other unsupported claims still need more evaluation.
"""
from __future__ import annotations

import re
from typing import Any

from backend.answer_guard import is_answer_consistent_with_quote

_FORMAT = re.compile(r"\b(?:PDF|DOCX|CSV|JSON|XML|XLSX|PPTX|TXT)\b", re.I)

_DATE = re.compile(
    r"(?<!\w)(?:0?[1-9]|[12]\d|3[01])\s+"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{4}(?!\w)",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _dates(text: str) -> set[str]:
    return {_norm(m.group()) for m in _DATE.finditer(text)}


def select_evidence_quote(
    answer: str,
    proposed_quote: str,
    passages: list[dict[str, Any]],
) -> tuple[dict[str, Any], str] | None:
    """Return (passage, literal evidence quote), or None when unverified.

    Accept a valid model-provided quote first. On a mismatch, only retry using
    an exact *written date* that occurs verbatim in the answer and a retrieved
    document line. Never infer missing facts or synthesize a citation.
    """
    ans_dates = _dates(answer)
    # Do not accept vague date claims backed by an unrelated non-date quote.
    if re.search(r"\b(?:date|day|month|year)\b", answer, re.IGNORECASE) and not ans_dates:
        return None
    literal_quote = _norm(proposed_quote)
    format_tokens = {m.group().casefold() for m in _FORMAT.finditer(answer)}

    for passage in passages:
        text = str(passage["text"])
        if (
            len(literal_quote) >= 8
            and literal_quote in _norm(text)
            and (not format_tokens or format_tokens.issubset({m.group().casefold() for m in _FORMAT.finditer(proposed_quote)}))
            and (not ans_dates or ans_dates.issubset(_dates(proposed_quote)))
            and is_answer_consistent_with_quote(answer, proposed_quote)
            and is_answer_consistent_with_quote(answer, text)
        ):
            return passage, proposed_quote.strip()

    # A model can choose the wrong literal sentence while answering a file-
    # format question correctly. Align only exact format tokens, and only
    # when the proposed quote occurs somewhere in the retrieved passages.
    if format_tokens and any(literal_quote in _norm(str(p["text"])) for p in passages if len(literal_quote) >= 8):
        options = []
        for passage in passages:
            for raw in str(passage["text"]).splitlines():
                line = raw.strip()
                found = {m.group().casefold() for m in _FORMAT.finditer(line)}
                if (len(line) >= 8 and format_tokens.issubset(found)
                        and _norm(answer) in _norm(line)
                        and is_answer_consistent_with_quote(answer, line)):
                    options.append((passage, line))
        if len({line.casefold() for _, line in options}) == 1:
            return options[0]

    # Recover one exact date from the actual passage. A quote about an
    # unrelated fee cannot substantiate a date answer.
    if len(ans_dates) != 1:
        return None
    sought = next(iter(ans_dates))
    for passage in passages:
        for line in str(passage["text"]).splitlines():
            evidence_line = line.strip()
            if (
                len(evidence_line) >= 8
                and sought in _dates(evidence_line)
                and is_answer_consistent_with_quote(answer, evidence_line)
                and is_answer_consistent_with_quote(answer, str(passage["text"]))
            ):
                return passage, evidence_line
    return None
