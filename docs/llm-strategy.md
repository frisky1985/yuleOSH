# LLM Strategy & RAG Architecture

> **Document**: `docs/llm-strategy.md`
> **Version**: 1.0.0
> **Status**: Approved — Sprint 1

---

## 1. Model Selection

### Production Models

| Model               | Provider    | Cost/1K input | Cost/1K output | Context | Quality Tier | Use Case                              |
|---------------------|-------------|---------------|----------------|---------|--------------|---------------------------------------|
| Claude 4 Sonnet     | Anthropic   | $0.015        | $0.075         | 200K    | High         | Architecture, code gen (safety), review blocking |
| DeepSeek V4         | DeepSeek    | $0.002        | $0.008         | 128K    | Medium       | Code gen (non-critical), test gen, summaries |
| GPT-4o              | OpenAI      | $0.010        | $0.030         | 128K    | High         | Benchmark baseline, fallback          |

### Routing Strategy

```
Task Type                   → Default Route     → Cheap Route
────────────────────────────────────────────────────────────────
SDD architecture design     → Claude 4 Sonnet    → N/A (must be quality)
Code gen (safety-critical)  → Claude 4 Sonnet    → N/A
Code gen (non-critical)     → DeepSeek V4        → DeepSeek V4 (no RAG)
Unit test generation        → DeepSeek V4        → DeepSeek V4 (no RAG)
MISRA violation fix         → Claude + RAG       → DeepSeek V4 + RAG
Review (blocking pass/fail) → Claude 4 Sonnet    → N/A
Review (non-blocking self)  → DeepSeek V4        → DeepSeek V4
Simple summary/status       → DeepSeek V4        → DeepSeek V4
```

### Cost Model Selection

Three user-selectable modes:
- **"quality"** : Claude 4 Sonnet + RAG — highest quality, highest cost
- **"balanced"** : DeepSeek V4 + RAG — default
- **"cheap"** : DeepSeek V4, no RAG — lowest cost
- **"auto"** : Route per task type table above

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LLMClient (unified API)                    │
│  ┌─────────────┐ ┌─────────────┐ ┌────────────────────────┐ │
│  │  TokenBudget │ │  Provider    │ │  CostLogger             │ │
│  │  Checker    │ │  Router     │ │  (audit JSONL)          │ │
│  └─────────────┘ └─────────────┘ └────────────────────────┘ │
│                        │                                      │
│                        ▼                                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  AbstractProvider (ABC)                                │ │
│  │  ├── ClaudeProvider   → api.anthropic.com              │ │
│  │  ├── DeepSeekProvider → api.deepseek.com               │ │
│  │  ├── OpenAIProvider   → api.openai.com                 │ │
│  │  └── MockProvider     → local, for tests               │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Multi-Provider Switching

### AbstractProvider Interface

```python
class AbstractProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list, config: LLMConfig) -> LLMResponse:
        ...

    @abstractmethod
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        ...
```

### Provider Registry

```python
PROVIDER_REGISTRY = {
    "anthropic": ClaudeProvider,
    "deepseek": DeepSeekProvider,
    "openai": OpenAIProvider,
    "mock": MockProvider,
}

LLMConfig(
    model="deepseek-v4",
    provider="deepseek",
    max_tokens=4096,
    temperature=0.3,
    rag_enabled=True,
    max_cost_usd=0.50,
)
```

---

## 4. RAG Engine

### Knowledge Sources

| Source               | Chunks  | Embedding               | Use                       |
|----------------------|---------|-------------------------|---------------------------|
| MISRA-C:2012 rules   | ~185    | text-embedding-3-small  | Code gen compliance       |
| Embedded best practices | ~50   | text-embedding-3-small  | Driver templates          |
| Project review history | dynamic | text-embedding-3-small | Consistent reviews        |

### Retrieval Strategy

```
User Prompt
    │
    ▼
[Query Embedding] → [Top-K Vector Search]
    │
    ▼
[Re-rank by keyword overlap] → [Context Assembly]
    │
    ▼
[Enhanced System Prompt] → [LLM]
```

- Embedding model: `text-embedding-3-small` (OpenAI) or `DeepSeek-Embedding`
- Vector store: In-memory dict + JSON (v1); ChromaDB (v2)
- Chunking: One chunk per MISRA rule ID (natural boundaries)
- Top-K: 8 for MISRA, 3 for project history

