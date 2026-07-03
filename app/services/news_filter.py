"""News relevance scoring and filtering.

Problem: raw yfinance news for a ticker often includes unrelated market-wide
stories (Bitcoin, gold miners, other big caps). This module scores each headline
against the specific company (name, ticker, executives, products) and its sector,
keeps only the most relevant items, and exposes a relevance score per item.

Scoring weights:
    company name / ticker .......... 4
    curated company keyword ........ 3   (executives, flagship products, segments)
    sector / industry keyword ...... 2

An item is kept if its score >= MIN_SCORE. We return the top N by score.
"""
from __future__ import annotations
import re
from typing import Optional

from app.models import Fundamentals, NewsItem

MIN_SCORE = 2.0
TOP_N = 5

NAME_STOPWORDS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "plc", "group", "holdings", "holding", "the", "sa", "ag",
    "nv", "class", "common", "stock", "technologies", "international",
}

# Curated, company-specific keywords (executives, products, segments, domain).
COMPANY_KEYWORDS = {
    "NVDA": ["nvidia", "jensen huang", "geforce", "cuda", "gpu", "rtx", "data center",
             "datacenter", "hopper", "blackwell", "accelerator", "ai chip", "ai chips"],
    "AMD": ["amd", "advanced micro devices", "lisa su", "ryzen", "radeon", "epyc",
            "instinct", "gpu", "cpu", "data center", "accelerator", "ai chip"],
    "MSFT": ["microsoft", "satya nadella", "azure", "copilot", "windows", "office",
             "xbox", "openai", "activision", "cloud"],
    "AAPL": ["apple", "tim cook", "iphone", "ipad", "mac", "macbook", "app store",
             "ios", "vision pro", "airpods", "services"],
    "TSLA": ["tesla", "elon musk", "model 3", "model y", "model s", "cybertruck",
             "robotaxi", "full self-driving", "fsd", "gigafactory", "autopilot"],
}

# Generic domain keywords keyed by a substring of the industry/sector name.
INDUSTRY_KEYWORDS = {
    "semiconduct": ["chip", "chips", "semiconductor", "semiconductors", "gpu", "cpu",
                    "wafer", "foundry", "data center", "processor", "accelerator", "node"],
    "software": ["software", "cloud", "saas", "platform", "subscription", "enterprise"],
    "consumer electronics": ["device", "devices", "smartphone", "hardware", "wearable", "gadget"],
    "auto": ["ev", "electric vehicle", "vehicle", "battery", "autonomous", "self-driving"],
    "internet": ["search", "advertising", "ads", "platform", "cloud"],
    "bank": ["loan", "loans", "deposit", "interest rate", "lending", "banking"],
    "drug": ["drug", "fda", "trial", "therapy", "clinical", "approval"],
    "biotech": ["drug", "fda", "trial", "therapy", "clinical", "pipeline"],
    "energy": ["oil", "gas", "barrel", "drilling", "refinery"],
    "retail": ["store", "stores", "same-store", "e-commerce", "shoppers"],
}


def _normalize(text: str) -> str:
    """Lowercase, collapse non-alphanumerics to single spaces, pad with spaces."""
    t = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    return " " + t + " "


def _contains(hay_norm: str, term: str) -> bool:
    t = re.sub(r"[^a-z0-9]+", " ", term.lower()).strip()
    if not t:
        return False
    return (" " + t + " ") in hay_norm


def _build_terms(f: Fundamentals) -> dict[str, float]:
    """Term -> weight. Higher-weight wins on overlap."""
    terms: dict[str, float] = {}

    # ticker + company name
    if f.ticker:
        terms[f.ticker.lower()] = 4.0
    if f.name:
        cleaned = re.sub(r"[^a-z0-9 ]", " ", f.name.lower())
        tokens = [w for w in cleaned.split() if w and w not in NAME_STOPWORDS]
        if tokens:
            # full distinctive phrase
            terms[" ".join(tokens)] = 4.0
            # single distinctive token (e.g. "nvidia", "apple")
            for w in tokens:
                if len(w) >= 4:
                    terms.setdefault(w, 4.0)

    # curated company keywords
    for kw in COMPANY_KEYWORDS.get((f.ticker or "").upper(), []):
        if terms.get(kw, 0) < 3.0:
            terms[kw] = max(terms.get(kw, 0), 3.0)

    # industry / sector keywords
    haystack = " ".join([f.industry or "", f.sector or ""]).lower()
    for key, kws in INDUSTRY_KEYWORDS.items():
        if key in haystack:
            for kw in kws:
                terms.setdefault(kw, 2.0)

    return terms


def score_item(item: NewsItem, terms: dict[str, float]) -> float:
    text = " ".join(filter(None, [item.title, item.publisher, getattr(item, "summary", None)]))
    hay = _normalize(text)
    score = 0.0
    for term, weight in terms.items():
        if _contains(hay, term):
            score += weight
    return min(score, 10.0)


def filter_news(items: list[NewsItem], f: Fundamentals,
                top_n: int = TOP_N, min_score: float = MIN_SCORE) -> list[NewsItem]:
    if not items:
        return []
    terms = _build_terms(f)
    scored = []
    for it in items:
        s = score_item(it, terms)
        if s >= min_score:
            it.relevance = round(s, 1)
            scored.append((s, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:top_n]]
