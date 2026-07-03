from __future__ import annotations
from typing import Optional
from pydantic import BaseModel

class NewsItem(BaseModel):
    title: str
    publisher: Optional[str] = None
    link: Optional[str] = None
    published: Optional[str] = None
    summary: Optional[str] = None
    relevance: Optional[float] = None

class Fundamentals(BaseModel):
    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = "USD"
    market_cap: Optional[float] = None
    pe_trailing: Optional[float] = None
    pe_forward: Optional[float] = None
    peg: Optional[float] = None
    price_to_sales: Optional[float] = None
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    profit_margin: Optional[float] = None
    roe: Optional[float] = None
    debt_to_equity: Optional[float] = None
    free_cash_flow: Optional[float] = None
    total_cash: Optional[float] = None
    total_debt: Optional[float] = None
    beta: Optional[float] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    recommendation: Optional[str] = None
    source: str = "yfinance"
    # V0.3.2 additive (all optional; absent -> not shown by UI)
    previous_close: Optional[float] = None
    day_change: Optional[float] = None
    day_change_pct: Optional[float] = None
    next_earnings_date: Optional[str] = None
    days_to_earnings: Optional[int] = None
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    target_low: Optional[float] = None
    target_upside_pct: Optional[float] = None
    num_analysts: Optional[int] = None
    recommendation_mean: Optional[float] = None
    pe_history_percentile: Optional[float] = None
    price_history: Optional[list[float]] = None

class ScoreBreakdown(BaseModel):
    growth: float
    profitability: float
    debt: float
    valuation: float
    moat: float
    momentum: float
    risk: float
    composite: float
    rating: str
    confidence: str

class Report(BaseModel):
    executive_summary: str
    bull_case: list[str]
    bear_case: list[str]
    what_changed: list[str]
    competitive_position: str
    valuation: str
    risks: list[str]
    final_score: float
    analyst_conclusion: str
    generated_by: str

class AnalysisResponse(BaseModel):
    fundamentals: Fundamentals
    scores: ScoreBreakdown
    news: list[NewsItem]
    report: Report
    data_source: str
    generated_at: str

class RankedItem(BaseModel):
    rank: int
    ticker: str
    name: Optional[str] = None
    composite: float
    rating: str

class CompareResponse(BaseModel):
    items: list[AnalysisResponse]
    ranking: list[RankedItem]
    top_pick: str
    verdict: str
    errors: list[str] = []
    generated_at: str
