# Personal Assistant 

A full-stack, multi-user AI assistant built with **FastAPI**, **React**, **PostgreSQL**, and **LangGraph**. It turns a LangGraph notebook workflow into a usable web application: people can register, chat with a specialist-agent team, review actions that need approval, and return to their saved conversations later.

The system routes each request to the right specialist, runs independent work in parallel when possible, and combines the results into one clear response. Administrators can also inspect the agent execution trace behind every chat turn.

## What it can do

- Create accounts and sign in with JWT authentication.
- Keep each user's conversations and messages in PostgreSQL.
- Route requests to a LangGraph team of specialist agents:
  - classify and draft emails;
  - extract structured information;
  - summarize text;
  - answer questions using vector-memory retrieval;
  - research papers on arXiv;
  - search flight options and prepare bookings.
- Ask for human approval before sending a drafted email or confirming a flight booking.
- Resume an interrupted workflow after a server restart through Postgres-backed LangGraph checkpoints.
- Provide an admin panel for users, conversations, and per-node execution traces.

## Contents

```text
.
├── backend/                FastAPI application and LangGraph agents
│   └── app/
│       ├── agent/          Graph, workers, tools, memory, and checkpoints
│       ├── controllers/    HTTP endpoints
│       ├── services/       Application business logic
│       ├── repositories/   Database access layer
│       └── models/         SQLAlchemy models
├── frontend/               React chat and admin interface
├── docker-compose.yml      Full local stack
└── .env.example            Environment-variable template
```

## Quick start (Docker)

1. Copy the env file and fill in your Gemini API key:

   ```bash
   cp .env.example .env
   # edit .env -> GEMINI_API_KEY=...
   ```

2. Build and run everything:

   ```bash
   docker compose up --build
   ```

3. Open the app:
   - Frontend: http://localhost:5173
   - Backend API docs (Swagger): http://localhost:8000/docs

4. Register a normal account from the UI, or register an **admin**
   account by filling the "Admin code" field with the value of
   `ADMIN_REGISTRATION_CODE` from your `.env`.

Postgres data (users, conversations, messages, node-execution logs, and
the LangGraph checkpoints that make human-in-the-loop pause/resume
survive a restart) persists in the `postgres_data` Docker volume.

## Running locally without Docker

**Backend**
```bash
cd backend
python -m venv .venv 
source .venv/bin/activate (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
export $(cat ../.env | xargs)     # or set the vars manually
uvicorn app.main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

## What the agent does

Every chat message goes through the same graph as the notebook:

1. **orchestrator** — one LLM call decomposes the message into zero or
   more subtasks, each tagged with the worker that should handle it.
2. **dispatch (`Send`)** — subtasks fan out to worker nodes/subgraphs in
   parallel.
3. **7 workers** — `email_classify`, `email_write` (self-critique loop +
   human review), `extract_info` (router + parallel refinement),
   `summarize`, `qa` (RAG over an in-memory vector store), `flight_booking`
   (ReAct tool loop + booking confirmation), `research_assistant` (arXiv
   search).
4. **aggregator** — merges every worker's result into one reply.

Two workers can **pause the whole graph** and hand control back to the
user: `email_write` (approve / request changes / reject a drafted email)
and `flight_booking` (confirm / cancel before actually booking a flight).
The frontend renders these as buttons via the `pending_interrupt` field
on the chat response; resuming calls `POST /chat/resume`.

## Admin panel

Any user registered with the correct admin code can open **Admin panel**
from the sidebar to see:
- every user and how many conversations they have,
- every conversation across all users,
- for each conversation, the full **node-execution trace**: which graph
  node fired, in what order, and its output.


## Environment variables

See [`.env.example`](.env.example) for the full list. The important ones:

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key used by every LLM/embedding call |
| `SECRET_KEY` | JWT signing secret — change in production |
| `ADMIN_REGISTRATION_CODE` | Shared secret that grants `is_admin=true` on register |
| `DATABASE_URL` | App database (users/conversations/messages/logs) |
| `CHECKPOINTER_DATABASE_URL` | LangGraph checkpoint store (interrupt/resume state) |
