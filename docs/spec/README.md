---
title: StudyForge — Build Package README
project: StudyForge
status: ready-for-agent
created: 2026-09-27
tags: [project, studyforge, saas, build-package]
---

# StudyForge: Build Package

This is everything an AI coding agent needs to build **StudyForge**, an exam-backwards study platform, as a real multi-user **SaaS product**, not a personal project. It follows the [[SaaS-Playbook/00-Index/Master MOC|SaaS Playbook]] through its agent-ready derivative, the [[Agent-Build-Checklist/README|Agent Build Checklist]]. That means every one of the 1,147 engineering items and 291 human items is accounted for: each one is built, adapted, or explicitly deferred with a reason. None are silently dropped.

> `StudyForge` is a placeholder name. The agent keeps it in a single `APP_NAME` config constant, so renaming it later takes one change.

## Decisions locked in (2026-09-27)
| Area | Decision |
|---|---|
| Customer | **B2C only**: individual college/university students, **18+**, US-first, open to global signups |
| Frontend | **Next.js (App Router) + React + TypeScript**, Tailwind + shadcn/ui, installable **PWA**, web only |
| System of record | **Supabase**: Postgres + pgvector + RLS, Auth, Storage, Queues (pgmq), Cron, Realtime, Vault |
| Core engine | **Python 3.12 FastAPI** on **Google Cloud Run** (a service for short work + Cloud Run Jobs for long work, woken on demand): parsing, OCR, speech-to-text, embeddings, knowledge graph, FSRS optimizer, grading, code sandbox |
| Hosting | Web app runs **locally as a production build** (Vercel-ready, not deployed) against **Supabase Cloud** (one project) + **Google Cloud Run** (engine + private code sandbox). All data lives in the cloud |
| Version control | **Local git only** (no GitHub). Checks run locally with `pnpm verify`; deploys are scripts |
| Email | **Faked** with an outbox: every email (including login emails) is stored and shown in Admin → Mail outbox. No email provider or domain |
| Environments | **Local + one cloud environment** (production). One account and project per service, no staging |
| Services | Sentry, PostHog, Langfuse (cloud free tier), Better Stack free tier. No Turnstile, no Upstash (rate limits in Postgres), no backups |
| LLMs | Routed per task: **Claude Sonnet 5** for the tutor, grading and Feynman analysis; **Claude Haiku 4.5** for bulk generation and tagging. Everything goes through an LLM gateway, so models can be swapped per task |
| Ingestion / OCR / STT / embeddings | **Free, self-hosted adapters by default** (Docling, PyMuPDF, faster-whisper, PaddleOCR, bge-small). **Paid APIs are switchable per task** (Deepgram, AssemblyAI, Claude vision, Mistral OCR, Voyage, OpenAI) from an admin **Provider Settings** screen |
| Billing | **Mock billing**: real plans, entitlements, checkout, invoices and plan changes, but every charge totals **$0.00**. It sits behind a `BillingProvider` interface, so Stripe can be dropped in later |
| Calendars | **Google Calendar two-way sync** only. Outlook and Apple are possible future additions, and the calendar code sits behind a `CalendarProvider` interface so they can be added without touching the planner |
| Build agent | **OpenAI Codex**, which reads the repo's `AGENTS.md` for its standing rules |
| Scope | **All 6 learning modules**, built as phased milestones on top of a full SaaS foundation |

## Files in this package (read in this order)
| # | File | Purpose |
|---|---|---|
| 00 | [[00 - Agent Kickoff Prompt]] | **Paste this to the agent.** Operating rules, session protocol, definition of done |
| 01 | [[01 - Product Requirements (PRD)]] | Every feature, user story and acceptance criterion |
| 02 | [[02 - Architecture & Stack]] | System design, repo layout, environments, ADR list |
| 03 | [[03 - Data Model & RLS]] | Every table, key columns, RLS rules, indexes, PII tiers |
| 04 | [[04 - API & Jobs Contract]] | REST `/api/v1` surface, job types, error/idempotency/rate-limit conventions |
| 05 | [[05 - Learning Algorithms]] | FSRS + crunch mode, backward scheduler, rebalancing, interleaving, mastery, cram queue |
| 06 | [[06 - AI & Provider Adapters]] | Model routing, adapter interfaces, prompt-injection defense, cost limits, evals |
| 07 | [[07 - Plans, Entitlements & Mock Billing]] | Plan matrix, quotas, the $0 checkout flow, the Stripe swap path |
| 08 | [[08 - Milestones & Acceptance Gates]] | M0–M11 build order, and what "done" means for each |
| 09 | [[09 - Checklist Overrides]] | How each Engineering Checklist note applies to StudyForge (built / adapted / N/A / deferred) |
| 10 | [[10 - Human Handoff (StudyForge)]] | What **you** must do: accounts, keys, legal review, Google verification, and more |
| — | `repo-templates/` | Files the agent copies into the repo on day one: `AGENTS.md`, `PROGRESS.md`, `.env.example`, `ADR template` |

## How to start
The repo is already set up at `C:\Users\baldy\Projects\studyforge`: git initialized, spec in `docs/spec/`, checklist copy in `docs/checklist/`, templates in place, and `.env.local` / `.env.production` created with the random secrets generated.
1. **Create the 8 accounts and paste each key once into `.env.keys`** in the repo root (the step-by-step clicks are in `docs/setup/KEYS_CHECKLIST.md`).
2. **Open the repo in Codex** and paste everything below the line in [[00 - Agent Kickoff Prompt]] as the first message.
3. **Plan:** the agent writes the task breakdown and checklist triage, then waits for your approval. Reply **"Approved. Proceed to the Second Step."**
4. **Env check:** the agent builds `pnpm env:check` and verifies your keys without printing them. It only comes back to you if something you provided is missing or wrong; otherwise it goes straight into M0 and fills in the Cloud Run URLs, deployer account and engine DB password itself.
5. **Build:** M0 → M11. It pauses only for human *actions* (Google OAuth test users, legal review, real-device checks). Whenever it stops, say **"Continue the StudyForge build."**

> This folder in the vault is the master copy of the spec. If you change a doc here later, copy it into the repo's `docs/spec/` too.

## Relationship to the earlier "Study Helper" scope
[[Study Helper/Master Scope Document|Study Helper — Master Scope Document]] was the personal-project version. StudyForge replaces it as the SaaS version. It keeps the good STEM ideas from it (KaTeX/MathLive, SymPy answer checking, the code sandbox, Anki `.apkg` import/export) and adds the six-module exam-backwards design and the full SaaS apparatus.
