# MyNaksh — Personalized Astrology Chat with a Shared Brain

A FastAPI service for a personal astrology chat. It keeps **short-term conversation context**
and a persistent **Shared Brain** (a Neo4j graph) holding useful long-term facts about each user.
On every message it picks only the relevant context, calls a swappable LLM, and decides what to
remember.

```
Chat → Understand query → Select relevant context (Shared Brain + session) → Build LLM context → LLM → Response → Update memory
```

---

## 1. Quick start (about 5 minutes)

**Requirements:** Docker with Docker Compose v2.24 or later. Python 3.10+ is only needed to run the tests locally.

```bash
git clone https://github.com/sameerkosurkar/mynaksh-shared-brain.git
cd mynaksh-shared-brain
cp .env.example .env          # then set an LLM key (see below), or leave LLM_PROVIDER=mock
docker compose up --build     # starts Neo4j 5 + the API
```

| What | URL |
|---|---|
| Swagger UI (try every endpoint) | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Neo4j Browser (user `neo4j`, password `mynaksh-dev-password`) | http://localhost:7474 |

Then, in another terminal, run the assignment's example conversation from start to finish:

```bash
./scripts/demo.sh             # prints each reply, context_used and memory_updates, then the user's graph
```

> Port 8000 already in use? Run `APP_PORT=8001 docker compose up --build` and `BASE_URL=http://localhost:8001 ./scripts/demo.sh`.

### Configure an LLM
Edit `.env` and set **one** provider. No key is committed to this repo; use your own.

| Provider | Get a key | `.env` |
|---|---|---|
| Google Gemini (free tier) | https://aistudio.google.com/apikey | `LLM_PROVIDER=gemini`<br>`GEMINI_API_KEY=...` |
| OpenAI | https://platform.openai.com/api-keys | `LLM_PROVIDER=openai`<br>`OPENAI_API_KEY=...` |
| Anthropic | https://console.anthropic.com/settings/keys | `LLM_PROVIDER=anthropic`<br>`ANTHROPIC_API_KEY=...` |
| None | – | `LLM_PROVIDER=mock` (default) |

After changing `.env`, restart with `docker compose up -d --force-recreate app`. Then check
`GET /health`: `llm_provider` shows which model is answering. Every chat response also carries
`llm_provider`, so you can always tell whether a real model answered.

The **mock** provider is a deterministic, offline stand-in. It builds answers only from the
context the pipeline selected. This lets the whole system (memory, context selection, graph, tests)
run and be judged without a key. With a real key, the same context goes to the real model.

### Run the tests (no Docker or key needed)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q                # 71 tests; the Neo4j integration tests run when Neo4j is up, otherwise they are skipped
.venv/bin/python -m eval.memory_eval
```

### Run without Docker for the API
```bash
docker compose up -d neo4j                        # or set GRAPH_BACKEND=memory in .env to skip Neo4j
.venv/bin/uvicorn app.main:app --reload --port 8000
```

---

## 2. Architecture

```
                 ┌────────────────────────────── ChatService.chat() ──────────────────────────────┐
POST /chat ──▶   │ 1. Understand query      RuleExtractor (facts in msg) + analyze() → intent, life areas │
                 │ 2. Select context        Shared Brain query by area  +  short-term session window    │
                 │                          ContextSelector: rank, filter, token budget                 │
                 │ 3. Build LLM context     prompt_builder: system rules + profile + memories + turns   │
                 │ 4. Generate              FallbackLLM: primary provider → retries → mock fallback     │
                 │ 5. Short-term update     ShortTermMemory (last N msgs + rolling summary)              │
                 │ 6. Long-term update      MemoryUpdater: create / reinforce / supersede / abandon      │
                 └───────────────────────────────────────────────────────────────────────────────────────┘
                         │                                    │
                ┌────────▼─────────┐                ┌─────────▼─────────┐
                │ GraphStore       │                │ LLMProvider       │
                │  Neo4jGraphStore │                │  Gemini / OpenAI  │
                │  InMemory (tests,│                │  Anthropic / Mock │
                │   fallback)      │                └───────────────────┘
                └──────────────────┘
