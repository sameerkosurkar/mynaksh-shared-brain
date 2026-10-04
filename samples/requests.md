# Sample API requests & responses

Captured from the Docker stack (Neo4j + `LLM_PROVIDER=gemini`, model `gemini-3.5-flash-lite`).
With `LLM_PROVIDER=mock` only the `response` text changes: `context_used`, `memory_updates` etc. are produced
by the pipeline, not by the model. A full mock run is in [`demo_output.txt`](demo_output.txt).

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
  "response": "Hello Rahul. It's great to connect with you. \n\nWith your Leo Sun, you naturally possess the confidence and leadership qualities needed to pursue bold new directions—traits that will serve you well as you plan your career change for 2027. \n\nTo help map out the most auspicious timing and planetary influences for your transition next year, could you share your exact time of birth?",
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
  "llm_provider": "gemini",
  "llm_model": "gemini-3.5-flash-lite",
  "degraded": false,
  "brain_available": true,
  "warnings": [
    "new_user"
  ],
  "latency_ms": 3271
}
```

## 3. Personalised question in the same session

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-456", "message": "What should I focus on in my career?"}'
```

```json
{
  "response": "Rahul, as a Leo, your career path thrives when you can express your natural creativity, confidence, and leadership. You shine brightest in roles where you can take charge, inspire others, and make a visible impact rather than blending into the background. \n\nAs you prepare for your career change in 2027, focus on identifying roles where your unique voice and initiative are valued. \n\nSince career transitions involve important professional decisions, remember that astrology offers guidance rather than guarantees—for financial or major career choices, it's always wise to consult a qualified professional. \n\nTo help tailor this advice specifically to your chart's career houses, do you happen to know your exact time of birth?",
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
  "llm_provider": "gemini",
  "llm_model": "gemini-3.5-flash-lite",
  "degraded": false,
  "brain_available": true,
  "warnings": [],
  "latency_ms": 2019
}
```

## 4. Follow-up resolved from short-term context

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-456", "message": "Why do you say that?"}'
```

```json
{
  "response": "Rahul, I connect your career focus to your Leo Sun because your Sun sign represents your core identity and vital energy in astrology. Being a Leo (born August 15 in Delhi), you are naturally wired with the Sun's traits—confidence, creativity, and a drive to lead—which strongly influence what kind of work will feel fulfilling to you. \n\nWhen you mentioned your goal of a career change next year (2027), pointing you toward roles with leadership and impact was a natural reflection of these innate Leo qualities.",
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
  "llm_provider": "gemini",
  "llm_model": "gemini-3.5-flash-lite",
  "degraded": false,
  "brain_available": true,
  "warnings": [],
  "latency_ms": 1904
}
```

## 5. New session: recall from the Shared Brain

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-789", "message": "What do you remember about my career goals?"}'
```

```json
{
  "response": "Hi Rahul, here is what I remember:\n\n- Your goal is a career change planned for next year (2027).",
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
  "llm_provider": "gemini",
  "llm_model": "gemini-3.5-flash-lite",
  "degraded": false,
  "brain_available": true,
  "warnings": [],
  "latency_ms": 1470
}
```

## 6. Correction: the old goal is superseded, not overwritten

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-789", "message": "Actually, I plan to switch jobs in 2028, not next year."}'
```

```json
{
  "response": "Got it, Rahul. I've updated your target year to 2028 for your career change. \n\nAs a Leo, your natural confidence and drive will be great assets as you prepare for this transition over the next couple of years. Since we're looking at timing your next steps, knowing your exact birth time would help us look closer at your transits. Would you happen to have it? \n\n*(Just a friendly reminder that astrology offers guidance rather than certainties, and for major life decisions, it's always wise to consult a professional advisor.)*",
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
  "llm_provider": "gemini",
  "llm_model": "gemini-3.5-flash-lite",
  "degraded": false,
  "brain_available": true,
  "warnings": [],
  "latency_ms": 3472
}
```

## 7. Irrelevant memories are left out

The career goal is not sent (no `career_goal` in `context_used`) because the question is about health.

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-789", "message": "How is my health looking this year?"}'
```

```json
{
  "response": "Hi Rahul, to give you meaningful astrological guidance on your health this year, I would need to know your exact time of birth. \n\n*(Please remember that astrology offers guidance rather than certainties, and for any medical concerns, it is always best to consult a professional healthcare provider.)*",
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
  "llm_provider": "gemini",
  "llm_model": "gemini-3.5-flash-lite",
  "degraded": false,
  "brain_available": true,
  "warnings": [
    "no_relevant_memory"
  ],
  "latency_ms": 1634
}
```

