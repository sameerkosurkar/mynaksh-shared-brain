# Sample API requests & responses

Captured from the Docker stack (Neo4j + `LLM_PROVIDER=mock`). With a real LLM key only the `response` text changes;
`context_used`, `memory_updates` etc. are produced by the pipeline, not the model.

## 1. Create a user with a profile (optional)

```bash
curl -X POST http://localhost:8000/users -H 'Content-Type: application/json' \
  -d '{"user_id": "priya-1", "name": "Priya", "date_of_birth": "1998-11-03", "time_of_birth": "18:30", "birth_place": "Pune", "preferred_language": "Hindi"}'
```

```json
{
  "user_id": "priya-1",
  "name": "Priya",
  "date_of_birth": "1998-11-03",
  "time_of_birth": "18:30",
  "birth_place": "Pune",
  "preferred_language": "Hindi",
  "sun_sign": "Scorpio",
  "astrology": {
    "sun_sign": "Scorpio",
    "element": "Water",
    "ruling_planet": "Mars",
    "traits": [
      "intense",
      "strategic",
      "private"
    ],
    "career_hint": "deep focus and transformation projects",
    "full_chart_available": true
  },
  "missing_profile_fields": []
}
```

## 2. First message from a new user (facts extracted and stored)

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-456", "message": "My name is Rahul. I was born on 15 August 1995 in Delhi. I'm planning to switch jobs next year."}'
```

```json
{
  "response": "Namaste Rahul! I've noted: name: Rahul; date of birth: 1995-08-15; birth place: Delhi; goal: Career Change (timeframe next year, target year 2027). As a Leo (Fire sign, ruled by Sun), you tend to do best with visibility, leadership and owning outcomes. Ask me what to focus on whenever you're ready.",
  "user_id": "user-123",
  "session_id": "session-456",
  "context_used": [
    "user_profile",
    "astrology_profile"
  ],
  "context_details": [],
  "memory_updates": [
    {
      "action": "created",
      "kind": "profile",
      "key": "profile:name",
      "title": "name",
      "detail": "Rahul"
    },
    {
      "action": "created",
      "kind": "profile",
      "key": "profile:date_of_birth",
      "title": "date_of_birth",
      "detail": "1995-08-15"
    },
    {
      "action": "created",
      "kind": "profile",
      "key": "profile:birth_place",
      "title": "birth_place",
      "detail": "Delhi"
    },
    {
      "action": "created",
      "kind": "astrology",
      "key": "zodiac",
      "title": "sun_sign",
      "detail": "Leo"
    },
    {
      "action": "created",
      "kind": "goal",
      "key": "goal:career_change",
      "title": "Career Change",
      "detail": "Career Change (timeframe: next year, target year: 2027)"
    }
  ],
  "intent": "share_info",
  "life_areas": [
    "career"
  ],
  "missing_profile_fields": [
    "time_of_birth"
  ],
  "llm_provider": "mock",
  "llm_model": "mock-astro-v1",
  "degraded": false,
  "brain_available": true,
  "warnings": [
    "new_user"
  ],
  "latency_ms": 83
}
```

## 3. Personalised question in the same session

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-456", "message": "What should I focus on in my career?"}'
```

```json
{
  "response": "Namaste Rahul! Based on what you've shared (Career Change (timeframe: next year, target year: 2027)), for career, focus on: build one visible proof of skill, have conversations with people already in the roles you want, and set a clear timeline for your move. As a Leo (Fire sign, ruled by Sun), you tend to do best with visibility, leadership and owning outcomes.",
  "user_id": "user-123",
  "session_id": "session-456",
  "context_used": [
    "user_profile",
    "astrology_profile",
    "career_goal",
    "conversation_history"
  ],
  "context_details": [
    {
      "label": "career_goal",
      "value": "Career Change (timeframe: next year, target year: 2027)",
      "score": 0.905
    }
  ],
  "memory_updates": [],
  "intent": "advice",
  "life_areas": [
    "career"
  ],
  "missing_profile_fields": [
    "time_of_birth"
  ],
  "llm_provider": "mock",
  "llm_model": "mock-astro-v1",
  "degraded": false,
  "brain_available": true,
  "warnings": [],
  "latency_ms": 27
}
```

