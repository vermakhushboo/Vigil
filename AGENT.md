# AGENT.md — Vigil Project Context

## Project Overview

**Vigil** is an autonomous AI incident response agent that:
1. Receives real production alerts from a local Docker environment (ELK + Alertmanager)
2. Autonomously investigates the incident using real tools (Elasticsearch logs, GitHub commits, runbook RAG, past incident memory)
3. Calls the on-call engineer's phone via Twilio
4. Delivers a voice briefing via ElevenLabs TTS
5. Holds a live voice Q&A conversation with the engineer about the incident
6. Stores the resolved incident in memory for future similarity matching

**Tagline:** *An autonomous AI agent that investigates production incidents and calls your on-call engineer for a live voice briefing before they've opened their laptop.*

**Hackathon Track:** Build anything with the Mistral API — agents, tools, products.

---

## Repository Structure

```
vigil/
├── AGENT.md
├── SKILLS.md
├── README.md
├── architecture.png
├── docker-compose.yml
├── .env.example
├── requirements.txt
│
├── infra/                          # Docker + observability stack
│   ├── flask-app/
│   │   ├── Dockerfile
│   │   ├── app.py                  # Flask chaos app
│   │   └── requirements.txt
│   ├── logstash/
│   │   └── pipeline/logstash.conf  # Log shipping config
│   ├── alertmanager/
│   │   └── alertmanager.yml        # Alert rules + webhook config
│   └── nginx/
│       └── nginx.conf
│
├── vigil/                          # Core Python application
│   ├── main.py                     # FastAPI entrypoint
│   ├── config.py                   # Env vars + settings
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── orchestrator.py         # Mistral planning agent with function calling
│   │   └── synthesiser.py          # Mistral briefing generator
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── log_analyser.py         # Elasticsearch log search
│   │   ├── github_finder.py        # GitHub recent commits via API
│   │   ├── runbook_search.py       # HuggingFace RAG on runbooks
│   │   └── incident_search.py      # Past incident similarity search
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── store.py                # Save resolved incident to ChromaDB
│   │   ├── retrieve.py             # Similarity search past incidents
│   │   └── patterns.py             # Detect recurring incidents
│   │
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── tts.py                  # ElevenLabs text-to-speech
│   │   └── stt.py                  # ElevenLabs speech-to-text
│   │
│   ├── phone/
│   │   ├── __init__.py
│   │   ├── outbound.py             # Twilio outbound call trigger
│   │   └── webhook.py              # Twilio conversation handler
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── incidents.py            # POST /incident, GET /incident/{id}
│   │   ├── calls.py                # POST /call/outbound, POST /call/webhook
│   │   ├── runbooks.py             # POST /runbooks/upload
│   │   └── websocket.py            # WS /ws/incident/{id}
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── incident.py             # Pydantic models
│   │
│   └── runbooks/                   # Markdown runbook files
│       ├── cpu-spike.md
│       ├── db-connection.md
│       └── 5xx-errors.md
│
├── ui/
│   └── index.html                  # Single-page dashboard
│
└── demo/
    ├── trigger_500.sh              # Trigger 5xx chaos scenario
    ├── trigger_cpu.sh              # Trigger CPU spike scenario
    ├── trigger_db.sh               # Trigger DB down scenario
    └── demo.sh                     # Run all scenarios sequentially
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| AI Agent / LLM | Mistral API (`mistral-large-latest`) | Orchestration, Q&A, synthesis |
| Embeddings | HuggingFace `sentence-transformers/all-MiniLM-L6-v2` | Embed runbooks + past incidents |
| Vector Store | ChromaDB (local) | Runbook RAG + incident memory |
| Voice TTS | ElevenLabs API | Convert briefings to speech |
| Voice STT | ElevenLabs STT API | Transcribe engineer speech on call |
| Phone Calls | Twilio Programmable Voice | Outbound calls + webhook loop |
| Log Storage | Elasticsearch 8.x | Real log ingestion from containers |
| Log Shipping | Logstash | Pipe container logs to ES |
| Alerting | Alertmanager | Fire webhooks on alert rules |
| Chaos App | Flask | Simulate real production failures |
| Backend | FastAPI (Python 3.11+) | API server |
| Realtime | WebSockets (FastAPI) | Live UI updates |
| UI | Plain HTML + Tailwind CSS | Single-page dashboard |
| Containers | Docker + Docker Compose | Full local infra |

---

## Environment Variables

```env
# Mistral
MISTRAL_API_KEY=

# ElevenLabs
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=          # The voice ID for Vigil's agent voice

# Twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=          # Your Twilio number e.g. +441234567890
ONCALL_PHONE_NUMBER=          # Engineer's real phone number

# Elasticsearch
ELASTICSEARCH_URL=http://localhost:9200

