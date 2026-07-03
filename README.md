# Auspex - V0.4.0 (Memory — external memory for investors)

> Auspex — your AI Investment Inbox. Reads the signals. You decide.
>
> Your senior equity analyst that never sleeps. Type one ticker for a full report - or several to compare them side by side, ranked best to worst with an analyst verdict.

V0.4.0 pivots Auspex into an external memory for disciplined investors: it confronts an investor's own written reasons against reality and ends with a question, never advice. New: a held-position onboarding (/app) that decomposes a holding reason into watchable lines (Claude with heuristic fallback), tags each line honestly as auto/back-testable, auto/watched-forward or manual, and replays 12 months with two carefully designed outcomes (an error save when a line was already crossed, a vigilance save when the thesis held). A deterministic Constitution filter (app/services/constitution.py) rejects any non-conformant generated text. The score/rating/verdict are no longer displayed (kept internal only). The old dashboard is preserved at /legacy. V0.3.7 (AUSPEX Branding Edition) renames every visible touchpoint from Autonomous Analyst to Auspex (landing, navigation, hero, footer, app header, page titles, metadata, marketing copy and CTAs), adds the secondary slogan Reads the signals. You decide., and sets the Founding Members CTA email to team.auspex@gmail.com. Branding only — no scoring, API, engine, business logic, design, colour or user-flow changes. V0.3.6 is a landing conversion pass: a free-vs-paid differentiator in the hero, stronger psychological framing of the cost (FOMO, time lost, decision fatigue), a less aggressive audience headline, founder-pricing scarcity/value reinforcement, and a new objection-handling FAQ. Landing copy only — no product, backend, dashboard or color changes. V0.3.5 sharpens the landing copy for conversion (clearer problem framing, founder pricing with future €49 price, tighter audience fit, an emotional cost block) — landing copy only, no product, backend, dashboard or color changes. V0.3.4 adds a public landing page at / (the marketing site) and serves the app at /app (also /dashboard). The landing pitches the AI Investment Inbox positioning, with a live-demo button to /app and a Founding Members offer (mailto-based, no payment integration yet — set FOUNDER_EMAIL in app/static/landing.html). V0.3.3 turns the single-ticker report into an AI investment inbox: a Priority Signal at the very top (HIGH / MEDIUM / NO ACTION) answering do I need to do something today, a What changed since your last review block, an Events that may change the thesis feed (analyst revisions, earnings, guidance, product, regulation, macro) in place of generic news, and a What would make me change my mind block (bull trigger / bear trigger / thesis breaker). Decision before analysis; report scroll cut by ~40%.

V0.3.2 adds real timely signals to the inbox and report — today's price change, days to next earnings, analyst targets & consensus, a 30-day price sparkline and valuation vs the stock's own 1-year P/E range. All new fields are optional and additive: when a value is missing nothing is shown, and the app falls back cleanly to prior behavior. The scoring engine and the /api/analyze and /api/compare contracts are unchanged.