## 4. Follow-up resolved from short-term context

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-456", "message": "Why do you say that?"}'
```

```json
{
  "response": "I said \"Namaste Rahul! Based on what you've shared (Career Change (timeframe: next year, target year: 2027)), for career, focus on: build one visible proof of skill,...\" because you told me about: Career Change (timeframe: next year, target year: 2027) Also, as a Leo (Fire sign, ruled by Sun), you tend to do best with visibility, leadership and owning outcomes.",
  "user_id": "user-123",
  "session_id": "session-456",
  "context_used": [
    "user_profile",
    "astrology_profile",
    "career_goal",
    "conversation_history"
  ],
  "context_details": [
    {
      "label": "career_goal",
      "value": "Career Change (timeframe: next year, target year: 2027)",
      "score": 0.905
    }
  ],
  "memory_updates": [],
  "intent": "followup",
  "life_areas": [
    "career"
  ],
  "missing_profile_fields": [
    "time_of_birth"
  ],
  "llm_provider": "mock",
  "llm_model": "mock-astro-v1",
  "degraded": false,
  "brain_available": true,
  "warnings": [],
  "latency_ms": 30
}
```

## 5. New session: recall from the Shared Brain

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-789", "message": "What do you remember about my career goals?"}'
```

```json
{
  "response": "Here's what I remember about your career:\n- Career Change (timeframe: next year, target year: 2027)",
  "user_id": "user-123",
  "session_id": "session-789",
  "context_used": [
    "user_profile",
    "astrology_profile",
    "career_goal",
    "previous_session_summary"
  ],
  "context_details": [
    {
      "label": "career_goal",
      "value": "Career Change (timeframe: next year, target year: 2027)",
      "score": 0.905
    }
  ],
  "memory_updates": [],
  "intent": "recall",
  "life_areas": [
    "career"
  ],
  "missing_profile_fields": [
    "time_of_birth"
  ],
  "llm_provider": "mock",
  "llm_model": "mock-astro-v1",
  "degraded": false,
  "brain_available": true,
  "warnings": [],
  "latency_ms": 25
}
```

## 6. Correction: the old goal is superseded, not overwritten

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-789", "message": "Actually, I plan to switch jobs in 2028, not next year."}'
```

```json
{
  "response": "Namaste Rahul! I've noted: goal: Career Change (timeframe 2028, target year 2028). As a Leo (Fire sign, ruled by Sun), you tend to do best with visibility, leadership and owning outcomes. Ask me what to focus on whenever you're ready.",
  "user_id": "user-123",
  "session_id": "session-789",
  "context_used": [
    "user_profile",
    "astrology_profile",
    "career_goal",
    "conversation_history"
  ],
  "context_details": [
    {
      "label": "career_goal",
      "value": "Career Change (timeframe: next year, target year: 2027)",
      "score": 0.905
    }
  ],
  "memory_updates": [
    {
      "action": "updated",
      "kind": "goal",
      "key": "goal:career_change",
      "title": "Career Change",
      "detail": "Career Change (timeframe: next year, target year: 2027) -> Career Change (timeframe: 2028, target year: 2028)"
    }
  ],
  "intent": "share_info",
  "life_areas": [
    "career"
  ],
  "missing_profile_fields": [
    "time_of_birth"
  ],
  "llm_provider": "mock",
  "llm_model": "mock-astro-v1",
  "degraded": false,
  "brain_available": true,
  "warnings": [],
  "latency_ms": 18
}
```

## 7. Irrelevant memories are left out

The career goals are not sent because the question is about health.

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-789", "message": "How is my health looking this year?"}'
```

```json
{
  "response": "Namaste Rahul! Here's my guidance: for health, focus on: keep a steady routine for sleep and movement, and consult a professional for anything persistent. As a Leo (Fire sign, ruled by Sun), you are naturally confident, creative and proud; use that, but watch for being too proud.",
  "user_id": "user-123",
  "session_id": "session-789",
  "context_used": [
    "user_profile",
    "astrology_profile",
    "conversation_history"
  ],
  "context_details": [],
  "memory_updates": [],
  "intent": "advice",
  "life_areas": [
    "health"
  ],
  "missing_profile_fields": [
    "time_of_birth"
  ],
  "llm_provider": "mock",
  "llm_model": "mock-astro-v1",
  "degraded": false,
  "brain_available": true,
  "warnings": [
    "no_relevant_memory"
  ],
  "latency_ms": 6
}
```

