# Greenzaction

Greenzaction is a full-stack sustainable spending intelligence app. It connects simulated UPI, card and wallet transactions to transparent category-based carbon estimates, Green Scores, rewards, analytics, recommendations and GreenBot.

## Project structure

```text
.
├── backend/
│   ├── app.py          # Flask REST API and transaction workflow
│   ├── auth.py         # JWT creation and role middleware
│   ├── carbon.py       # factors, calculations, ratings, scoring and rewards
│   ├── ai.py            # Gemini adapter plus rule-based fallback and GreenBot
│   └── store.py        # MongoDB adapter with demo-memory fallback
├── frontend/           # reserved for future component extraction
├── public/manus-routes.json
├── src/                # React/Vite client
├── .env.example
├── plan.md
└── TODO.md
```

## Run locally

1. Copy `.env.example` to `.env` and set `JWT_SECRET`. Add `MONGODB_URI` if you want MongoDB persistence; otherwise the app starts in demo-memory mode so the UI is immediately usable.
2. Install Python dependencies with `python3 -m pip install -r requirements.txt`.
3. Install frontend dependencies with `pnpm install` (or `npm install`).
4. Start the API in one terminal: `python3 -m backend.app`.
5. Start Vite in another: `pnpm dev`.

The browser app runs at `http://localhost:3000`, and the API is proxied at `/api`. The seeded demo account is `demo@greenzaction.app` / `demo1234`. The seeded admin account is `admin@greenzaction.app` / `admin1234`. For real deployments, create or promote admin roles through a protected operational workflow rather than exposing role editing in the browser.

## Data model and estimation note

The API writes users, transactions, emission factors, carbon calculations, Green Scores, reward ledger entries, achievements, sustainability goals and recommendations. A transaction uses a category-specific spend-to-activity proxy and then multiplies the proxy activity by a published-factor reference. The result is explicitly marked as an estimate, with factor source, method and confidence stored beside it. It does not claim that currency is a physical activity measurement.

## External API keys

Set `GEMINI_API_KEY` and optionally `GEMINI_MODEL` to enable Gemini recommendations. When unavailable or if the request fails, the deterministic rule-based engine remains active. No provider key is committed to the repository.

## Production container

The Dockerfile builds the Vite client and serves the resulting static files from Flask on `PORT` (default `3000`). MongoDB is still read at runtime through `MONGODB_URI`; container filesystem state is not used as durable application storage.

## Advanced capabilities

The upgrade adds product-level lifecycle profiles with quantities and phase breakdowns, sustainable shopping search, a purchase simulator, scikit-learn/Pandas monthly forecasting with MAE/RMSE and insufficient-history gating, personal carbon budgets, dynamic challenges and redemption, curated merchant discovery, advanced GreenBot intents, and a carbon-intelligence screen. Product and merchant reference records are stored or exposed with source/confidence metadata; the app continues to label estimates clearly.

Advanced routes are `/app/intelligence`, `/app/shopping`, `/app/simulator`, and `/app/merchants`.
