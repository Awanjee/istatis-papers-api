# arco-papers-app

Flutter frontend for the Arco Papers AI platform. Web-first, connects to the Python/LangGraph backend. Being built in parallel with the backend as a real product with real business use cases.

## What this is

The client-facing layer for an AI-powered business management platform for Arco Papers, a paper manufacturing business in Islamabad, Pakistan. The app will expose AI-driven tools — quotation generation, payment status, price queries — to business staff and eventually customers.

This is also a deliberate portfolio project: the stack is chosen to demonstrate Flutter beyond mobile, including Flutter Web and integration with a Python AI backend.

## Stack

- **Flutter / Dart** — web target (desktop and mobile planned)
- **State management** — Provider (migrating to Riverpod)
- **Backend** — [arco-papers-api](https://github.com/Awanjee/arco-papers-api) (Python, LangChain, LangGraph)

## What's planned

- Landing page at root (`/`) — public-facing business website
- AI portal at `/portal` — internal tools for staff
  - Payment status dashboard
  - Quotation generator
  - WhatsApp message history

## Background

Three years building production Flutter apps at Compare The Market (Brisbane, Australia) — iOS and Android, tens of thousands of users. This project extends that into Flutter Web and AI-integrated product development.

## Related

- Backend: [arco-papers-api](https://github.com/Awanjee/arco-papers-api)
