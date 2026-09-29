"""Self-serve data export (DATA-01; GDPR access + portability).

``EXPORT_POLICY`` classifies **every** user-data table (doc 03): exported (optionally with redacted columns) or
excluded with a reason. :func:`unclassified_tables` is what the M10 completeness test runs against the live schema,
so adding a user table without deciding its export treatment fails CI. The ZIP holds ``data/<table>.json`` +
``.csv``, original uploads, ``cards.apkg``, a ``manifest.json`` with row counts and SHA-256 checksums, and a README.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

VERSION = "export-1"
FORMAT_VERSION = 1


class TablePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    include: bool
    reason: str = ""
    redact: tuple[str, ...] = ()  # columns removed before export


def _inc(*redact: str) -> TablePolicy:
    return TablePolicy(include=True, redact=redact)


def _exc(reason: str) -> TablePolicy:
    return TablePolicy(include=False, reason=reason)


EXPORT_POLICY: dict[str, TablePolicy] = {
    # account
    "profiles": _inc(), "user_settings": _inc(),
    "legal_acceptances": _inc("ip_hash"), "consent_records": _inc("anon_id"),
    "support_access_grants": _inc(), "data_requests": _inc("artifact_path"),
    "webauthn_credentials": _inc("credential_id", "public_key", "sign_count"),
    "mfa_recovery_codes": _exc("secret material (hashes of recovery codes)"),
    "push_subscriptions": _exc("device push endpoints and keys (secrets)"),
    # courses & ingestion
    "courses": _inc(), "units": _inc(), "documents": _inc("storage_path"), "document_assets": _inc("storage_path"),
    "chunks": _inc("embedding", "fts"), "concepts": _inc("embedding"), "concept_edges": _inc(),
    "concept_chunks": _inc(), "unit_concepts": _inc(), "asset_links": _inc(),
    # planning & calendar
    "exams": _inc(), "exam_units": _inc(), "exam_concepts": _inc(), "syllabus_extractions": _inc(),
    "availability_rules": _inc(), "busy_blocks": _inc("title_hash", "external_id"),
    "calendar_connections": _inc("vault_secret_id", "sync_token", "channel_id", "channel_resource_id"),
    "study_plans": _inc(), "study_sessions": _inc("external_event_refs"),
    # comprehension & retention
    "cards": _inc(), "generation_batches": _inc(), "feynman_attempts": _inc("audio_path"),
    "tutor_threads": _inc(), "tutor_messages": _inc(), "cheat_sheets": _inc("exported_path"),
    "card_states": _inc(), "review_logs": _inc(), "fsrs_parameters": _inc(), "review_sessions": _inc(),
    # diagnostics
    "questions": _inc(), "rubrics": _inc(), "mock_exams": _inc(), "attempts": _inc(), "attempt_answers": _inc(),
    "mastery_snapshots": _inc(), "exam_checklist_items": _inc(),
    # platform
    "usage_events": _inc("idempotency_key", "job_id"), "notifications": _inc(), "notification_preferences": _inc(),
    "email_outbox": _inc("dedupe_key"), "support_tickets": _inc(), "support_messages": _inc(),
    "content_reports": _inc(),
    "jobs": _exc("internal processing records (payloads redacted after 7 days, deleted after 30)"),
    "idempotency_keys": _exc("internal 24-hour request deduplication records"),
    "usage_counters": _exc("derived totals of usage_events, which are exported"),
    "email_suppressions": _exc("stores only a hash of the address, not linkable data"),
    "private.rate_limit_buckets": _exc("transient hashed rate-limit counters"),
    # billing
    "billing.subscriptions": _inc("provider_subscription_id"), "billing.checkout_sessions": _inc(),
    "billing.invoices": _inc(), "billing.invoice_lines": _inc(), "billing.entitlement_overrides": _inc(),
    "billing.billing_events": _exc(
        "raw provider webhook payloads (the resulting subscription/invoice state is exported)"
    ),
    # audit (subject's own security events)
    "audit.events": _inc("ip_hash", "request_id"),
}  # fmt: skip

GLOBAL_TABLES = frozenset(
    {
        "legal_documents",
        "app_config",
        "app_config_history",
        "billing.plans",
        "billing.plan_prices",
        "billing.mock_ledger",
    }
)


def unclassified_tables(schema_user_tables: Iterable[str]) -> list[str]:
    """Tables holding per-user data (have ``user_id`` / ``subject_user_id``) that the policy doesn't classify."""
    return sorted(t for t in schema_user_tables if t not in EXPORT_POLICY and t not in GLOBAL_TABLES)


