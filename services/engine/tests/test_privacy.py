import csv
import io
import json
import re
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine.privacy.deletion import (
    Footprint,
    Residual,
    can_cancel,
    deletion_due,
    plan_deletion,
    remaining_steps,
    verify_erasure,
)
from engine.privacy.export import EXPORT_POLICY, GLOBAL_TABLES, ExportError, build_export_zip, unclassified_tables

SPEC = Path(__file__).resolve().parents[3] / "docs" / "spec" / "03 - Data Model & RLS.md"
NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


def spec_tables() -> set[str]:
    """Every table named in the data-model spec's tables (first column of each table row)."""
    text = SPEC.read_text(encoding="utf-8")
    names = set(re.findall(r"^\| `([a-z_.]+)`", text, flags=re.M))
    names |= {
        "exam_concepts",
        "support_messages",
    }  # declared inline ("exam_units / exam_concepts", "… / support_messages")
    billing = re.search(
        r"`plans`, `plan_prices`, `subscriptions`, `checkout_sessions`, `invoices` \(\+ `invoice_lines`\), "
        r"`billing_events`",
        text,
    )
    if billing:
        names |= {
            f"billing.{t}"
            for t in (
                "plans",
                "plan_prices",
                "subscriptions",
                "checkout_sessions",
                "invoices",
                "invoice_lines",
                "billing_events",
                "entitlement_overrides",
            )
        }
    names.add("audit.events")
    return names


def test_every_spec_table_is_classified() -> None:
    tables = spec_tables()
    assert len(tables) > 60  # guard: the spec parser really found the tables
    assert unclassified_tables(tables) == []


def test_policy_sanity() -> None:
    assert not EXPORT_POLICY["mfa_recovery_codes"].include
    assert "embedding" in EXPORT_POLICY["chunks"].redact
    assert "vault_secret_id" in EXPORT_POLICY["calendar_connections"].redact
    assert not (set(EXPORT_POLICY) & GLOBAL_TABLES)


def test_build_export_zip(tmp_path: Path) -> None:
    out = tmp_path / "export.zip"
    rows = {
        "cards": [
            {
                "id": "c1",
                "user_id": "u1",
                "front_md": "Q, with comma",
                "back_md": "A",
                "tags": ["x", "y"],
                "created_at": NOW,
            }
        ],
        "chunks": [{"id": "k1", "user_id": "u1", "content_md": "text", "embedding": [0.1, 0.2]}],
    }
    manifest = build_export_zip(out, "u1", NOW, rows, original_files=[("../../etc/notes.pdf", b"%PDF")], apkg=b"PK")
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert {
            "data/cards.json",
            "data/cards.csv",
            "data/chunks.json",
            "originals/notes.pdf",
            "cards.apkg",
            "README.md",
            "manifest.json",
        } <= names
        chunks = json.loads(zf.read("data/chunks.json"))
        assert "embedding" not in chunks[0]
        cards_csv = list(csv.DictReader(io.StringIO(zf.read("data/cards.csv").decode("utf-8-sig"))))
        assert cards_csv[0]["front_md"] == "Q, with comma" and json.loads(cards_csv[0]["tags"]) == ["x", "y"]
        assert json.loads(zf.read("data/cards.json"))[0]["created_at"] == NOW.isoformat()
        assert "mfa_recovery_codes" in zf.read("README.md").decode()
    assert manifest["tables"]["chunks"] == {"rows": 1, "redacted_columns": ["embedding", "fts"]}
    assert len(manifest["files"]["cards.apkg"]) == 64


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ({"mystery_table": []}, "no export policy"),
        ({"mfa_recovery_codes": []}, "excluded"),
        ({"cards": [{"id": "c9", "user_id": "someone-else"}]}, "another user"),
    ],
)
def test_export_refusals(tmp_path: Path, rows: dict, message: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ExportError, match=message):
        build_export_zip(tmp_path / "x.zip", "u1", NOW, rows)


def test_deletion_grace_period() -> None:
    requested = NOW
    assert not deletion_due(requested, NOW + timedelta(days=6, hours=23))
    assert deletion_due(requested, NOW + timedelta(days=7))
    assert can_cancel(requested, NOW + timedelta(days=3), executed=False)
    assert not can_cancel(requested, NOW + timedelta(days=8), executed=False)
    assert not can_cancel(requested, NOW + timedelta(days=1), executed=True)


def test_deletion_plan_order_and_resume() -> None:
    plan = plan_deletion(
        Footprint(
            user_id="u1",
            calendar_connected=True,
            delete_calendar_events=True,
            buckets_with_objects=("uploads", "exports"),
        )
    )
    kinds = [s.kind for s in plan]
    assert kinds.index("delete_calendar_events") < kinds.index("revoke_calendar_tokens")
    assert kinds.index("posthog_delete_person") < kinds.index("delete_auth_user")
    assert kinds[-2:] == ["delete_auth_user", "audit_completed"]
    assert [s.target for s in plan if s.kind == "delete_storage_prefix"] == ["uploads/u1/", "exports/u1/"]
    assert len({s.idempotency_key for s in plan}) == len(plan)
    rest = remaining_steps(plan, [plan[0].idempotency_key, plan[1].idempotency_key])
    assert rest == plan[2:]

    minimal = [s.kind for s in plan_deletion(Footprint(user_id="u2", analytics_person=False, llm_traces=False))]
    assert "revoke_calendar_tokens" not in minimal and "posthog_delete_person" not in minimal


def test_verify_erasure() -> None:
    assert verify_erasure([Residual(store="cards", count=0), Residual(store="uploads", count=0)]) == []
    assert verify_erasure([Residual(store="cards", count=2)]) == [Residual(store="cards", count=2)]