```

```
app/
├── api/            routes.py (HTTP), schemas.py (validation)
├── chat/           query_understanding.py, context_selector.py, prompt_builder.py, service.py (pipeline)
├── brain/          models.py, store.py (interface, in-memory, resilient wrapper), neo4j_store.py
├── memory/         extractor.py (what to remember), updater.py (how to store/update), short_term.py
├── llm/            base.py (interface), providers.py, mock.py, fallback.py (retry + provider chain)
├── profile/        astrology.py (sun sign + attributes, stubbed)
├── lexicon.py      life-area vocabulary shared by query understanding and extraction
├── config.py       all settings via env / .env
└── main.py         wiring, error handlers
tests/              scenarios, extractor, context selection, error handling, Neo4j integration
eval/               offline memory-extraction and context-relevance evaluation
scripts/demo.sh     the assignment's conversation via curl
samples/            captured real requests/responses
```

### API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/chat` | Main endpoint. Request and response follow the assignment, with extra fields (below) |
| `POST` | `/users` | Create or update a user with a profile (optional; `/chat` auto-creates users) |
| `PATCH` | `/users/{id}/profile` | Partial profile update (same update rules as chat: history kept, zodiac recomputed) |
| `GET` | `/users/{id}` | Profile + computed astrology + missing fields |
| `GET` | `/users/{id}/brain` | The user's sub-graph: relationships, supersede links, profile history, sessions |
| `DELETE` | `/users/{id}` | Right to be forgotten: removes the user and all their memories |
| `GET` | `/health` | Graph and LLM status |

`/chat` response extensions: `context_details` (what was injected, with scores), `memory_updates`
(what was stored and why), `intent`, `life_areas`, `missing_profile_fields`, `llm_provider`/`llm_model`,
`degraded`, `brain_available`, `warnings`, `latency_ms`.

---

## 3. Shared Brain — graph schema

### Entities (nodes)
| Label | Key properties | Notes |
|---|---|---|
| `User` | `user_id`, `name`, `date_of_birth`, `time_of_birth`, `birth_place`, `preferred_language` | Profile fields live on the user node. Each is 1:1 and always needed. |
| `ZodiacSign` | `name`, `element`, `ruling_planet` | Shared node. Many users point to the same `Leo`. |
| `Memory:Goal` | `title`, `status`, `attr_timeframe`, `attr_target_year` / `attr_target_month` | e.g. Career Change → 2027 |
| `Memory:Interest` | `title` | e.g. Entrepreneurship, Yoga |
| `Memory:Preference` | `title`, `attr_type` | e.g. language = Hindi, response style = concise |
| `Memory:LifeEvent` | `title`, `attr_when` | important memories: promotion, marriage, bereavement |
| `Memory:Concern` | `title` | ongoing worries: health, finances |
| `LifeArea` | `name` | career, relationships, health, finance, education, family, spirituality, travel, personal |
| `Session` | `session_id`, `summary`, `turns`, `last_active` | Conversation summaries, used for "what did we talk about" |
| `ProfileHistory` | `field`, `old_value`, `new_value`, `changed_at` | Audit trail of profile corrections |

Every `Memory` node also carries `key` (a canonical identity such as `goal:career_change`),
`confidence`, `importance`, `mention_count`, `source_text`, `created_at` and `updated_at`.

### Relationships
```
(User)-[:HAS_ZODIAC]->(ZodiacSign)
(User)-[:HAS_GOAL]->(Goal)              (User)-[:INTERESTED_IN]->(Interest)
(User)-[:PREFERS]->(Preference)         (User)-[:EXPERIENCED]->(LifeEvent)
(User)-[:CONCERNED_ABOUT]->(Concern)    (User)-[:HAD_SESSION]->(Session)
(User)-[:HAD_PROFILE_VALUE]->(ProfileHistory)
(Memory)-[:ABOUT]->(LifeArea)           # what part of life a memory concerns
(Memory)-[:SUPERSEDES]->(Memory)        # a correction; the old node is kept with status=superseded
```

This is Neo4j after running `scripts/demo.sh` (real output):
```
rel, node, status, target, area
"HAS_GOAL", "Career Change", "active", "2028", "career"
"HAS_GOAL", "Product Management Interview", "active", "2026-11", "career"
"HAS_GOAL", "Career Change", "superseded", "2027", "career"      ← corrected by the user; kept for history
"HAS_ZODIAC", "Leo", NULL, NULL, NULL
```
Try it in the Neo4j Browser: `MATCH p=(u:User)-[*1..2]->() RETURN p`.

### How information is retrieved
1. The query is mapped to **life areas** (e.g. "What should I focus on for my career?" → `career`).
2. A Cypher traversal fetches only active memories in those areas:
   `MATCH (:User {user_id:$uid})-->(m:Memory)-[:ABOUT]->(a:LifeArea) WHERE m.status IN $statuses AND a.name IN $areas …`
