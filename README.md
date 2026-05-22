# Arco Papers AI Platform

An AI-powered sales and operations platform for Arco Papers,
a paper manufacturer and supplier in Islamabad, Pakistan.
Built as a portfolio project demonstrating full-stack AI
engineering with LangChain, RAG, and tool-calling agents.

🌐 **Live Demo:** https://arco-papers-app-6b721.web.app  
📡 **API:** https://arco-papers-api.onrender.com/health  
📱 **Frontend Repo:** https://github.com/Awanjee/arco-papers-app

## Demo

▶️ [Watch 2-minute demo](https://www.loom.com/share/516dc81b811446ebbfbe28b6fa49836c)

---

## What It Does

- **AI Sales Assistant** — answers product and pricing
  questions using RAG over a product knowledge base
- **Tool-Calling Agent** — automatically calculates bulk
  order costs, pricing tiers, and order comparisons
- **Tender Scraper** — scrapes Pakistani government
  procurement portals weekly, scores tenders 0-100
  using an LLM, and emails a formatted digest
- **Product Catalogue** — browsable catalogue with
  category filters and pricing tiers

---

## Architecture
Flutter Web App (Firebase)
│
│ HTTP (Dio)
▼
FastAPI Backend (Render)
│
├── LangChain Agent
│       ├── RAG Tool → ChromaDB vector store
│       ├── Pricing Tier Tool → tier calculator
│       └── Order Cost Tool → quote generator
│
└── Tender Scraper (APScheduler)
├── Playwright → PPRA EPADS
├── Playwright → Pakistan Post
├── Playwright → TenderService.pk
├── LangChain LLM → relevance scoring
└── Gmail SMTP → weekly digest

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Flutter (Web, Android, iOS ready) |
| State Management | Provider |
| HTTP Client | Dio |
| Backend | FastAPI (Python 3.12) |
| AI Framework | LangChain + OpenAI GPT-4o-mini |
| RAG | ChromaDB + OpenAI Embeddings |
| Web Scraping | Playwright + BeautifulSoup4 |
| Scheduling | APScheduler |
| Frontend Hosting | Firebase Hosting |
| Backend Hosting | Render |
| Version Control | GitHub |

---

## Key Engineering Decisions

**Why RAG over fine-tuning?**  
Product catalogue data changes frequently. RAG allows
real-time updates to the knowledge base without
retraining. Rebuilds the vector store on startup —
works correctly on ephemeral hosting (Render free tier).

**Why a tool-calling agent over a simple chain?**  
Pricing calculations require deterministic logic that
LLMs hallucinate if asked to reason from text alone.
Separating pricing into a Python tool gives exact
results while the LLM handles natural language
understanding.

**Why Playwright over requests for scraping?**  
PPRA and government portals render content via
JavaScript. Standard HTTP requests return empty pages.
Playwright runs a headless Chromium instance to get
fully rendered HTML.

**Why Flutter for the frontend?**  
Single codebase deployable to web, Android, and iOS.
Demonstrates cross-platform capability relevant to
mobile engineering roles.

---

## Local Setup

### Prereqs
- Python 3.12+
- Flutter 3.x
- OpenAI API key

### Backend

```bash
git clone https://github.com/Awanjee/arco-papers-api
cd arco-papers-api
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
playwright install chromium
```

Create `.env`:
```
OPENAI_API_KEY=your_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_or_anon_key
SUPABASE_JWT_SECRET=your_jwt_secret_from_dashboard
GMAIL_ADDRESS=your_gmail@gmail.com
GMAIL_APP_PASSWORD=your_app_password
NOTIFY_EMAIL=your_email@gmail.com
```

`SUPABASE_JWT_SECRET` is under **Project Settings → API → JWT Settings**.
It is **not** the same as `SUPABASE_KEY` (API key). Required for protected routes.

Run:
```bash
uvicorn main:app --reload
```

### Tender Scraper

```bash
python tender_scraper.py
```

Runs immediately then schedules weekly at Monday 8am PKT.

### Frontend

```bash
git clone https://github.com/Awanjee/arco-papers-app
cd arco-papers-app
flutter pub get
flutter run -d chrome
```

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/chat` | No | Send message, get AI response |
| POST | `/quote` | No | Generate and email a quote |
| GET | `/quotes/history` | Bearer JWT | List quotes for logged-in client |
| POST | `/orders` | Bearer JWT | Create order from `quote_id` |
| GET | `/health` | No | Health check |

### Chat Request
```json
{
  "message": "Price for 7500 C4 envelopes?",
  "session_id": "session_abc123"
}
```

### Chat Response
```json
{
  "response": "For 7,500 C4 envelopes the price is PKR 7.0
               per unit — total PKR 52,500.",
  "session_id": "session_abc123"
}
```

---

## Project Structure
arco-papers-api/
├── main.py              # FastAPI app, routes, CORS
├── agent.py             # LangChain agent, tools, RAG
├── tender_scraper.py    # Scraper, scorer, email digest
├── requirements.txt
└── .env                 # Not committed

---

## What I Learned Building This

- **RAG architecture** — chunking strategy, embedding
  models, retrieval tuning
- **LangChain LCEL** — chain composition with the pipe
  operator, RunnablePassthrough, itemgetter patterns
- **Agent tool design** — writing tool docstrings that
  guide LLM tool selection accurately
- **Async Python** — asyncio, concurrent scraping with
  gather(), APScheduler for cron jobs
- **Production constraints** — ephemeral filesystems on
  free hosting, CORS configuration, environment
  variable management

---

## Author

**Muhammad Usama Awan**  
Flutter & .NET Developer | AI Integration  
📧 usamaawan925@gmail.com  
🔗 [LinkedIn](https://linkedin.com/in/muhammad-usama-awan)  
🐙 [GitHub](https://github.com/Awanjee)