## 8. Long-tail facts picked up by the LLM extractor

The rules do not cover these phrasings; the LLM extractor (hybrid mode) adds them after schema validation.

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "user-123", "session_id": "session-789", "message": "I volunteer at an animal shelter every weekend and I have been learning Vedic astrology from my grandmother."}'
```

```json
{
  "response": "That's wonderful, Rahul. Volunteering at an animal shelter reflects the warm, generous heart of your Leo Sun, and learning Vedic astrology from your grandmother is such a special way to connect with your roots and this ancient wisdom. \n\nSince you are exploring Vedic astrology, you might appreciate how planetary periods (dashas) and transits guide us—though remember, astrology offers guidance rather than certainties, and for any health decisions, always consult a professional. \n\nWould you like to share your time of birth so we can explore how your chart connects to your studies and upcoming plans?",
  "user_id": "user-123",
  "session_id": "session-789",
  "context_used": [
    "user_profile",
    "astrology_profile",
    "conversation_history"
  ],
  "context_details": [],
  "memory_updates": [
    {
      "action": "created",
      "kind": "interest",
      "key": "interest:animal_shelter_volunteering",
      "title": "Animal shelter volunteering",
      "detail": "Animal shelter volunteering"
    },
    {
      "action": "created",
      "kind": "interest",
      "key": "interest:learning_vedic_astrology",
      "title": "Learning Vedic astrology",
      "detail": "Learning Vedic astrology"
    }
  ],
  "intent": "advice",
  "life_areas": [
    "education"
  ],
  "missing_profile_fields": [
    "time_of_birth"
  ],
  "llm_provider": "gemini",
  "llm_model": "gemini-3.5-flash-lite",
  "degraded": false,
  "brain_available": true,
  "warnings": [
    "no_relevant_memory"
  ],
  "latency_ms": 3294
}
```

## 9. Preferred language (Hindi)

```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"user_id": "priya-1", "session_id": "s1", "message": "What should I focus on in my career?"}'
```

```json
{
  "response": "नमस्ते प्रिया! वृश्चिक राशि (Scorpio) का जल तत्व और मंगल का प्रभाव आपको स्वाभाविक रूप से रणनीतिक, गहन और समर्पित बनाता है। \n\nआपके इस स्वभाव को देखते हुए, करियर में आपको ऐसी भूमिकाओं पर ध्यान देना चाहिए जहाँ आपकी रिसर्च स्किल्स, गहराई और समस्याओं को सुलझाने की क्षमता काम आए—जैसे डेटा एनालिटिक्स, रिसर्च, मनोविज्ञान (psychology), या स्ट्रेटेजिक मैनेजमेंट। आप सतही कामों के बजाय किसी प्रोजेक्ट के मूल तक जाने में माहिर हैं, इसलिए ऐसे क्षेत्र चुनें जहाँ स्वायत्तता (autonomy) हो।\n\nचूंकि करियर के फैसले महत्वपूर्ण होते हैं, याद रखें कि ज्योतिष केवल मार्गदर्शन प्रदान करता है; अपने अंतिम निर्णय के लिए पेशेवर सलाह भी अवश्य लें।\n\nक्या आप वर्तमान में किसी खास क्षेत्र में काम कर रही हैं, या किसी नए रास्ते पर विचार कर रही हैं?",
  "user_id": "priya-1",
  "session_id": "s1",
  "context_used": [
    "user_profile",
    "astrology_profile"
  ],
  "context_details": [],
  "memory_updates": [],
  "intent": "advice",
  "life_areas": [
    "career"
  ],
  "missing_profile_fields": [],
  "llm_provider": "gemini",
  "llm_model": "gemini-3.5-flash-lite",
  "degraded": false,
  "brain_available": true,
  "warnings": [
    "no_relevant_memory"
  ],
  "latency_ms": 2197
}
```

## 10. Invalid input

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

## 11. Inspect the user's Shared Brain

```bash
curl -X GET http://localhost:8000/users/user-123/brain -H 'Content-Type: application/json'
```

```json
{
  "user": {
    "updated_at": "2026-10-04T10:56:19+00:00",
    "user_id": "user-123",
    "date_of_birth": "1995-08-15",
    "name": "Rahul",
    "birth_place": "Delhi",
    "created_at": "2026-10-04T10:56:15+00:00",
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
        "id": "90c23b423123491784ad2a0e7853cee0",
        "kind": "goal",
        "key": "goal:career_change",
        "title": "Career Change",
        "area": "career",
        "confidence": 0.85,
        "importance": 0.9,
        "status": "superseded",
        "source_text": "I'm planning to switch jobs next year.",
        "mention_count": 1,
        "created_at": "2026-10-04T10:56:19+00:00",
        "updated_at": "2026-10-04T10:56:28+00:00",
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
        "id": "2062190425c543779d23a1da5e4da64e",
        "kind": "goal",
        "key": "goal:career_change",
        "title": "Career Change",
        "area": "career",
        "confidence": 0.9,
        "importance": 0.9,
        "status": "active",
        "source_text": "Actually, I plan to switch jobs in 2028, not next year.",
        "mention_count": 2,
        "created_at": "2026-10-04T10:56:28+00:00",
        "updated_at": "2026-10-04T10:56:28+00:00",
        "attr_timeframe": "2028",
        "attr_target_year": 2028
      },
      "about": {
        "label": "LifeArea",
        "name": "career"
      }
    },
    {
      "type": "INTERESTED_IN",
      "target": {
        "label": "Interest",
        "id": "0792cd5155bf41ec927cc43d626a2596",
        "kind": "interest",
        "key": "interest:learning_vedic_astrology",
        "title": "Learning Vedic astrology",
        "area": "spirituality",
        "confidence": 0.8,
        "importance": 0.9,
        "status": "active",
        "source_text": "I volunteer at an animal shelter every weekend and I have been learning Vedic astrology from my grandmother.",
        "mention_count": 1,
        "created_at": "2026-10-04T10:56:33+00:00",
        "updated_at": "2026-10-04T10:56:33+00:00"
      },
      "about": {
        "label": "LifeArea",
        "name": "spirituality"
      }
    },
    {
      "type": "INTERESTED_IN",
      "target": {
        "label": "Interest",
        "id": "36f9da1111314fc08189c9751d46fd7f",
        "kind": "interest",
        "key": "interest:animal_shelter_volunteering",
        "title": "Animal shelter volunteering",
        "area": "personal",
        "confidence": 0.8,
        "importance": 0.8,
        "status": "active",
        "source_text": "I volunteer at an animal shelter every weekend and I have been learning Vedic astrology from my grandmother.",
        "mention_count": 1,
        "created_at": "2026-10-04T10:56:33+00:00",
        "updated_at": "2026-10-04T10:56:33+00:00"
      },
      "about": {
        "label": "LifeArea",
        "name": "personal"
      }
    }
  ],
  "supersedes": [
    {
      "new_id": "2062190425c543779d23a1da5e4da64e",
      "old_id": "90c23b423123491784ad2a0e7853cee0"
    }
  ],
  "profile_history": [],
  "sessions": [
    {
      "key": null,
      "summary": "User: What do you remember about my career goals? Naksh: Hi Rahul, here is what I remember:  - Your goal is a career change planned for next year (2027). Actually, I plan to switch jobs in 2028, not next year. | How is my health looking this year? | I volunteer at an animal shelter every weekend and I have been learning Vedic astrology from my grandmother.",
      "user_id": "user-123",
      "session_id": "session-789",
      "started_at": "2026-10-04T10:56:24+00:00",
      "last_active": "2026-10-04T10:56:33+00:00",
      "turns": 8
    },
    {
      "key": null,
      "summary": "My name is Rahul. I was born on 15 August 1995 in Delhi. I'm planning to switch jobs next year. | What should I focus on in my career? | Why do you say that?",
      "user_id": "user-123",
      "session_id": "session-456",
      "started_at": "2026-10-04T10:56:19+00:00",
      "last_active": "2026-10-04T10:56:23+00:00",
      "turns": 6
    }
  ]
}
```

## 12. Health

```bash
curl -X GET http://localhost:8000/health -H 'Content-Type: application/json'
```

```json
{
  "status": "ok",
  "graph_backend": "neo4j",
  "graph_available": true,
  "llm_provider": "gemini",
  "llm_model": "gemini-3.5-flash-lite",
  "llm_chain": [
    "gemini",
    "mock"
  ]
}
```