3. The results are ranked by `0.5·importance + 0.3·confidence + 0.2·recency`. Recency has a 90-day half-life, and a goal whose target year has passed is down-weighted (decay).
4. The profile and zodiac come from the `User` node and its `HAS_ZODIAC` edge.

Constraints and indexes: unique `User.user_id`, `Memory.id`, `LifeArea.name`, `ZodiacSign.name` and `Session.key`
(sessions are keyed per user), plus an index on `(Memory.key, Memory.status)` for update lookups.

### Why this design
* **A typed node per memory, not a JSON blob on the user.** Each fact can be queried, updated, scored
  and audited on its own. The relationship type (`HAS_GOAL`, `PREFERS` …) reads exactly like the
  assignment's examples.
* **`LifeArea` as a hub.** Context selection becomes a one-hop graph filter instead of keyword search
  over every memory. It also leaves room for cross-user analytics, e.g. which areas users care about most.
* **`SUPERSEDES` instead of overwrite.** Corrections never lose history. The system can explain
  "you earlier said 2027" and recover from a bad extraction.
* **Canonical `key` per fact** (`goal:career_change`). "Switch jobs", "change my job" and
  "new job" collapse into one memory, so repeats reinforce it instead of duplicating it.
* **Shared `ZodiacSign` / `LifeArea` nodes.** Static astrology attributes are stored once, and new
  astrology entities (nakshatra, planets, dasha) can be attached later without changing user data.

---

## 4. Memory strategy

| | Short-term context | Long-term memory (Shared Brain) |
|---|---|---|
| Holds | Last 6 messages verbatim + a rolling summary of older turns | Durable facts about the user |
| Scope | One `(user_id, session_id)` | All sessions, forever (until corrected or deleted) |
| Store | In process, behind `ShortTermMemory` (Redis in production) | Neo4j |
| Used for | Follow-ups ("Why do you say that?"), pronouns, flow | Personalisation, recall across conversations |

### What is remembered
The mechanism is a **hybrid**. A deterministic `RuleExtractor` always runs. An `LLMExtractor` also runs
when a real LLM is configured and the message is a statement worth the cost.
* **Profile:** name, date/time/place of birth, preferred language. A date of birth automatically creates the `HAS_ZODIAC` edge.
* **Goals with timeframes:** "next year" is resolved to `target_year` (2027 when today is 2026) and "next month" to `target_month`.
  Tentative wording ("maybe", "thinking of") lowers confidence.
* **Interests, preferences** (language, answer style), **life events** (promotion, marriage, loss) and **concerns**.

### What is NOT remembered
* Questions, greetings, thanks ("What should I focus on?", "Why?", "Thanks!")
* Hypotheticals ("What if I quit my job?")
* Other people's plans ("My friend wants to start a business")
* Requests for information ("I want to know what the stars say")
* Temporary states and vague statements with no life area ("I'm tired today", "I like that")
* **PII:** phone numbers, emails, Aadhaar/card numbers and PAN are redacted before anything is stored.
* Candidates below `MIN_MEMORY_CONFIDENCE` (0.5). Facts proposed only by the LLM are capped at 0.8 confidence.

### How memories are represented
As typed graph nodes (see the schema), with `confidence` (how sure we are), `importance` (how useful
it is), `mention_count`, `status` (`active` / `superseded` / `abandoned`) and `source_text` (the
redacted sentence it came from, so every memory can be explained).

### How existing memories are updated
| Situation | Example | Action |
|---|---|---|
| New fact | "I'm planning to switch jobs next year" | `created` |
| Same fact again | repeated in a later session | `reinforced`: mention_count+1, confidence up |
| Conflicting detail | "Actually I plan to switch jobs in 2028, not next year" | `updated`: new node `SUPERSEDES` the old one |
| Plan dropped | "I'm no longer planning to switch jobs" | `abandoned`: kept, but excluded from context |
| Profile correction | "Actually I was born in Mumbai, not Delhi" | `corrected`: overwritten + `ProfileHistory` node; zodiac recomputed if DOB changes |

Near-duplicate titles within the same kind and area (token Jaccard ≥ 0.6) are treated as the same memory.
Every chat response lists what was stored in `memory_updates`, so memory behaviour is fully visible.

---

## 5. Context selection

The goal is to send the LLM **only what helps answer this message**, never the whole graph or the whole history.

