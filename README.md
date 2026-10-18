# NewsRadar 📡 — News-Based Stock Risk Analysis

NewsRadar collects financial news for a watchlist of companies, analyses every article with an LLM and turns the results into a dashboard of risk scores, sentiment trends and signals, both for public tickers and for private companies such as startups.

**Live demo:** https://newsradar-web.onrender.com
*(Hosted on Render's free tier, so the first load after a period of inactivity can take 30–60 seconds while the server wakes up.)*

> **Principle:** NewsRadar gives a clear direction (bullish / neutral / bearish) and a conviction level, but it keeps the **news-flow signal separate from price prediction**. It says explicitly what news cannot tell you (valuation, whether a move is already priced in) and adds a **"verify first" checklist** to every view. No unexplained BUY/SELL calls. This is not investment advice.

---

## Features

- **Watchlist with two entity types:** `ticker` (public companies, news via Finnhub) and `keyword` (private companies and startups, news via NewsAPI), behind an interchangeable `NewsProvider` interface.
- **Scheduled ingestion:** an APScheduler job refreshes news automatically. Articles are de-duplicated by URL hash, so the same article is never analysed (or paid for) twice.
- **Two-level LLM analysis with structured output**
  - *Per article:* sentiment (−1..1), event type, risk flags, impact horizon, relevance (articles below 0.3 are filtered out) and a short rationale.
  - *Per entity:* risk score (0–100), sentiment trend, top 3 drivers, summary, stance and conviction, 2–4 "what to verify" points and an invalidation condition.
- **Chat with the news:** a streaming (SSE) chat in which the latest ~15 articles of an entity are injected as context.
- **Analyst consensus and price targets** (Finnhub / Financial Modeling Prep) shown next to the news signal.
- **Bilingual (TR / EN):** both the interface and the AI analysis are generated in the user's language.
- **Multi-user and cost-safe for a public site:** bcrypt passwords, signed session tokens, anonymous sessions, tiered per-user quotas, a system-wide **daily LLM budget in USD** and an **admin panel** with usage, spend per model, cache hit rate and system health.
- **Cost controls:** every LLM call is recorded with its model and input / output / cache tokens and priced from a per-model price table; prompt caching on the system prompt and tool schemas; entity assessments are skipped when there is no new data; assessment prompts are kept below the 100k-token price tier.
- **Output quality guards:** no user-facing field ends mid-sentence (length is steered by the prompt, code only trims at a sentence boundary as a safety net), boilerplate phrases are banned and retried once, and every assessment is scanned for investment-advice wording.
- **Interactive charts** (daily averages, calendar axis, time selector, zoom/pan) built with Recharts.

## Tech stack

| Layer | Technologies |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, SQLite, APScheduler, Pydantic, bcrypt |
| LLM | **Anthropic Claude API** (`claude-haiku-5-5` for article analysis, entity assessments and chat; configurable per purpose) behind a provider abstraction; any OpenAI-compatible endpoint (e.g. OpenRouter) can be switched in with one environment variable |
| Data sources | Finnhub (ticker news, analyst recommendations), NewsAPI (keyword news), Financial Modeling Prep (price targets) |
| Frontend | React 18, Vite, Tailwind CSS, Recharts |
| Deployment | Render (web service + static site, defined in [`render.yaml`](render.yaml)), deployed from GitHub |

## Architecture

```
newsradar/
├── backend/                     FastAPI + SQLite + APScheduler + LLM
│   ├── app/
│   │   ├── config.py            settings from .env (no keys in code)
│   │   ├── db/                  SQLAlchemy models
│   │   ├── providers/           NewsProvider interface + Finnhub / NewsAPI / FMP
│   │   ├── analysis/            LLM pipeline: prompts, schemas, provider abstraction,
│   │   │                        model/price table, output-quality guards
│   │   ├── api/                 routes: entities, refresh, dashboard, chat (SSE), auth, admin
│   │   ├── ingest.py            fetching + URL-hash de-duplication
│   │   ├── refresh.py           fetch → analyse orchestration
│   │   ├── scheduler.py         automatic refresh
│   │   ├── quota.py, budget.py  per-user quotas + per-call cost tracking, daily USD budget
│   │   └── security.py          sessions, rate limiting, hardening
│   ├── evals/                   live evaluation scripts (full refresh checks, model comparison)
│   ├── test_*.py                17 test scripts (security, quotas, isolation, truncation, …)
│   └── .env.example
└── frontend/                    React (Vite) + Tailwind + Recharts
```

## Engineering notes: problems I ran into

Building and running NewsRadar in production surfaced several real problems. These were the most instructive:

- **Silently truncated LLM output.** Large article batches hit the output-token limit, so responses were cut off without an obvious error. Fix: configurable batch size and output-token cap, plus automatic batch splitting when a truncation is detected (covered by `test_truncation.py`).
- **A relevance pre-filter that dropped Turkish articles.** Valid Turkish news was being filtered out before it ever reached the analysis step, so the filter had to be fixed to let non-English articles through.
- **Templated LLM answers.** Example sentences in the system prompt made the model copy them almost word for word. Removing the examples fixed it.
- **Making a public LLM app affordable.** Anyone can open the site, so costs are capped by per-user quotas, a system-wide daily USD budget and a per-IP limit on anonymous sessions. Switching to a small model with prompt caching and skipping assessments when nothing changed brought a full five-company refresh (TR + EN, up to 40 new articles per company) to roughly $0.07 in live tests.
- **Model output that looks fine until it doesn't.** Hard word caps cut verdicts mid-sentence, a model occasionally returned a list as a single string, and tool-call markup once leaked into a text field. Each is now caught by an automated check and handled without producing broken text.
- **Security hardening.** An attacker-perspective test suite (`test_security_audit.py`) led to fixes such as blocking brute force via spoofed `X-Forwarded-For` headers.
- **Free-tier hosting constraints.** Render's free disk is not persistent, so the default watchlist is re-seeded on start-up.

## Running locally

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your API keys (see comments in the file)
python -m app.seed          # default watchlist
uvicorn app.api.main:app --reload    # http://localhost:8000 (API docs: /docs)
```

Step-by-step checks without the server:

```bash
python -m app.cli status          # provider keys + watchlist
python -m app.cli llm-check       # each configured model: access, tool use, caching, cost
python -m app.cli fetch TSLA      # fetch news for one entity
python -m app.cli analyze TSLA    # run the LLM analysis and print JSON
```

Tests (each script uses an isolated temporary database):

```bash
python test_security.py
python test_truncation.py
```

Live evaluation (real API calls, runs on a copy of the local database):

```bash
python -m evals.eval_refresh --db /tmp/nr_eval.db --out evals/reports/refresh.md
```

### Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

If the backend runs elsewhere, set `VITE_API_URL` in `frontend/.env` (see `frontend/.env.example`).

## How it was built

I built NewsRadar as a personal project with AI-assisted development (Claude). I defined the product and its features, worked through the architecture and trade-offs, and tested and debugged it in production. I'm a Business Information Systems (Wirtschaftsinformatik) student at Hochschule Furtwangen University.

**Sarp Bıçak** · [sarpbicak@gmail.com](mailto:sarpbicak@gmail.com)

---

*NewsRadar is a news-flow signal tool, not financial advice. Always verify before acting.*
