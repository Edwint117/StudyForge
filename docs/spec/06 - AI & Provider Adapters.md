---
title: StudyForge — AI & Provider Adapters
project: StudyForge
created: 2026-09-27
tags: [project, studyforge, ai, llm]
---

# 06: AI & Provider Adapters

## 1. Principles
1. **Every AI/ML call goes through an adapter.** No feature code imports a vendor SDK directly. A lint rule bans `@anthropic-ai/sdk`, `anthropic`, `deepgram` and similar packages outside `packages/llm-gateway` and `services/engine/engine/adapters`.
2. **Free/self-hosted by default. Paid APIs can be switched in per task and per plan** from Admin → Provider Settings (`app_config.providers`), with no redeploy.
3. **Meter before and after:** a quota check before the call (estimated cost) and a usage event after it (actual tokens/seconds/pages → `usage_events`).
4. **Fail safe:** timeouts, retries with backoff on 429/5xx, a per-provider **circuit breaker** (5 consecutive failures or > 50% errors in 1 min → open for 2 min → fall back to the next provider in the task's chain), and a **global AI kill switch** that returns `503 ai_temporarily_unavailable` with a friendly UI message.
5. **No training on user data:** only providers whose API terms say customer data isn't used for training (verify and record each one in `docs/subprocessors.yaml`).

## 2. Model routing (LLM tasks)
Defaults below. Admins can override per plan. Model IDs are current as of 2026-09. **Verify them against the Models API at build time**, and keep them only in `app_config`, never hard-coded in feature code.

| Task ID | Default model | Why | Notes |
|---|---|---|---|
| `tutor.socratic` | **`claude-sonnet-5`** (Free plan: `claude-haiku-4-5`, so the Free daily cap covers ~13 messages) | Needs judgment to withhold answers and give hints well | Streaming; adaptive thinking; effort `medium`; prompt caching on the system prompt + retrieved context |
| `grade.rubric` | **`claude-sonnet-5`** | Partial credit and error classification need reliability | Structured output (JSON schema); effort `high`; runs **after** deterministic checks |
| `feynman.analyze` | **`claude-sonnet-5`** | Gap and buzzword detection | Structured output |
| `question.generate` | `claude-sonnet-5` | Exam-quality questions | Verified by `question.solve` ×2 |
| `question.solve` (verification) | `claude-sonnet-5` (independent context) | Must disagree when the question is wrong | Two runs at different temperature-free prompt framings |
| `cards.generate` | **`claude-haiku-4-5`** | High volume, cheap | **Batch API** (50% cheaper) for batches > 50 cards; structured output |
| `cards.lint` | `claude-haiku-4-5` | Cheap quality pass | |
| `ingest.tag_chunks` / `ingest.extract_concepts` | `claude-haiku-4-5` | Bulk classification and extraction | Batch where latency allows |
| `ingest.link_assets` (tiebreak) | `claude-haiku-4-5` | Only for ambiguous embedding matches | |
| `syllabus.extract` | `claude-haiku-4-5` → escalate to `claude-sonnet-5` if any required field has confidence < 0.7 | Dates and weights must be right | Structured output + source spans |
| `answer.keypoints` | `claude-haiku-4-5` | Card free-explain verification | Cached by answer hash |
| `cheatsheet.compress` | `claude-haiku-4-5` | Fitting to the page budget | |
| `ocr.vision` (paid option) | `claude-haiku-4-5` (vision) / `claude-sonnet-5` for dense math | Handwriting + math → LaTeX | Only when selected in Provider Settings |

Implementation notes (Claude API, as of 2026-09):
- Use **structured outputs** (`output_config.format` with a JSON schema) for every extraction or grading task, and validate again with zod/pydantic.
- Citations: the tutor produces its own `[[chunk:<id>]]` markers that are validated against the retrieved set. Don't combine the API's native `citations` with structured outputs, because they're incompatible. The tutor uses streaming text + markers, not structured output.
- **Prompt caching:** put stable content first (the system prompt, then the course "context pack" of the concept list + retrieved chunks), and verify `cache_read_input_tokens > 0` in tests.
- Haiku 4.5 takes `budget_tokens`-style thinking, if any. Sonnet 5 uses adaptive thinking (`budget_tokens` is rejected). Encode this per model in the gateway, not in feature code.
- Record `model`, `prompt_version`, token usage and cost on every call.

## 3. Non-LLM adapters (defaults = free)
| Capability | Interface | Default (free, self-hosted in engine) | Paid options (switchable) | Selection rule |
|---|---|---|---|---|
| Document parse (PDF/DOCX/PPTX) | `DocumentParser.parse(file) → NormalizedDoc` | **Docling** (layout, tables, formula → LaTeX, code) with **PyMuPDF** fast path for text-only PDFs; python-pptx for speaker notes | LlamaParse, Mistral OCR (document mode) | Fall back to the paid parser or `ocr.vision` for pages with < 50 extractable characters (scans) |
| OCR (printed + handwriting) | `OcrEngine.recognize(image) → {text_md, latex[], confidence}` | **PaddleOCR** (printed); **TrOCR-handwritten** (free, moderate quality) | Claude vision (`ocr.vision`), Mistral OCR, Google Document AI, Mathpix (math) | Auto-escalate a page to the paid engine **only if** the plan allows it and the free confidence is < 0.6; otherwise flag the page for user review |
| Speech-to-text | `Transcriber.transcribe(audio) → segments[{start_ms,end_ms,text,speaker?,words[]}]` | **faster-whisper** (`small.en` on CPU int8 by default; `medium` on performance machines), VAD on, word timestamps | Deepgram (Nova), AssemblyAI (diarization), OpenAI transcription API | By plan (Pro+ → paid by default if enabled) and by audio length |
| Embeddings | `Embedder.embed(texts) → vector[384]` | **fastembed `BAAI/bge-small-en-v1.5`** (384-d, ONNX, CPU) | Voyage, OpenAI `text-embedding-3-small` (dimension-reduced to 384) | **One global setting for every plan** (vectors from different models can't be compared, so per-plan choice would break search when a user changes plan). Changing it requires a `maintenance.reembed` job; `chunks.embedding_model` is tracked; Provider Settings rejects per-plan differences |
| Math equivalence | `MathChecker` | SymPy (engine) | — | — |
| Code run | `CodeRunner` | Piston (sandbox app) | Judge0 CE hosted | — |
| TTS (optional, later) | — | — | — | out of scope |

Adapter contract (Python):
```python
class Adapter(Protocol):
    id: str                     # "stt.faster_whisper"
    capability: str             # "stt"
    cost_model: CostModel       # per_second / per_page / per_token → estimate()
    async def health(self) -> Health: ...
```
**Default routing by plan tier** (seeded into `app_config.providers`, editable in Provider Settings): the **Free** plan uses free/self-hosted adapters for every task, with no exceptions (low-confidence OCR pages are flagged for the user to review). **Pro/Pro+** get the better services: **Claude vision OCR** (`ocr.vision`, billed to the existing Anthropic key) for pages the free OCR reads with confidence < 0.6, and the paid adapter for a task whenever its API key is configured, otherwise the free one (except embeddings, which are one global choice for all plans). All six paid integrations (Claude vision, Deepgram, AssemblyAI, OpenAI transcription, Mistral OCR, Voyage/OpenAI embeddings) are built and tested with recorded-HTTP fakes, so they work the moment a key is added.

Registry: `resolve(task, plan_tier) → [primary, *fallbacks]` from `app_config.providers`, filtered by circuit-breaker state and by the adapter's required env vars being present (a paid adapter with no API key is silently unavailable, and a warning is shown in the admin UI).

Admin **Provider Settings** UI (ADM-04): a table of tasks × plan tiers → adapter dropdown, showing the estimated cost per unit, the last 24h error rate, p95 latency and a health badge. There's a **Test** button (runs a fixture through the adapter) and a change history.

## 4. RAG (tutor, Feynman, grading grounding)
- **Retrieval:** `search_chunks` hybrid (FTS + vector, RRF k=60), top 24 → rerank by cross-signal (concept overlap with the query's detected concepts, and chunk type priority for definitions/theorems) → top 8, ≤ 6k tokens. Always filtered to `user_id` via RLS, **and** by `course_id` in SQL. Never search across users. The service role is never used for retrieval.
- **Grounding rule:** the system prompt requires answering only from the provided chunks. If the retrieval max score is below the threshold (tuned by eval), the model is told "no relevant material" and must say so.
- **Citation validation:** the markers are parsed and checked to be a subset of the retrieved IDs; invalid ones are removed and counted (`tutor.invalid_citation` metric).

## 5. Prompt-injection & data-leakage defense
Uploaded documents, transcripts, OCR text, calendar event data, question stems and user messages are all **untrusted**.
1. Retrieved content is wrapped in delimited blocks: `<course_material id="…" source="…">…</course_material>`. The system prompt states that the content inside these blocks is data, never instructions.
2. **No tools** are exposed to the tutor model. The only output is text + citation markers. No URLs are fetched from model output, and no actions are taken from model output without user confirmation (e.g. "make cards from this" is a user-clicked button, not model-initiated).
3. Output filtering: strip or neutralize markdown images, raw HTML, and links to non-allowlisted domains in rendered AI output (prevents exfiltration through image URLs). Rendering goes through sanitize-html plus the KaTeX `trust:false` option.
4. System prompts never contain secrets or other users' data. Per-user context contains only that user's rows.
5. **Socratic guard:** a pre-check classifies whether the user is asking for a final answer to an item in their question bank or card set (embedding match > 0.9) and forces hint mode. A post-check (Haiku, cheap) verifies that the response doesn't state the final answer when in hint mode; if it does, the response is regenerated once, then falls back to a canned hint.
6. **Exam lock:** the tutor endpoint returns 423 during an active attempt (server check on `attempts.status='in_progress'` for that user).
7. Red-team eval set (`evals/injection/`): documents containing "ignore previous instructions", exfil-link attempts, requests to reveal the system prompt, and requests for other users' data → must pass 100%.

## 6. Cost limits
- Per user per plan: monthly quotas (doc 07) plus a **daily AI cost cap** (`ai_cost_micros`): Free $0.05/day, Pro $0.50/day, Pro+ $1.50/day (tunable in `app_config`). Mock-exam jobs (`mock.build`, `attempt.grade`, `attempt.regrade`) are exempt from the daily cap because one mock costs more than a Free day's cap; they're limited by the monthly mock-exam quota instead.
- **Global:** a monthly AI budget (`app_config.global_ai_budget_usd`, e.g. $100). Alerts at 50/80/100%. At 100% the system switches automatically to a "degraded" routing profile (all tasks → Haiku or free adapters, tutor limited), and at 120% the kill switch trips.
- Per-request `max_tokens` caps per task, and input-size caps (e.g. a Feynman explanation ≤ 4k tokens).
- **Anthropic Console:** one workspace + key for the project, with a monthly spend limit set (🔑 human task). Local development uses the same key, under the same budgets.
- Dashboards: cost per task per day, cost per active user, and top 20 users by spend (admin).

## 7. Evals (`evals/`)
| Suite | Size (launch) | Metric | Gate |
|---|---|---|---|
| `syllabus_extract` | 30 real-format syllabi (synthetic/public) | field-level F1 for exams/dates/weights | ≥ 0.95 dates, ≥ 0.9 weights |
| `concept_extract` | 10 docs, hand-labelled concepts | precision/recall | P ≥ 0.8, R ≥ 0.7 |
| `cards_quality` | 200 generated cards, rubric-judged (LLM judge calibrated on 50 human labels) | % passing the quality rubric | ≥ 90% |
| `tutor_socratic` | 80 prompts (homework-style asks, conceptual questions, off-material questions) | no final-answer leaks; citation validity; says "not in materials" when appropriate | leaks 0, citation validity ≥ 95% |
| `grading` | 150 answers with human scores + error classes | MAE in points ≤ 10% of max; error-class accuracy ≥ 0.8 | as stated |
| `feynman` | 40 explanations with labelled gaps | gap recall ≥ 0.75 | |
| `question_verify` | 50 flawed + 50 correct generated questions | flawed-question catch rate ≥ 0.9 | |
| `injection` | 60 adversarial docs/messages | pass rate | 100% |
| `ocr` / `stt` adapters | 20 pages / 10 audio clips | CER / WER per adapter | tracked, used to choose defaults |

The fast subset runs in `pnpm verify` whenever prompts/gateway/adapters changed, and the full suite in `pnpm nightly`. Results are stored as JSON in `evals/results/` and trended in Langfuse. Every prompt has a `prompt_version`, and a prompt change fails CI if it lowers any gate metric.

## 8. Observability for AI
Langfuse trace per call: task, model, prompt_version, user_id (hashed), tokens, cost, latency, cache hit, retrieval IDs (not content by default), and the eval score where applicable. Alerts: error rate > 5% per task for 10 min, p95 latency > 2× baseline, and daily spend > forecast by 30%. Content logging stays **off** in production, except for traces of reports the user explicitly submits (SUP-02), which the user consents to.
