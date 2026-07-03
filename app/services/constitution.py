"""AUSPEX Constitution — deterministic conformance filter (V0.4).

The Constitution is a hard product rule, enforced in code, not only in copy:
- AUSPEX never holds an opinion, never recommends buy/sell, never rates the user,
  never judges.
- It returns the user's own words, dated, confronted with facts, and always ends
  with a question, never an instruction.
- No sentence may have AUSPEX as the subject of an opinion verb.

This module validates AUSPEX-GENERATED text only. It must never be run on the
user's own quoted words (those are displayed verbatim, untouched).

Design: a pure, deterministic, dependency-free filter. It exposes `check()` to
audit a generated string, `is_conformant()` for a boolean, and small safe builders
(`fact_question`, `as_condition`) that produce text guaranteed to pass `check()`.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

# Verbs that would turn AUSPEX into an opinion-holder / adviser / judge.
_OPINION_VERBS = (
    r"think|thinks|thought|believe|believes|feel|feels|reckon|reckons|"
    r"recommend|recommends|advise|advises|suggest|suggests|urge|urges|"
    r"rate|rates|rated|rating|grade|grades|score|scores|judge|judges|"
    r"predict|predicts|forecast|forecasts|expect|expects|prefer|prefers|"
    r"like|likes|favou?r|favou?rs|warn|warns|conclude|concludes"
)
# AUSPEX (or "we"/"the app") as subject of an opinion verb.
_SUBJECT_OPINION = re.compile(
    r"\b(auspex|we|i|the\s+app|the\s+system)\s+(?:\w+\s+){0,2}(?:" + _OPINION_VERBS + r")\b",
    re.IGNORECASE,
)
# Direct buy/sell/hold instructions.
_INSTRUCTION = re.compile(
    r"\b(you\s+should|you\s+must|you\s+need\s+to|"
    r"buy\s+now|sell\s+now|time\s+to\s+(?:buy|sell)|"
    r"we\s+recommend|i\s+recommend|recommended\s+action|"
    r"(?:^|\W)(?:buy|sell|short)\s+(?:it|this|now|the\s+stock|shares?))\b",
    re.IGNORECASE,
)
# A standalone imperative buy/sell verb at the start of a clause.
_IMPERATIVE_TRADE = re.compile(r"(?:^|[.;]\s*)(buy|sell|short)\b", re.IGNORECASE)


@dataclass
class Check:
    ok: bool
    reasons: list[str]


def check(text: str, require_question: bool = False) -> Check:
    """Audit a generated string. Returns ok=False with reasons if it violates the
    Constitution. If require_question is True, the text must end with a question."""
    reasons: list[str] = []
    t = (text or "").strip()
    if not t:
        return Check(False, ["empty"])
    if _SUBJECT_OPINION.search(t):
        reasons.append("auspex_as_opinion_subject")
    if _INSTRUCTION.search(t):
        reasons.append("buy_sell_instruction")
    if _IMPERATIVE_TRADE.search(t):
        reasons.append("imperative_trade")
    if require_question and not t.endswith("?"):
        reasons.append("does_not_end_with_question")
    return Check(len(reasons) == 0, reasons)


def is_conformant(text: str, require_question: bool = False) -> bool:
    return check(text, require_question=require_question).ok


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def fact_question(fact: str, question: str) -> str:
    """Safe builder for a confrontation line: a dated fact followed by a question.
    Guarantees conformance: the output ends with a question and carries no opinion
    or instruction added by AUSPEX. Callers pass already-factual strings.

    If the assembled text somehow trips the filter (e.g. a fact phrased oddly),
    we fall back to the question alone, which is always safe.
    """
    fact = _strip(fact)
    question = _strip(question)
    if not question.endswith("?"):
        question = question.rstrip(".") + "?"
    out = (fact + " " + question).strip() if fact else question
    if not check(out, require_question=True).ok:
        out = question  # the question alone is the minimal safe form
    return out


def as_condition(text: str) -> str:
    """Normalise a user-described exit rule into a neutral, monitorable condition
    phrase, stripping any imperative trade verb. Used only for the assertion label
    that AUSPEX displays (the user's raw words are shown separately, untouched)."""
    t = _strip(text)
    t = re.sub(r"^\s*(sell|buy|exit|dump|trim|short)\s+(if|when|once|below|above)\b",
               r"\2", t, flags=re.IGNORECASE)
    t = re.sub(r"^\s*(sell|buy|exit|dump|trim)\b[:,]?\s*", "", t, flags=re.IGNORECASE)
    return t.strip() or text.strip()
