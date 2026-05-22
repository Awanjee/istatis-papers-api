# Arco Papers — Session Handover
*Generated end of long session — verify against actual 
code before trusting*

## Current state summary
Full-stack AI platform for Arco Papers (family paper 
business, Islamabad PK). Two repos, both deployed and 
working in production.

## Repos
- Flutter: `C:\Usama\Projects\arco_papers_app`
  - Firebase: https://arco-papers-app-6b721.web.app
  - GitHub: github.com/Awanjee/arco-papers-app
- API: `C:\Usama\Projects\arco-papers`
  - Render: https://arco-papers-api.onrender.com
  - GitHub: github.com/Awanjee/arco-papers-api

## Tech stack
- Flutter web (Provider, Dio, Google Fonts)
- FastAPI + Python 3.12
- LangChain 1.4+ with langchain-classic
  (create_tool_calling_agent, AgentExecutor)
- OpenAI gpt-4o-mini
- ChromaDB (in-memory, rebuilt on startup)
- Supabase (PostgreSQL) — products, pricing_tiers,
  clients, quotes, orders, tenants, categories
- Firebase Hosting (frontend)
- Render free tier (backend — cold starts after 15min)
- UptimeRobot recommended to keep Render awake

## Key import fixes (LangChain 1.4+)
These moved — don't revert:
```python
from langchain_classic.agents import (
    create_tool_calling_agent, AgentExecutor
)
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter
)
from langchain_core.tools.retriever import (
    create_retriever_tool
)
from langchain_chroma import Chroma
```

## Flutter app structure
lib/
main.dart
models/
message.dart
product.dart
quote_request.dart  # QuoteRequest, QuoteResponse
data/
products_data.dart  # hardcoded fallback,
# not used for quotes
services/
api_service.dart    # sendMessage(), requestQuote()
providers/
chat_provider.dart
screens/
home_screen.dart    # bottom nav: chat/catalogue/quote
catalogue_screen.dart
quote_screen.dart   # 3-tab form with success screen
widgets/
chat_bubble.dart
chat_input.dart
suggestion_chips.dart

## API structure
arco-papers/
main.py          # FastAPI, /chat, /quote, /health
agent.py         # LangChain agent, tools,
# build_agent(), chat(),
# generate_quote()
database.py      # Supabase client, all DB functions
tender_scraper.py # Playwright scraper, APScheduler,
# Gmail digest
requirements.txt
.env             # never commit

## Supabase schema
Tables: tenants, categories, products, pricing_tiers,
clients, quotes, orders, order_items

- tenant_id on all tables (multi-tenancy ready)
- Arco Papers is the only tenant currently
- RLS disabled for now
- Products and pricing loaded from DB dynamically
  (not hardcoded anymore)
- Quotes saved on every /quote request
- Clients upserted by email on quote save

## Environment variables needed
### Render + local .env
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
NOTIFY_EMAIL=
PYTHON_VERSION=3.12.0

## What's working in production
- /chat — RAG agent with tool-calling, session memory
- /quote — generates quote via LangChain, saves to 
  Supabase, sends 2 emails (customer + Arco Papers)
- /health — {"status":"ok","sessions":N}
- Flutter: chat tab, catalogue tab, quote tab
- Tender scraper — scrapes PPRA, Pakistan Post, 
  TenderService.pk weekly, scores with LLM, 
  emails digest (run manually or Monday 8am PKT)

## Known issues / watch out for
- Render cold start kills demos — ping /health 
  2-3 min before showing anyone
- api_service.dart has TWO urls — local and render.
  Easy to accidentally deploy with wrong one.
  Production should be Render URL.
- quote_screen.dart uses _selectedProductName 
  (not _selectedProductType — old name caused bugs)
- send_quote_email uses quote['product_name'] 
  (not product_type — caused KeyError previously)
- LangChain version is sensitive — do not upgrade
  without testing all agent functionality

## Next sprint — Sprint 2: Client Authentication
This is the next thing to build. Plan:

1. Supabase Auth — email/password
   - Enable in Supabase dashboard → Authentication
   - Add supabase_flutter package to Flutter
   
2. New Flutter screens needed:
   - login_screen.dart
   - signup_screen.dart  
   - client_dashboard_screen.dart
   
3. Auth flow:
   - App opens → check if logged in
   - If not → show login screen
   - If yes → show main app (chat/catalogue/quote)
   - Quote requests automatically linked to 
     logged-in client

4. Client dashboard:
   - List of past quotes with status
   - Reorder button on each quote
   - Basic account info

5. Backend changes needed:
   - /quotes/history endpoint — returns quotes 
     for authenticated client
   - /orders endpoint — place order from quote
   - Supabase JWT verification on protected routes

## Pending business tasks (separate track)
- Real product catalogue with actual prices 
  (Usama will provide)
- PPRA vendor registration
- B2B outreach to hospitals/universities
- Google Business Profile photos
- Logo needed for all platforms

## Job search status
- LinkedIn optimized, Open to Work set
- Applied to Turing.com (vetting in progress)
- Applied to Toptal (on waitlist)
- Some LinkedIn applications sent, 
  couple of generic rejections
- Resume versions:
  - General: MUHAMMAD_USAMA_AWAN_Resume.pdf
  - Flutter-targeted: 
    MUHAMMAD_USAMA_AWAN_Flutter_Resume.pdf

## How to start next session
1. cd to relevant repo
2. activate venv (API): venv\Scripts\activate
3. start backend: uvicorn main:app --reload
4. start flutter: flutter run -d chrome
5. verify /health returns ok
6. state single task for the session

## Usama's preferences (from profile.md)
- Implementation first, theory on request
- No long preambles
- Focused diffs, no drive-by refactors
- Flag when to push back on AI suggestions
- Rate tools 1-10
- Map Python concepts to C# equivalents
- Direct, technical, probability estimates