## 8. Invalid input

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-789", "message": "   "}'
```

```json
{
  "error": "invalid_input",
  "details": [
    {
      "field": "message",
      "message": "Value error, message must not be blank"
    }
  ]
}
```

## 9. Inspect the user's Shared Brain

```bash
curl -X GET http://localhost:8000/users/user-123/brain -H 'Content-Type: application/json'
```

```json
{
  "user": {
    "updated_at": "2026-10-03T13:02:52+00:00",
    "user_id": "user-123",
    "date_of_birth": "1995-08-15",
    "name": "Rahul",
    "birth_place": "Delhi",
    "created_at": "2026-10-03T13:02:52+00:00",
    "sun_sign": "Leo"
  },
  "relationships": [
    {
      "type": "HAS_ZODIAC",
      "target": {
        "label": "ZodiacSign",
        "name": "Leo"
      }
    },
    {
      "type": "HAS_GOAL",
      "target": {
        "label": "Goal",
        "id": "f1f0c89d1bbb40a5b6393109911f4d1e",
        "kind": "goal",
        "key": "goal:career_change",
        "title": "Career Change",
        "area": "career",
        "confidence": 0.85,
        "importance": 0.9,
        "status": "superseded",
        "source_text": "I'm planning to switch jobs next year.",
        "mention_count": 1,
        "created_at": "2026-10-03T13:02:52+00:00",
        "updated_at": "2026-10-03T13:02:53+00:00",
        "attr_timeframe": "next year",
        "attr_target_year": 2027
      },
      "about": {
        "label": "LifeArea",
        "name": "career"
      }
    },
    {
      "type": "HAS_GOAL",
      "target": {
        "label": "Goal",
        "id": "1310e912aa51404b91ef3bb5edfa7173",
        "kind": "goal",
        "key": "goal:career_change",
        "title": "Career Change",
        "area": "career",
        "confidence": 0.9,
        "importance": 0.9,
        "status": "active",
        "source_text": "Actually, I plan to switch jobs in 2028, not next year.",
        "mention_count": 2,
        "created_at": "2026-10-03T13:02:53+00:00",
        "updated_at": "2026-10-03T13:02:53+00:00",
        "attr_timeframe": "2028",
        "attr_target_year": 2028
      },
      "about": {
        "label": "LifeArea",
        "name": "career"
      }
    }
  ],
  "supersedes": [
    {
      "new_id": "1310e912aa51404b91ef3bb5edfa7173",
      "old_id": "f1f0c89d1bbb40a5b6393109911f4d1e"
    }
  ],
  "profile_history": [],
  "sessions": [
    {
      "key": null,
      "summary": "What do you remember about my career goals? | Actually, I plan to switch jobs in 2028, not next year. | How is my health looking this year?",
      "user_id": "user-123",
      "session_id": "session-789",
      "started_at": "2026-10-03T13:02:52+00:00",
      "last_active": "2026-10-03T13:02:53+00:00",
      "turns": 6
    },
    {
      "key": null,
      "summary": "My name is Rahul. I was born on 15 August 1995 in Delhi. I'm planning to switch jobs next year. | What should I focus on in my career? | Why do you say that?",
      "user_id": "user-123",
      "session_id": "session-456",
      "started_at": "2026-10-03T13:02:52+00:00",
      "last_active": "2026-10-03T13:02:52+00:00",
      "turns": 6
    }
  ]
}
```

## 10. Health

```bash
curl -X GET http://localhost:8000/health -H 'Content-Type: application/json'
```

```json
{
  "status": "ok",
  "graph_backend": "neo4j",
  "graph_available": true,
  "llm_provider": "mock",
  "llm_model": "mock-astro-v1",
  "llm_chain": [
    "mock"
  ]
}
```
