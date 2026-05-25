# arco-papers-api

Python backend for the Arco Papers AI platform — a family paper manufacturing business in Islamabad, Pakistan. The API powers an AI assistant, quotation flow, and operational automations (payment reminders, research agents) while integrating with Supabase for product and order data.

## What this does

- **AI chat** — LangChain tool-calling agent with product/pricing context from Supabase and optional RAG over product docs (Chroma).
- **Quote generation** — `POST /quote` builds quotes from live pricing, can email customer and internal inbox via Gmail.
- **Authenticated client APIs** — Quote history and order creation from accepted quotes (Supabase JWT).
- **Payment reminders** — Scheduled WhatsApp template messages for due / 7-day / 14-day overdue B2B payments (`backend/payment_reminders.py`).
- **Research agents** — Standalone learning implementations: hand-rolled loop (`research_assistant.py`) vs LangGraph (`research_assistant_lg.py`).
- **Tender scraping** — Experimental scrapers for government procurement listings (`tender_scraper.py`).
- **Static web UI** — `GET /` serves `static/index.html` alongside the Flutter app.

## Stack

| Layer | Technology |
|--------|------------|
| API | FastAPI, Uvicorn |
| AI | OpenAI, LangChain, LangGraph (backend experiments) |
| Data | Supabase (products, clients, quotes, orders) |
| Vector store | Chroma (product RAG in `agent.py`) |
| Auth | Supabase JWT verification (`auth.py`) |
| Messaging | WhatsApp Cloud API (Meta) |
| Email | Gmail SMTP (quote delivery) |
| Deploy | Render (`render.yaml`) |

## API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | No | Static HTML frontend |
| `GET` | `/health` | No | Health check |
| `POST` | `/chat` | No | AI assistant (in-memory session per `session_id`) |
| `POST` | `/quote` | No | Generate and optionally email a quote |
| `GET` | `/quotes/history` | Bearer (Supabase) | List quotes for signed-in client |
| `POST` | `/orders` | Bearer (Supabase) | Create order from a quote |

## Project structure

```
arco-papers/
├── main.py                 # FastAPI app, routes, quote email
├── agent.py                # LangChain chat + quote tools, Chroma RAG
├── auth.py                 # Supabase JWT validation
├── database.py             # Supabase data access
├── tender_scraper.py       # PPRA / Pakistan Post tender scrapers
├── static/                 # Legacy web chat UI
├── backend/
│   ├── research_assistant.py
│   ├── research_assistant_lg.py
│   ├── payment_reminders.py
│   ├── payments.json       # Dev payment ledger for reminders
│   ├── test_research.py
│   └── test_whatsapp.py
├── requirements.txt
├── render.yaml
└── .env.example
```

## Prerequisites

- Python 3.11+
- Supabase project (products, clients, quotes, tenants)
- OpenAI API key
- Optional: Gmail app password, WhatsApp Cloud API credentials, `SUPABASE_JWT_SECRET`

## Local setup

```powershell
cd arco-papers
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set at minimum:

```env
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
SUPABASE_JWT_SECRET=

# Quote emails (optional)
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=

# WhatsApp reminders (backend/payment_reminders.py, test_whatsapp.py)
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
```

Run the API:

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Backend scripts

```powershell
# Research agent tests
python backend\test_research.py

# WhatsApp test send (loads .env from project root)
python backend\test_whatsapp.py

# Payment reminder batch job
python backend\payment_reminders.py
```

## Deployment

Configured for [Render](https://render.com): `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set `OPENAI_API_KEY` and Supabase secrets in the Render dashboard.

Public URL used by the Flutter app: `https://arco-papers-api.onrender.com`

## Related

- Flutter client: [arco-papers-app](https://github.com/Awanjee/arco-papers-app) (sibling repo / `arco_papers_app` in monorepo)