def _jsonable(v: Any) -> Any:
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, UUID | Decimal):
        return str(v)
    if isinstance(v, bytes):
        return None  # binary columns are never exported inline
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_jsonable(x) for x in v]
    return v


class ExportError(ValueError):
    pass


def build_export_zip(
    out: Path,
    user_id: str,
    generated_at: datetime,
    rows_by_table: Mapping[str, Sequence[Mapping[str, Any]]],
    original_files: Sequence[tuple[str, bytes]] = (),
    apkg: bytes | None = None,
) -> dict[str, Any]:
    """Write the export archive; returns the manifest. Refuses unclassified or excluded tables and rows that
    belong to another user (a last line of defense against a buggy query)."""
    manifest: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "exporter": VERSION,
        "user_id": user_id,
        "generated_at": generated_at.isoformat(),
        "tables": {},
        "files": {},
    }
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:

        def add(name: str, data: bytes) -> None:
            zf.writestr(name, data)
            manifest["files"][name] = hashlib.sha256(data).hexdigest()

        for table in sorted(rows_by_table):
            policy = EXPORT_POLICY.get(table)
            if policy is None:
                raise ExportError(f"table {table!r} has no export policy")
            if not policy.include:
                raise ExportError(f"table {table!r} is excluded from exports: {policy.reason}")
            rows = []
            for row in rows_by_table[table]:
                owner = row.get("user_id", row.get("subject_user_id", user_id))
                if str(owner) != user_id:
                    raise ExportError(f"row in {table!r} belongs to another user")
                rows.append({k: _jsonable(v) for k, v in row.items() if k not in policy.redact})
            add(f"data/{table}.json", json.dumps(rows, indent=2, ensure_ascii=False).encode())
            columns = sorted({k for r in rows for k in r})
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(
                    {k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict | list) else v for k, v in r.items()}
                )
            add(f"data/{table}.csv", buf.getvalue().encode("utf-8-sig"))  # BOM so Excel opens UTF-8 correctly
            manifest["tables"][table] = {"rows": len(rows), "redacted_columns": list(policy.redact)}

        for name, data in original_files:
            safe = Path(name).name  # never allow paths/traversal inside the archive
            add(f"originals/{safe}", data)
        if apkg is not None:
            add("cards.apkg", apkg)
        excluded = {t: p.reason for t, p in EXPORT_POLICY.items() if not p.include}
        manifest["excluded_tables"] = excluded
        add("README.md", _readme(generated_at, excluded).encode())
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return manifest


def _readme(generated_at: datetime, excluded: Mapping[str, str]) -> str:
    lines = [
        "# Your StudyForge data export",
        "",
        f"Generated {generated_at.isoformat()}.",
        "",
        "- `data/*.json` and `data/*.csv`: every record we hold about you, one file per table.",
        "- `originals/`: the files you uploaded.",
        "- `cards.apkg`: all your flashcards, importable into Anki.",
        "- `manifest.json`: row counts and SHA-256 checksums for every file.",
        "",
        "Some internal or secret records are not included:",
        "",
    ]
    lines += [f"- `{t}`: {reason}" for t, reason in sorted(excluded.items())]
    lines += [
        "",
        "Some columns are removed from included tables (storage paths, secrets, internal ids); "
        "see `redacted_columns` in the manifest.",
    ]
    return "\n".join(lines) + "\n"