| Intent (rule-based classifier) | Long-term memories sent | Short-term |
|---|---|---|
| `smalltalk` ("Hi", "Thanks") | none (name only) | – |
| `advice` with a life area | only memories `ABOUT` that area | recent turns |
| `advice` without an area | at most the top 3 high-importance memories | recent turns |
| `followup` ("Why do you say that?") | **the exact memories used for the previous answer** (stored in the turn metadata) | recent turns (always) |
| `recall` ("What do you remember…") | everything in the asked area (all areas if none named) + previous-session summaries | – |
| `share_info` ("My name is…") | memories in the mentioned area + the new facts being saved | recent turns |

Other rules:
* **Birth details** (DOB, time, place) are included only when the question is about astrology (kundli, chart, sign …). The sun sign and its traits are included for advice.
* **Token budget** (`MAX_CONTEXT_TOKENS`, default 1200): the oldest turns are dropped first, then the lowest-scored memories.
* **Missing data** goes into the prompt as "Not yet known: …". The model is told to ask for it rather than guess, and the response lists `missing_profile_fields`.

---

## 6. LLM layer

`LLMProvider.generate(LLMRequest) -> LLMResponse` is the only interface the app depends on.
`GeminiProvider`, `OpenAIProvider` (any OpenAI-compatible server through `OPENAI_BASE_URL`, e.g. Ollama or vLLM),
`AnthropicProvider` and `MockProvider` each use plain `httpx` (no vendor SDKs), about 30 lines per provider.
`FallbackLLM` retries retryable errors (timeouts, 429, 5xx) with backoff, then falls back to the next provider.
Switching provider is a one-line `.env` change.

The prompt contains: system rules (no invented facts, astrology framed as guidance, explain reasoning on
"why", respond in the preferred language), the compact profile and sun sign, the selected memories, the
new facts from this message, the session summary, and then the recent turns plus the current message as chat messages.
**Hindi or other languages:** the user's `preferred_language`, or Devanagari input, sets the response language.

---

## 7. Error handling

| Failure | Behaviour |
|---|---|
| Invalid input (empty or oversized message, bad IDs, future DOB, bad time) | `422 {"error": "invalid_input", "details": [...]}` |
| Unknown user on `/chat` | Auto-created (`warnings: ["new_user"]`). Profile endpoints return 404 |
| Missing profile information | Still answers; `missing_profile_fields` is returned and the model asks for the missing details |
| LLM failure | Retries, then the fallback provider (`degraded: true`). If every provider fails, a polite fallback reply is returned (`llm_unavailable`) and **memory is still saved** |
| Neo4j failure | `ResilientGraphStore` switches to an in-memory store and opens a circuit breaker for 30 s, so an outage does not add a connection timeout to every request. Chat keeps working with `brain_available: false`, and `/health` reports `degraded` |
| Empty memory / no relevant context | The model answers generally and says honestly that nothing is stored (`no_relevant_memory`) |
| Any unexpected exception | `500 {"error": "internal_error"}`, logged with a stack trace, no internals leaked |

---

## 8. Testing & evaluation

`pytest -q` runs **71 tests**. They use the in-memory graph and the mock LLM, so they need no network.
The Neo4j integration tests run automatically when Neo4j is reachable.

| # | Scenario (assignment list) | Test |
|---|---|---|
| 1 | New user | `test_new_user_is_created_and_asked_for_missing_details` |
| 2 | Creating a long-term memory | `test_intro_message_creates_profile_zodiac_and_goal`, `test_pm_interview_goal_with_timeframe` |
| 3 | Retrieving a memory | `test_career_question_uses_goal_and_profile` |
| 4 | Follow-up question | `test_followup_uses_short_term_context` |
| 5 | New session using previous information | `test_new_session_recalls_long_term_memory` |
| 6 | Irrelevant memory | `test_irrelevant_memories_are_excluded_from_context`, `test_small_talk_and_other_peoples_plans_are_not_remembered` |
| 7 | User correcting existing information | `test_correcting_profile_keeps_history_and_recomputes`, `test_correcting_goal_supersedes_old_version`, `test_abandoned_goal_is_no_longer_used`, `test_repeated_fact_is_reinforced_not_duplicated` |
| 8 | Missing user information | `test_missing_birth_details_are_flagged_and_requested`, `test_empty_memory_recall_is_honest` |
| – | Error handling | `tests/test_errors.py` (invalid input, LLM failure/fallback/retry, graph outage) |
| – | Unit | `tests/test_extractor.py`, `tests/test_context_selector.py`, `tests/test_providers.py` (provider adapters vs stubbed HTTP), `tests/test_hybrid_extraction.py` |
| – | Real Neo4j | `tests/test_neo4j_integration.py` (round trip, supersede, per-user session isolation) |

