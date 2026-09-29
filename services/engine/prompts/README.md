# LLM prompts (doc 06 §2, §5)

| Path | What it is |
|---|---|
| `<task>.v<N>.md` | Versioned prompt template: front matter, then `# system` (static, the cached prefix), optional `# context` (cached course "context pack"), and `# user` |
| `schemas/<task>.v1.json` | `output_config.format` JSON schema, generated from the pydantic model in `engine/llm/schemas.py::TASK_OUTPUTS` (structured-output subset only) |
| `examples/<task>.v1.json` | Valid and invalid example outputs. Tests check them against both the schema and the model |
| `versions.lock.json` | Append-only SHA-256 lock of every prompt file |

## Rules
- **Never edit a locked prompt.** Copy it to `v<N+1>`, change the copy, then run `uv run python -m engine.llm.prompts --lock`. Old versions stay for reproducibility; `load(task)` picks the highest. Record `prompt_version` (`<task>@<N>`) on every call (doc 06 §2/§8).
- **Model IDs aren't here.** `tier: sonnet|haiku` maps to the `llm.claude_sonnet` / `llm.claude_haiku` adapters; the model IDs live in `app_config` (doc 06 §2). Sonnet 5 uses adaptive thinking with `effort`; Haiku 4.5 takes no effort parameter.
- **Untrusted inputs are delimited by `render()`, never by callers.** Retrieved chunks become `<course_material id source>` blocks; strings are wrapped in reserved tags (`<student_answer>`, `<syllabus_text>`, `<user_message>`, `<untrusted>`, …). Any reserved tag inside the text is escaped, so a document can't close its block or forge a `<turn_directive>`.
- **The tutor** streams text with `[[chunk:<id>]]` markers (no structured output, no tools). The server builds the `<turn_directive>` (`prompts.turn_directive()`) from the Socratic pre-check (mode `hint`, levels 1–3) and the worked-solution eligibility check. Every hint-mode reply is checked by `tutor.guard` (regenerate once, then fall back to a canned hint).
- **Validate replies with `schemas.parse_output(task, raw_json)`** (strict JSON mode), then with the consuming engine function (`grade_with_rubric`, `feynman.analyze`, `validate_extraction`, `lint_card`, `merge_concepts`, `verify_generated_question`).
- After changing an output model: `uv run python -m engine.llm.schemas --write` (a test fails on drift).
- The syllabus prompt's spans index into the text inside `<syllabus_text>`. If the syllabus itself contains a reserved tag (vanishingly rare), escaping shifts later offsets, and `validate_extraction` then flags those spans. That's safe: it just triggers review.
