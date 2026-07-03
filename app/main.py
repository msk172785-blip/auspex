"""AUSPEX — FastAPI app: landing, memory flow (/app), legacy dashboard, and API."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app import __version__
from app.config import settings
from app.models import AnalysisResponse, CompareResponse
from app.services.data_provider import get_data, fetch_history
from app.services.scoring import compute_scores, WEIGHTS
from app.services.report import build_report
from app.services.compare import build_comparison
from app.services.decompose import decompose_reason

MAX_COMPARE = 8
logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Auspex", version=__version__)
STATIC_DIR = Path(__file__).parent / "static"


class AnalyzeRequest(BaseModel):
    ticker: str
    live: bool = True


class CompareRequest(BaseModel):
    tickers: list[str] | str
    live: bool = True


class DecomposeRequest(BaseModel):
    ticker: str
    reason: str
    exit_condition: str | None = None


def _parse_tickers(raw) -> list[str]:
    if isinstance(raw, str):
        parts = raw.replace(",", " ").split()
    else:
        parts = []
        for r in raw:
            parts.extend(str(r).replace(",", " ").split())
    seen, out = set(), []
    for p in parts:
        t = p.strip().upper()
        if t and t not in seen and t.replace(".", "").replace("-", "").isalnum():
            seen.add(t); out.append(t)
    return out


def _valid_ticker(t: str) -> bool:
    return bool(t) and t.replace(".", "").replace("-", "").isalnum()


def _analyze(ticker: str, live: bool) -> AnalysisResponse:
    ticker = (ticker or "").strip().upper()
    if not _valid_ticker(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")
    try:
        fundamentals, news, source = get_data(ticker, prefer_live=live)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    scores = compute_scores(fundamentals)
    report = build_report(fundamentals, scores, news)
    return AnalysisResponse(fundamentals=fundamentals, scores=scores, news=news,
        report=report, data_source=source,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _compare(tickers_raw, live: bool) -> CompareResponse:
    tickers = _parse_tickers(tickers_raw)
    if not tickers:
        raise HTTPException(status_code=400, detail="No valid tickers provided.")
    if len(tickers) > MAX_COMPARE:
        raise HTTPException(status_code=400, detail=f"Too many tickers (max {MAX_COMPARE}).")
    items, errors = [], []
    for t in tickers:
        try:
            items.append(_analyze(t, live))
        except HTTPException as e:
            errors.append(f"{t}: {e.detail}")
        except Exception as e:
            errors.append(f"{t}: {e}")
    if not items:
        raise HTTPException(status_code=404, detail="; ".join(errors) or "No data.")
    return build_comparison(items, errors)


@app.get("/api/compare", response_model=CompareResponse)
def compare_get(tickers: str, live: bool = True):
    return _compare(tickers, live)


@app.post("/api/compare", response_model=CompareResponse)
def compare_post(req: CompareRequest):
    return _compare(req.tickers, req.live)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__, "llm_enabled": settings.llm_enabled,
            "llm_provider": settings.llm_provider,
            "decompose_engine": "anthropic" if settings.ANTHROPIC_API_KEY else "heuristic",
            "anthropic_model": settings.ANTHROPIC_MODEL,
            "weights": WEIGHTS}


@app.get("/api/diag/anthropic")
def diag_anthropic():
    """Live check: makes one tiny Claude call and returns the real outcome so a silent
    fallback becomes visible (model errors, quota, network)."""
    from app.services import llm
    if not settings.ANTHROPIC_API_KEY:
        return {"key_present": False, "model": settings.ANTHROPIC_MODEL, "ok": False, "error": "no_key"}
    text, err = llm.anthropic_json("Reply with the single token OK.", "Say OK.", max_tokens=8)
    return {"key_present": True, "provider": "anthropic", "model": settings.ANTHROPIC_MODEL,
            "ok": err is None, "sample": (text or "")[:60], "error": err}


@app.get("/api/analyze", response_model=AnalysisResponse)
def analyze_get(ticker: str, live: bool = True):
    return _analyze(ticker, live)


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze_post(req: AnalyzeRequest):
    return _analyze(req.ticker, req.live)


@app.post("/api/decompose")
def decompose_post(req: DecomposeRequest):
    """Reason -> monitorable assertions + current metrics + 1y price history. The
    score/rating/report are deliberately NOT returned. engine_note explains any fallback."""
    ticker = (req.ticker or "").strip().upper()
    if not _valid_ticker(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")
    if not (req.reason or "").strip():
        raise HTTPException(status_code=400, detail="A reason is required.")
    try:
        fundamentals, _news, source = get_data(ticker, prefer_live=True)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    hist = fetch_history(ticker)
    result = decompose_reason(req.reason, req.exit_condition, fundamentals)
    f = fundamentals
    eps = (f.price / f.pe_trailing) if (f.price and f.pe_trailing) else None
    return {
        "ticker": ticker,
        "name": f.name,
        "currency": f.currency or "USD",
        "price": f.price,
        "pe_trailing": f.pe_trailing,
        "eps": (round(eps, 4) if eps is not None else None),
        "current": result["snapshot"],
        "history": hist,
        "assertions": result["assertions"],
        "engine": result["engine"],
        "engine_note": result.get("engine_note"),
        "model": result.get("model"),
        "data_source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@app.get("/")
def landing():
    return FileResponse(STATIC_DIR / "landing.html")


@app.get("/app")
def app_page():
    return FileResponse(STATIC_DIR / "memory.html")


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(STATIC_DIR / "memory.html")


@app.get("/legacy")
def legacy_page():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