### How to tell whether the Shared Brain improves responses
`python -m eval.memory_eval` runs a small labelled offline evaluation (it also runs in the test suite as a regression gate):
```
Memory extraction : precision 1.00  recall 1.00  (22/22 messages exact)
Context selection : 6/6 queries had all relevant and no irrelevant memories
```
These sets are small and hand-written alongside the rules, so treat them as regression tests, not a
quality claim. In production I would measure:

| Dimension | Metric | How |
|---|---|---|
| Memory accuracy | Precision/recall of stored facts | Annotate a sample of real conversations each week; diff against what was stored |
| Memory persistence | Recall@session-N | Scripted multi-session conversations: is the fact from session 1 used correctly in session 5? |
| Context relevance | Precision of injected memories; tokens per request | Log `context_details`; LLM-judge or human label "was each item needed?" |
| Irrelevant context | Rate of answers mentioning off-topic memories | LLM judge on (question, context, answer) |
| Personalisation | Pairwise preference, Brain ON vs OFF | Same question with and without context; LLM judge + human spot checks; online A/B (CSAT, follow-up rate, retention) |
| Consistency | Contradiction rate | Judge whether an answer contradicts a stored fact or an earlier turn |
| Corrections | Time-to-correct, repeated-correction rate | Count users who correct the same fact twice: a sign extraction is wrong |

---

## 9. Key design decisions & trade-offs

* **Rules first, LLM second, for extraction and intent.** Rules are free, instant, deterministic and testable, and
  they cover the high-value structured facts (profile, goals with dates). The LLM extractor adds coverage
  for the long tail when a key is configured. Trade-off: rules miss unusual phrasings. That is why the LLM
  layer exists, and why its output is schema-validated and confidence-capped.
* **Facts in the current message are understood before the LLM call but saved after it.** The model can
  use "I was born on…" right away, and persistence still follows the assignment's order (Response → Memory Update).
* **Synchronous memory update.** Simple and consistent: the next request always sees the new memory.
  In production, LLM extraction would move to a queue (see below) to cut latency.
* **Versioning over mutation** (`SUPERSEDES`, `ProfileHistory`): slightly more storage in return for auditability and explainability.
* **The in-memory graph has the same interface as Neo4j.** Tests run in about 2 s with no infrastructure, and it
  doubles as the outage fallback. Trade-off: writes made during an outage are not replayed into Neo4j.
* **Mock LLM.** The system runs and can be assessed without any key; a real provider is one env var away.
* **Stubbed astrology.** Only the tropical sun sign with static attributes is computed. Moon sign and ascendant need an
  ephemeris plus exact time and place; the profile reports whether a full chart *would* be possible.

## 10. Production considerations
* **Short-term memory → Redis** (TTL per `user:session` key) so API pods stay stateless; summarise older turns with the LLM instead of extractively.
* **Asynchronous memory pipeline:** publish `(user_id, message, response)` to a queue. Workers run LLM extraction, dedupe and conflict resolution
  off the request path, and an outbox replays graph writes missed during an outage.
* **Neo4j:** use a cluster or Aura; keep a constraint and index per lookup; cap memories per user (prune by score); scheduled decay jobs
  to archive stale goals; for semantic recall at scale, add vector embeddings on `Memory` nodes (Neo4j vector index) combined with the area filter.
* **Privacy:** PII redaction (done), encryption at rest, a `DELETE /users/{id}` right-to-erasure path (done), consent before storing
  sensitive areas (health), and never logging message bodies at INFO level.
* **Security:** authentication (the user_id must come from a verified token, not the request body), rate limiting per user, and prompt-injection
  hygiene (memories are inserted as data in a separate section, and extracted facts are schema-validated).
* **Observability:** metrics for latency per stage, LLM tokens and cost, fallback rate, circuit-breaker state and memory writes per action;
  traces across the pipeline; `context_details` logged for offline evaluation.
* **Cost and latency:** route cheap intents (smalltalk, recall) to a small model; cache the system prompt; the token budget is already enforced.

## Bonus items implemented
Memory confidence and importance scores · conflict resolution (supersede, abandon) · memory decay (recency half-life, stale goals) ·
conversation summarisation (rolling plus per-session `Session.summary`) · model fallback with retries · context and token budget ·
preferred-language responses (Hindi etc.) · graph traversal via `LifeArea`.

## Sample requests & responses
See [`samples/requests.md`](samples/requests.md) for curl requests with responses, and
[`samples/demo_output.txt`](samples/demo_output.txt) for the full captured output of `scripts/demo.sh`
against the Docker stack (Neo4j + mock LLM).