# GitHub (optional, for real commit lookup)
GITHUB_TOKEN=
GITHUB_REPO=                  # e.g. owner/repo-name

# App
APP_BASE_URL=                 # Public URL for Twilio webhooks e.g. via ngrok
PORT=8000
```

---

## Core Agent Logic

### Orchestrator Agent (`agents/orchestrator.py`)

Uses **Mistral function calling** to autonomously decide which tools to invoke.

```python
SYSTEM_PROMPT = """
You are Vigil, an autonomous incident response agent.
When given an incident, you must investigate it thoroughly before briefing the on-call engineer.
You have access to tools: search_logs, get_recent_commits, search_runbooks, search_past_incidents.
Call tools iteratively until you have identified:
1. The root cause or most likely cause
2. When it started
3. Any recent changes (deploys/commits) that may have caused it
4. A relevant runbook or past resolution
Only stop investigating when you have enough context to brief an engineer confidently.
Be concise. Engineers are asleep.
"""
```

The agent loop:
1. Send incident details + system prompt to Mistral with tools defined
2. Mistral returns a `tool_use` response — call the tool, get result
3. Append tool result to messages, call Mistral again
4. Repeat until Mistral returns a `text` response (investigation complete)
5. Pass all findings to the Synthesiser

### Synthesiser Agent (`agents/synthesiser.py`)

Takes all findings and generates a 30-second voice briefing script:

```python
SYSTEM_PROMPT = """
Convert this incident investigation into a clear, spoken briefing for an on-call engineer.
Rules:
- Max 4 sentences
- Start with severity and service affected
- Include the most likely cause
- End with the recommended first action
- Write for spoken audio, not reading. No bullet points, no markdown.
"""
```

### Conversational Q&A (in `phone/webhook.py`)

On every Twilio webhook call (engineer speaks):
1. ElevenLabs STT transcribes audio
2. Append to conversation history
3. Call Mistral with: system prompt + full incident context + conversation history
4. ElevenLabs TTS converts response to audio
5. Return TwiML with audio URL to Twilio

The system prompt for Q&A:
```python
SYSTEM_PROMPT = """
You are Vigil, on a live phone call with an on-call engineer about an active incident.
You have already investigated the incident. Here is everything you know:
{incident_context}

Answer questions concisely — you are speaking, not writing.
No bullet points. Max 2 sentences per answer.
If the engineer says 'thanks', 'got it', 'I'll take it from here', or similar — ask them in one sentence how it was resolved, then say goodbye.
"""
```

---

## Mistral Function Calling — Tool Definitions

These are passed to every Mistral API call in the orchestrator:

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": "Search Elasticsearch for recent error logs. Use this to find what errors are occurring and when they started.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms e.g. 'ERROR cpu memory'"},
                    "time_range": {"type": "string", "description": "Time range e.g. '5m', '15m', '1h'", "default": "10m"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_commits",
            "description": "Get the most recent Git commits to find if a bad deploy caused the incident.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of commits to return", "default": 5}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_runbooks",
            "description": "Search internal runbooks for remediation steps matching this incident type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Incident description to match against runbooks"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_past_incidents",
            "description": "Search historical incidents to find similar past events and how they were resolved.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Incident description to find similar past incidents"}
                },
                "required": ["query"]
            }
        }
    }
]
```

---

## Data Models (`models/incident.py`)

```python
class IncidentStatus(str, Enum):
    RECEIVED = "received"
    INVESTIGATING = "investigating"
    CALLING = "calling"
    IN_CALL = "in_call"
    RESOLVED = "resolved"

class IncidentFindings(BaseModel):
    root_cause: Optional[str]
    started_at: Optional[str]
    last_commit: Optional[str]
    runbook_match: Optional[str]
    past_similar: Optional[str]
    is_recurring: bool = False
    recurrence_count: int = 0

class Incident(BaseModel):
    id: str
    title: str
    severity: str                    # critical, warning, info
    service: str
    raw_logs: Optional[str]
    status: IncidentStatus
    findings: Optional[IncidentFindings]
    briefing_script: Optional[str]
    call_transcript: List[dict]      # [{role, content, timestamp}]
    resolution: Optional[str]        # Captured from engineer at end of call
    created_at: datetime
    resolved_at: Optional[datetime]
```

---

## Memory System (`memory/`)

Uses **ChromaDB** with two collections:
- `runbooks` — embedded runbook markdown files
- `past_incidents` — embedded resolved incident summaries

### Storing an incident (`store.py`)
Called after the engineer confirms resolution on the phone call.

```python
def store_incident(incident: Incident):
    text = f"""
    Title: {incident.title}
    Service: {incident.service}
    Root Cause: {incident.findings.root_cause}
    Last Commit: {incident.findings.last_commit}
    Resolution: {incident.resolution}
    Duration: {duration_mins} minutes
    Transcript summary: {summarise_transcript(incident.call_transcript)}
    """
    collection.add(documents=[text], ids=[incident.id], metadatas=[{...}])
```