### MISRA Rule Format

```python
MISRA_RULE = {
    "rule_id": "Rule 10.1",
    "category": "Required",
    "title": "Integer type implicit conversion",
    "summary": "...",
    "violation_examples": ["uint16_t x=10; uint32_t y=x+5;"],
    "fix_examples": ["uint16_t x=10; uint32_t y=(uint32_t)x+5;"],
    "related_rules": ["10.3", "10.4"],
    "severity": "high",
}
```

---

## 5. Token Budget Pre-check

Prevents runaway costs by estimating token usage before each LLM call.

### Pricing Table

```python
PRICING = {
    "claude-4-sonnet": {
        "input_per_1k": 0.015,
        "output_per_1k": 0.075,
        "context_window": 200_000,
    },
    "deepseek-v4": {
        "input_per_1k": 0.002,
        "output_per_1k": 0.008,
        "context_window": 128_000,
    },
}
```

### Task Budgets

| Task Type             | Max Cost (USD) | Max Output Tokens |
|-----------------------|----------------|--------------------|
| code_generation       | 0.50           | 4096               |
| test_generation       | 0.30           | 2048               |
| architecture_design   | 0.80           | 6144               |
| misra_review          | 0.40           | 3072               |
| simple_summary        | 0.10           | 1024               |

### Pre-check Flow

```
1. Estimate prompt tokens: len(text) / 3.5
2. Check context window: prompt_tokens < 80% of context_window
3. Estimate cost: input_cost + output_cost (conservative)
4. Compare against task budget
5. If over budget → return BudgetExceeded error with details
6. Otherwise → proceed to LLM call
```

---

## 6. LLM Call Audit Log

Every LLM invocation is logged to `.osh/logs/llm_calls.jsonl` (JSON Lines format).

### Log Entry Schema

```json
{
    "timestamp": "2026-07-05T14:30:00Z",
    "task_type": "code_generation",
    "model": "claude-4-sonnet",
    "provider": "anthropic",
    "tokens_in": 2450,
    "tokens_out": 1230,
    "cost": 0.128,
    "duration_s": 45.2,
    "status": "success",
    "task_id": "T001",
    "user_id": "usr_abc"
}
```

### CostLogger API

```python
CostLogger.log(LLMCallLog(...))           # Append to JSONL
CostLogger.get_daily_summary("2026-07-05") # → {total_calls, total_cost, per_model}
CostLogger.get_task_cost("T001")           # → total USD for a pipeline task
```

### Data Retention

- JSONL files rotate at 10 MB
- Evidence pack includes `llm-call-log.json` (recent 1000 entries)
- Full history stored in `.osh/logs/llm_calls/` by month

---

## 7. Backward Compatibility

The existing `_call_llm` function is preserved as a thin wrapper:

```python
# Temporary compatibility shim (remove after 2 release cycles)
async def _call_llm(prompt: str, **kwargs) -> str:
    response = await LLMClient.call(prompt=prompt, **kwargs)
    return response.content
```

All 20+ step handler imports remain unchanged during Sprint 1.
Migration planned for Sprint 2–3.

---

## 8. Cost Control Strategy

| Layer         | Mechanism                                    | Savings Estimate |
|---------------|----------------------------------------------|------------------|
| Model routing | Use DeepSeek V4 for non-critical tasks        | 60%              |
| Token budget  | Pre-check, reject oversized prompts           | 10%              |
| RAG precision | Only inject relevant context (not full corpus) | 15%              |
| Retry cap     | Max 3 retries with exponential backoff        | 5%               |
| Caching       | Embedding cache (avoid re-indexing)           | 20% on RAG       |

**Target cost per pipeline run**: $0.15–$0.50 (vs $2.00+ without optimization)

---

## References

- Technical implementation plan §4: LLM strategy + RAG
- `src/yuleosh/llm/client.py` — Existing LLM client (retained as backend)
- `src/yuleosh/llm/providers/` — Provider adapter implementations
- `src/yuleosh/llm/token_budget.py` — Budget pre-check middleware
- `src/yuleosh/llm/cost.py` — Audit cost logger