V0.3.1 reframes the home as an inbox for investors: it answers one question — do I need to do anything today? Your watchlist is triaged into Act now / Watch / Nothing to do, with memory of your last review and per-name deltas. V0.3 turns the analyst into a daily decision assistant: a home dashboard (AI Daily Brief, Today's Opportunities, Market Pulse, local Watchlist) and a richer single-ticker report (Why Now + conviction score, Portfolio Fit with best/not-ideal, Peer rank & percentile, Next Catalysts, structured Analyst Verdict). Frontend-only; the scoring engine and API are unchanged.

V0.2.1 is the first stable, reproducible release. It runs fully locally, with zero API keys and zero cost out of the box. An LLM key is optional and only upgrades the writing quality.

- Python 3.13 compatible (binary wheels only - no Rust, no Visual Studio Build Tools).
- Single-ticker analysis and multi-ticker comparison.
- Proprietary 7-dimension scoring with a composite score out of 100.
- Keyword-based news relevance filtering (only the 5 most relevant headlines).
- Premium dark web UI served directly by the backend (no Node build step).

---

## What it does

Single ticker (for example NVDA):

1. Pulls fundamentals + recent news (yfinance, free, no key).
2. Scores 7 dimensions and computes a proprietary composite out of 100.
3. Generates a structured analyst report (Executive Summary, Bull/Bear, What Changed, Competitive Position, Valuation, Risks, Conclusion).
4. Renders everything in a polished dark web UI.

Multiple tickers (for example NVDA, AMD, MSFT, AAPL, TSLA):

1. A summary card per company (composite score, rating, all sub-scores).
2. A side-by-side comparison table (best value in each row marked).
3. An automatic leaderboard, ranked best to worst.
4. An analyst verdict: which company deserves the most attention today, and why.

If live data cannot be fetched (offline, rate-limited), the app falls back to bundled sample data for NVDA, AMD, MSFT, AAPL and TSLA, so the demo always works.

---

## Requirements

- Python 3.13 (3.10+ also works).
- Internet access for live data (yfinance) and for the Google Fonts CDN used by the UI (the UI still works offline with system fonts).

---

## Install and run - Windows (PowerShell)

From the folder where you extracted the project:

```powershell
cd Desktop\autonomous-analyst

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python run.py
```

Then open http://127.0.0.1:8000 and type a ticker.

If PowerShell blocks the activation script, see Troubleshooting below.

## Install and run - macOS / Linux

```bash
cd autonomous-analyst
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

## Optional - richer report writing via an LLM

```bash
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux
```

Put OPENAI_API_KEY=... (or ANTHROPIC_API_KEY=...) in .env, then restart. Without a key, the app uses the deterministic template engine (free).

---

## Dependencies (reproducible installs)

Two files describe dependencies:

- `requirements.in` - human-maintained constraints (version ranges). Edit this file when you intentionally add or bump a dependency.
- `requirements.txt` - the pinned lockfile: every package, including transitive ones, fixed to an exact version. This is what you install. Running `pip install -r requirements.txt` six months from now reinstalls the same set validated for this release.

Day to day you only run:

```bash
pip install -r requirements.txt
```

To change a dependency, edit `requirements.in`, then regenerate the lockfile with pip-tools:

```bash
pip install pip-tools
pip-compile requirements.in        # rewrites requirements.txt
```

Notes:

- The lockfile was resolved and validated on Python 3.10; all pinned versions also ship binary wheels for Python 3.13 (no Rust, no Build Tools).
- `uvloop` is pinned with a marker (`sys_platform != "win32"`) because it has no Windows wheel. On Windows, uvicorn runs on asyncio instead - this is expected and supported.
- For a platform-perfect lock on Windows + Python 3.13, run `pip-compile` on that machine.

---

## Usage examples

- Single report: type NVDA and press Analyze (or Enter).
- Comparison: type NVDA, AMD, MSFT, AAPL, TSLA and press Analyze.
- Quick buttons under the input run common tickers and the 5-way comparison.

API:

```bash
curl "http://127.0.0.1:8000/api/analyze?ticker=NVDA"
curl "http://127.0.0.1:8000/api/compare?tickers=NVDA,AMD,MSFT,AAPL,TSLA"
curl "http://127.0.0.1:8000/api/health"
```

| Method | Route | Purpose |
|---|---|---|
| GET | /api/analyze?ticker=NVDA | Full analysis for one company |
| POST | /api/analyze | { "ticker": "NVDA", "live": true } |
| GET | /api/compare?tickers=NVDA,AMD | Ranked comparison + analyst verdict (max 8) |
| POST | /api/compare | { "tickers": "NVDA, AMD", "live": true } |
| GET | / | Public landing page |
| GET | /app  ·  /dashboard | The application (AI Investment Inbox) |
| GET | /api/health | Engine status + scoring weights |

---

## Scoring model

Composite = weighted sum of seven 0-100 sub-scores:

| Dimension | Weight | Driven by |
|---|---|---|
| Growth | 20% | revenue and earnings growth |
| Profitability | 18% | operating / net margin, ROE |
| Moat | 15% | gross margin, ROE, operating margin |
| Valuation | 15% | forward P/E, P/S, PEG (cheaper = higher) |
| Debt | 12% | debt/equity, net-cash bonus |
| Momentum | 12% | position in the 52-week range |
| Risk | 8% | beta (lower beta = higher score) |

Rating bands: 80+ Strong Buy, 67+ Buy, 50+ Hold, 38+ Reduce, else Sell. Every threshold lives in app/services/scoring.py and is easy to tune.

News relevance: each headline is scored against the company name/ticker (weight 4), curated company keywords such as executives and products (weight 3), and sector keywords (weight 2). Only headlines above the threshold are kept, and only the top 5 are shown. Logic lives in app/services/news_filter.py.

---

## Project structure

```
autonomous-analyst/
  run.py                       launcher (python run.py)
  requirements.in              human-maintained constraints
  requirements.txt             pinned lockfile (install this)
  README.md
  .env.example
  app/
    main.py                    FastAPI app + routes + serves the UI
    config.py                  settings (.env)
    models.py                  pydantic schemas
    services/
      data_provider.py         yfinance + bundled fixtures fallback
      scoring.py               proprietary scoring engine
      report.py                analyst report generator (+ optional LLM)
      compare.py               ranking + analyst verdict
      news_filter.py           news relevance scoring/filtering
      llm.py                   optional OpenAI/Anthropic enhancement
      fixtures.py              offline sample data
    static/
      index.html               single-file premium UI
```

---

## Troubleshooting

- PowerShell: "running scripts is disabled on this system" when activating the venv. Run once in the same window: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass, then run .\.venv\Scripts\Activate.ps1 again.
- "python is not recognized" or wrong version. Use the Windows launcher: py -3.13 -m venv .venv. Check installed versions with py -0p.
- Port 8000 already in use. Set another port before launching: set PORT=8010 (PowerShell: $env:PORT=8010), then python run.py.
- The UI loads but fonts look generic. Inter/JetBrains Mono are loaded from the Google Fonts CDN; offline, the UI falls back to system fonts. Layout and styling are unaffected.
- News or fundamentals show "sample (bundled fixture)" as the source. Live fetch failed (offline, rate limit, or unknown ticker) and the app fell back to bundled sample data. Try again later or check connectivity.
- "No highly relevant recent news found." No fetched headline passed the relevance threshold for that company. This is expected behavior, not an error.
- Install fails trying to compile from source. Make sure you are on Python 3.13 (or 3.10+) and that pip is up to date: python -m pip install --upgrade pip. The pinned floors in requirements.txt all ship binary wheels.

---

## Known limitations

- Data source: fundamentals and news come from yfinance, an unofficial wrapper around Yahoo Finance. It can rate-limit, change shape, or return incomplete fields. When live data is unavailable the app shows bundled sample data, clearly labelled as such.
- News filtering is keyword-based: it is fast and deterministic, but it can keep a domain-relevant headline about a competitor, or miss a relevant headline phrased without the expected keywords. It is not semantic.
- No user accounts: there is no login or per-user state.
- No persistent watchlist: nothing is saved between sessions; each analysis is computed on demand.
- No LLM by default: report text is generated by a deterministic template unless an API key is provided.
- Scores are heuristic: thresholds are hand-tuned for a demo, not calibrated against historical returns. This is research/education tooling, not investment advice.

---

## Roadmap

- V0.3 - LLM enrichment: richer, more natural executive summaries, verdicts and conclusions when an API key is present, with automatic fallback to the template engine.
- V0.4 - Watchlist: save tickers and revisit them; lightweight local persistence.
- V0.5 - Daily brief: a scheduled run that screens a list and surfaces only what changed and what needs attention.
- V1.0 - Autonomous agents: dedicated agents (Earnings, News, Insider, Macro, Portfolio, Discovery) behind an orchestrator, moving toward a personal CIO experience.

---

## Disclaimer

Research and education only. Not personalised investment advice. Bundled sample data is illustrative and not live market data.
