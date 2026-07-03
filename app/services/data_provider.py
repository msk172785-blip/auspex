"""Data acquisition layer.

Strategy: try live data via yfinance. If it fails (no network, rate limit,
unknown ticker), fall back to bundled fixtures so the demo always renders.
"""
from __future__ import annotations
from typing import Optional
import logging
import datetime as _dt
import hashlib

from app.models import Fundamentals, NewsItem
from app.services.fixtures import get_fixture
from app.services.news_filter import filter_news

logger = logging.getLogger("data_provider")


def _safe(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _enrich_yf(t, info, f):
    """Best-effort additive enrichment. Any failure leaves fields as None."""
    try:
        last = f.price
        prev = info.get("previousClose") or info.get("regularMarketPreviousClose")
        fi = getattr(t, "fast_info", None)
        if fi is not None:
            try:
                last = (fi.get("last_price") if hasattr(fi, "get") else getattr(fi, "last_price", None)) or last
                prev = (fi.get("previous_close") if hasattr(fi, "get") else getattr(fi, "previous_close", None)) or prev
            except Exception:
                pass
        if last is not None and prev not in (None, 0):
            f.previous_close = float(prev)
            f.day_change = float(last) - float(prev)
            f.day_change_pct = (float(last) / float(prev) - 1) * 100
    except Exception:
        pass
    try:
        if info.get("targetMeanPrice"): f.target_mean = float(info["targetMeanPrice"])
        if info.get("targetHighPrice"): f.target_high = float(info["targetHighPrice"])
        if info.get("targetLowPrice"): f.target_low = float(info["targetLowPrice"])
        if info.get("numberOfAnalystOpinions"): f.num_analysts = int(info["numberOfAnalystOpinions"])
        if info.get("recommendationMean"): f.recommendation_mean = float(info["recommendationMean"])
        if f.target_mean and f.price:
            f.target_upside_pct = (f.target_mean / f.price - 1) * 100
    except Exception:
        pass
    try:
        ts = info.get("earningsTimestampStart") or info.get("earningsTimestamp")
        edate = None
        if ts:
            edate = _dt.datetime.utcfromtimestamp(int(ts)).date()
        else:
            cal = getattr(t, "calendar", None)
            ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if isinstance(ed, (list, tuple)) and ed:
                ed = ed[0]
            if ed is not None:
                edate = ed.date() if hasattr(ed, "date") else ed
        if edate is not None:
            f.next_earnings_date = str(edate)
            try:
                f.days_to_earnings = int((edate - _dt.date.today()).days)
            except Exception:
                pass
    except Exception:
        pass
    try:
        hist = t.history(period="1y", interval="1d")
        closes = [float(x) for x in hist["Close"].dropna().tolist()] if (hist is not None and len(hist)) else []
        if closes:
            f.price_history = [round(c, 2) for c in closes[-30:]]
            eps = info.get("trailingEps")
            if eps and eps > 0:
                cur = (f.price or closes[-1]) / eps
                series = [c / eps for c in closes]
                below = sum(1 for x in series if x <= cur)
                f.pe_history_percentile = round(below / len(series) * 100, 1)
    except Exception:
        pass


def _enrich_fixture(f):
    """Synthetic but deterministic enrichment for offline sample mode only."""
    try:
        if not f.price:
            return
        seed = int(hashlib.md5(f.ticker.encode()).hexdigest(), 16)
        dcp = round(((seed % 700) / 100.0) - 3.5, 2)
        f.day_change_pct = dcp
        f.previous_close = round(f.price / (1 + dcp / 100.0), 2)
        f.day_change = round(f.price - f.previous_close, 2)
        up = ((seed // 7) % 22) / 100.0 + 0.03
        f.target_mean = round(f.price * (1 + up), 2)
        f.target_high = round(f.target_mean * 1.15, 2)
        f.target_low = round(f.target_mean * 0.85, 2)
        f.target_upside_pct = round((f.target_mean / f.price - 1) * 100, 1)
        f.num_analysts = 25 + seed % 25
        f.recommendation_mean = round(1.6 + (seed % 18) / 10.0, 1)
        f.pe_history_percentile = float(40 + seed % 50)
        days = 7 + seed % 35
        f.days_to_earnings = int(days)
        f.next_earnings_date = str(_dt.date.today() + _dt.timedelta(days=days))
        base = f.price * 0.93
        n = 30
        hist = []
        for i in range(n):
            frac = i / (n - 1)
            wig = (((seed >> (i % 16)) & 7) - 3) / 100.0 * f.price * 0.01
            hist.append(round(base + (f.price - base) * frac + wig, 2))
        hist[-1] = round(f.price, 2)
        f.price_history = hist
    except Exception:
        pass


def _from_yfinance(ticker: str) -> Optional[tuple[Fundamentals, list[NewsItem]]]:
    try:
        import yfinance as yf
    except Exception as e:  # library missing
        logger.warning("yfinance not importable: %s", e)
        return None

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        if not info or _safe(info, "currentPrice", "regularMarketPrice", "marketCap") is None:
            return None

        fundamentals = Fundamentals(
            ticker=ticker.upper(),
            name=_safe(info, "longName", "shortName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            price=_safe(info, "currentPrice", "regularMarketPrice"),
            currency=info.get("currency", "USD"),
            market_cap=info.get("marketCap"),
            pe_trailing=info.get("trailingPE"),
            pe_forward=info.get("forwardPE"),
            peg=info.get("trailingPegRatio") or info.get("pegRatio"),
            price_to_sales=info.get("priceToSalesTrailing12Months"),
            revenue_growth=info.get("revenueGrowth"),
            earnings_growth=_safe(info, "earningsGrowth", "earningsQuarterlyGrowth"),
            gross_margin=info.get("grossMargins"),
            operating_margin=info.get("operatingMargins"),
            profit_margin=info.get("profitMargins"),
            roe=info.get("returnOnEquity"),
            debt_to_equity=info.get("debtToEquity"),
            free_cash_flow=info.get("freeCashflow"),
            total_cash=info.get("totalCash"),
            total_debt=info.get("totalDebt"),
            beta=info.get("beta"),
            week52_high=info.get("fiftyTwoWeekHigh"),
            week52_low=info.get("fiftyTwoWeekLow"),
            recommendation=info.get("recommendationKey"),
            source="yfinance",
        )

        news: list[NewsItem] = []
        try:
            for item in (t.news or [])[:30]:
                content = item.get("content", item)
                title = content.get("title") or item.get("title")
                if not title:
                    continue
                pub = None
                prov = content.get("provider") or {}
                if isinstance(prov, dict):
                    pub = prov.get("displayName")
                pub = pub or item.get("publisher")
                link = None
                url = content.get("canonicalUrl") or content.get("clickThroughUrl")
                if isinstance(url, dict):
                    link = url.get("url")
                link = link or item.get("link")
                summary = content.get("summary") or content.get("description")
                news.append(NewsItem(title=title, publisher=pub, link=link,
                                     published=content.get("pubDate"), summary=summary))
        except Exception as e:
            logger.warning("news parse failed: %s", e)

        try:
            _enrich_yf(t, info, fundamentals)
        except Exception as e:
            logger.warning("enrich failed for %s: %s", ticker, e)
        return fundamentals, news
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        return None


def _from_fixture(ticker: str) -> Optional[tuple[Fundamentals, list[NewsItem]]]:
    fx = get_fixture(ticker)
    if not fx:
        return None
    news = [NewsItem(title=n["title"], publisher=n.get("publisher")) for n in fx.get("news", [])]
    data = {k: v for k, v in fx.items() if k != "news"}
    fundamentals = Fundamentals(ticker=ticker.upper(), source="fixture", **data)
    _enrich_fixture(fundamentals)
    return fundamentals, news


def get_data(ticker: str, prefer_live: bool = True) -> tuple[Fundamentals, list[NewsItem], str]:
    """Returns (fundamentals, news, data_source)."""
    ticker = ticker.strip().upper()
    if prefer_live:
        live = _from_yfinance(ticker)
        if live:
            f, n = live
            if not n:  # backfill news from fixture if live news empty
                fx = _from_fixture(ticker)
                if fx:
                    n = fx[1]
            return f, filter_news(n, f), "live (yfinance)"

    fx = _from_fixture(ticker)
    if fx:
        return fx[0], filter_news(fx[1], fx[0]), "sample (bundled fixture)"

    raise ValueError(
        f"No data available for '{ticker}'. Live fetch failed and no bundled "
        f"sample exists. Try NVDA, AAPL, TSLA or MSFT for the offline demo."
    )


def fetch_history(ticker: str, period: str = "1y") -> dict:
    """Daily (date, close) series for the 12-month rewind. Live via yfinance,
    deterministic synthetic fixture fallback so the flow always runs offline."""
    ticker = ticker.strip().upper()
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval="1d")
        if hist is not None and len(hist):
            ser = hist["Close"].dropna()
            closes = [round(float(x), 2) for x in ser.tolist()]
            dates = [d.strftime("%Y-%m-%d") for d in ser.index]
            if closes:
                return {"dates": dates, "closes": closes, "source": "live (yfinance)"}
    except Exception as e:
        logger.warning("history fetch failed %s: %s", ticker, e)
    fx = get_fixture(ticker)
    base = (fx or {}).get("price")
    if not base:
        return {"dates": [], "closes": [], "source": "unavailable"}
    seed = int(hashlib.md5(ticker.encode()).hexdigest(), 16)
    n = 252
    start = base * 0.78
    today = _dt.date.today()
    closes, dates = [], []
    for i in range(n):
        frac = i / (n - 1)
        wig = (((seed >> (i % 23)) & 15) - 7) / 100.0 * base * 0.012
        cyc = 0.06 * base * ((i % 63) / 63.0 - 0.5)
        closes.append(round(start + (base - start) * frac + wig + cyc, 2))
        dates.append(str(today - _dt.timedelta(days=(n - 1 - i))))
    closes[-1] = round(base, 2)
    return {"dates": dates, "closes": closes, "source": "sample (bundled fixture)"}