### Pattern detection (`patterns.py`)
Query ChromaDB for incidents with same service + similar title. If 3+ found, flag as recurring.

---

## Docker Chaos Scenarios

### Flask chaos app endpoints (`infra/flask-app/app.py`)

```
GET /                    → healthy response
GET /chaos/500           → returns HTTP 500
GET /chaos/cpu           → runs CPU-intensive loop for 30s
GET /chaos/slow-query    → runs a 10s Postgres query
GET /health              → health check endpoint
```

### Alertmanager rules

Three rules that fire to `POST {APP_BASE_URL}/incident`:

1. **5xx Alert** — 5 or more 500 errors in 60 seconds
2. **Container Restart** — any container restarts more than 2 times in 5 minutes
3. **DB Connection** — Postgres container stops responding

---

## API Endpoints

### `POST /incident`
Receives Alertmanager webhook. Validates payload, creates Incident object, triggers agent pipeline asynchronously.

**Request body (Alertmanager format):**
```json
{
  "alerts": [{
    "labels": { "alertname": "High5xxRate", "service": "flask-app", "severity": "critical" },
    "annotations": { "summary": "5xx error rate exceeded threshold" },
    "startsAt": "2025-02-28T14:31:00Z"
  }]
}
```

### `GET /incident/{id}`
Returns full incident object including status, findings, and call transcript.

### `POST /call/webhook`
Twilio hits this on every speech event during the call. Handles full STT → Mistral → TTS loop. Returns TwiML.

### `POST /runbooks/upload`
Accepts markdown file upload. Chunks, embeds, stores in ChromaDB runbooks collection.

### `WS /ws/incident/{id}`
WebSocket connection. Server pushes status updates as the agent progresses through investigation stages.

---

## Twilio Call Flow

```
1. Investigation completes
2. POST /call/outbound → Twilio creates outbound call to ONCALL_PHONE_NUMBER
3. Engineer answers
4. Twilio hits POST /call/webhook with CallStatus=initiated
5. Vigil returns TwiML: <Say> with ElevenLabs audio URL (the briefing)
6. Engineer speaks
7. Twilio hits POST /call/webhook with engineer's speech as audio
8. Vigil: STT → Mistral → TTS → return TwiML with answer audio
9. Repeat steps 6-8 until end-of-call intent detected
10. Vigil asks for resolution, stores it, says goodbye
11. Call ends
```

**Important:** Twilio webhooks require a public URL. Use `ngrok http 8000` during development.

---

## UI Dashboard (`ui/index.html`)

Single HTML file using Tailwind CDN. Three panels:

1. **Incident Feed** — scrolling list of incidents with severity badge, title, time, status
2. **Active Incident Panel** — selected incident showing:
   - Agent status with animated indicator
   - Findings cards (root cause, last commit, runbook, past similar)
   - Recurring incident warning banner (if applicable)
   - Live call transcript (streamed via WebSocket)
   - Call status (Investigating / Calling John / In Call / Resolved)
3. **Config Panel** — on-call name + phone, runbook upload button

WebSocket connection opens on page load, updates incident state in real time.

---

## Build Order

1. `docker-compose.yml` + Flask chaos app + Alertmanager rules
2. FastAPI skeleton + `POST /incident` endpoint
3. Mistral orchestrator agent with 2 fake tools first (logs + commits)
4. Wire real Elasticsearch log search tool
5. Wire real GitHub commits tool
6. ChromaDB + HuggingFace embeddings + runbook RAG tool
7. Past incident memory store + retrieve + patterns
8. ElevenLabs TTS + STT
9. Twilio outbound call + webhook conversation loop
10. WebSocket + UI dashboard
11. README + architecture diagram + demo scripts

---

## Key Implementation Notes

- **Async everything** — FastAPI with `async def`, agent pipeline runs in background task so `/incident` returns immediately
- **Incident state machine** — always update `incident.status` at each stage so WebSocket and UI stay in sync
- **Mistral model** — use `mistral-large-latest` for the orchestrator and Q&A, `mistral-small-latest` is fine for the synthesiser
- **ElevenLabs audio hosting** — Twilio needs a public URL for audio files. Save MP3s to a `/static/audio/` directory served by FastAPI
- **ChromaDB persistence** — initialise with `persist_directory="./chroma_db"` so memory survives restarts
- **ngrok** — required for Twilio webhooks in development. Set `APP_BASE_URL` to your ngrok URL
- **Twilio TwiML** — use `<Gather input="speech">` to capture engineer speech, `<Play>` to serve ElevenLabs audio
- **Error handling** — if any tool fails, the agent should continue with available context rather than crash
- **Conversation history** — keep full message history in the Incident object and pass it all to Mistral on every Q&A turn
