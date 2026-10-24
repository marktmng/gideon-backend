# Gideon Backend Service — Phase 2: Real AI Brain & Context-Aware Memory

FastAPI backend service powering Gideon, a personal AI assistant inspired by Gideon from DC's *Legends of Tomorrow*.

Phase 2 upgrades Gideon from a simulated assistant into a genuine AI-powered assistant with Google Gemini integration, Server-Sent Events (SSE) streaming, context-aware conversation history, bounded memory retrieval, and runtime diagnostics.

---

## 1. Phase 2 Features

- **Google Gemini Provider**: Built with Google's official `google-genai` Python SDK (`from google import genai`).
- **Pluggable AI Architecture**: Clean provider abstraction via `BaseAIProvider` and `AIProviderFactory`. `DemoAIProvider` remains available for offline development without API credentials.
- **SSE Streaming Responses**: Real-time token/delta streaming over HTTP POST (`POST /api/v1/conversations/{id}/messages/stream`) with documented event sequence (`start`, `delta`, `complete`, `error`).
- **Persistent Neural Memory System**: SQLAlchemy-backed `memories` table with full CRUD endpoints (`/api/v1/memories`) and bounded keyword-based context retrieval.
- **Untrusted Memory Isolation**: Saved memories are strictly sandboxed as reference data in prompts and prevented from overriding core system instructions.
- **Sanitized Error & Security Controls**: API keys and secrets are never logged, returned in responses, or exposed to the frontend. Provider errors (rate limits, timeouts, auth failures) map to structured domain exceptions.
- **Automated Offline Testing**: Full pytest test suite with 50 passing tests that run completely offline with mock providers.

---

## 2. Configuration & AI Provider Setup

All backend settings are loaded from `gideon-backend/.env` using Pydantic Settings.

### Safe Default: Demo Mode (Offline)
Fresh installations default to:
```env
AI_PROVIDER=demo
```
In demo mode, Gideon generates simulated responses locally with zero network calls and no external API keys required.

### Enabling Google Gemini

1. **Obtain an API Key**:
   Visit [Google AI Studio](https://aistudio.google.com/) and create a free or paid API key.
   > **Note on Antigravity Subscriptions:** Having a Google Antigravity IDE subscription does **not** automatically grant API keys or API credits for external applications. You must generate dedicated API credentials via Google AI Studio.

2. **Configure `.env`**:
   Copy `.env.example` to `.env` (if not already done):
   ```powershell
   Copy-Item .env.example .env
   ```
   Update `.env`:
   ```env
   AI_PROVIDER=gemini
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   AI_MODEL=gemini-2.5-flash
   AI_REQUEST_TIMEOUT_SECONDS=60
   AI_MAX_CONTEXT_MESSAGES=20
   AI_MAX_OUTPUT_TOKENS=1024
   AI_TEMPERATURE=0.7
   MEMORY_MAX_RETRIEVAL_COUNT=5
   ```

3. **Supported Gemini Models**:
   - `gemini-2.5-flash` (Recommended default: fast, cost-effective, multimodal)
   - `gemini-3.7-flash` (Advanced reasoning & coding performance)
   - `gemini-3.5-flash-lite` (Ultra-fast, lowest latency)

---

## 3. Running Locally (Windows PowerShell)

```powershell
# Navigate to backend directory
cd c:\Mark\Gideon\gideon-backend

# Ensure dependencies are installed
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Run database migrations
.\.venv\Scripts\alembic.exe upgrade head

# Launch backend with convenience script
.\run.bat
# Alternatively:
.\.venv\Scripts\python.exe run.py
```
The server will start on `http://127.0.0.1:8000`.

---

## 4. Running Tests

The test suite runs with isolated test databases and mock AI providers. No API keys or internet connection are required.

```powershell
.\.venv\Scripts\pytest.exe -v
```

---

## 5. API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | System health check |
| `GET` | `/api/v1/health` | Versioned health check |
| `GET` | `/api/v1/assistant/status` | Assistant diagnostics, active provider, model, capabilities |
| `GET` | `/api/v1/conversations` | List conversation sessions (paginated) |
| `POST` | `/api/v1/conversations` | Create a new conversation session |
| `GET` | `/api/v1/conversations/{id}` | Get conversation metadata |
| `PATCH` | `/api/v1/conversations/{id}` | Update conversation title |
| `DELETE` | `/api/v1/conversations/{id}` | Delete conversation and cascade messages |
| `GET` | `/api/v1/conversations/{id}/messages` | List conversation messages |
| `POST` | `/api/v1/conversations/{id}/messages` | Submit user message and receive non-streaming assistant reply |
| `POST` | `/api/v1/conversations/{id}/messages/stream` | Submit user message and stream assistant reply via SSE |
| `GET` | `/api/v1/memories` | List persistent memories (supports `category` and `search` query) |
| `POST` | `/api/v1/memories` | Create a persistent memory directive |
| `GET` | `/api/v1/memories/{id}` | Retrieve a memory by ID |
| `PATCH` | `/api/v1/memories/{id}` | Update memory key, content, or category |
| `DELETE` | `/api/v1/memories/{id}` | Delete a persistent memory |
| `GET` | `/api/v1/tasks` | List mission tasks with status filter |
| `POST` | `/api/v1/tasks` | Create a new task directive |
| `PATCH` | `/api/v1/tasks/{id}` | Update task status or priority |
| `DELETE` | `/api/v1/tasks/{id}` | Delete a task |

---

## 6. SSE Streaming Protocol

Endpoint: `POST /api/v1/conversations/{conversation_id}/messages/stream`

Events emitted in sequence:
1. `event: start`
   Payload: `{"conversation_id": "...", "user_message": {...}, "relevant_memories_count": 2}`
2. `event: delta`
   Payload: `{"delta": "text token fragment"}`
3. `event: complete`
   Payload: `{"conversation_id": "...", "assistant_message": {...}}`
4. `event: error` (on failure)
   Payload: `{"detail": "Error description", "error_type": "AIProviderError"}`

If an error occurs before streaming begins (e.g. 404 Conversation Not Found or 400 Empty Content), a standard HTTP error response is returned instead of an SSE stream.

---

## 7. Troubleshooting

- **503 Service Unavailable / AIConfigurationError**: You selected `AI_PROVIDER=gemini` but `GEMINI_API_KEY` is empty or missing in `.env`.
- **429 Too Many Requests / AIRateLimitError**: Gemini API rate limit or project quota has been reached. Wait a minute or check your quota in Google Cloud Console.
- **504 Gateway Timeout / AIProviderTimeoutError**: Gemini generation exceeded `AI_REQUEST_TIMEOUT_SECONDS` (default: 60s). Check network connectivity.
- **Database Locked (SQLite)**: Ensure multiple test runners or processes are not holding exclusive write locks simultaneously.
