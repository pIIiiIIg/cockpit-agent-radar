"""Shared, fail-closed Cursor Agent cost ledger.

The database lives outside either repository so Harness and Radar reserve from
the same Beijing-day budget.  Prompts and secrets are never persisted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

BEIJING = timezone(timedelta(hours=8))
SCHEMA_VERSION = 1
DEFAULT_SOFT_USD = 180.0
DEFAULT_HARD_USD = 200.0
DEFAULT_POOLS = {
    "harness_implementation": 110.0,
    "radar_review_report": 45.0,
    "publication": 10.0,
    "recovery_reserve": 15.0,
}
DEFAULT_RATES = {
    "source": "https://cursor.com/docs/models-and-pricing",
    "effective_date": "2026-08-10",
    "currency": "USD",
    "per_million_tokens": {
        "auto": {
            "input": 1.25, "cache_read": 0.25, "cache_write": 1.25, "output": 6.00,
            "pricing_mode": "Auto Cost only"
        },
        "composer-2.5": {
            "input": 0.50, "cache_read": 0.20, "cache_write": 0.50, "output": 2.50
        },
        "glm-5.2-high": {
            "input": 1.65, "cache_read": 0.51, "cache_write": 1.65, "output": 4.65,
            "base_api_rate": {"input": 1.40, "cache_read": 0.26, "output": 4.40},
            "cursor_token_rate": 0.25,
            "pricing_note": "conservative Teams/Enterprise effective rate"
        },
        "gpt-5.6-sol-xhigh": {
            "input": 5.00, "cache_read": 0.50, "cache_write": 6.25, "output": 30.00,
            "long_context_threshold": 272000,
            "long_input_multiplier": 2.0,
            "long_output_multiplier": 1.5,
        },
    },
}


class BudgetDenied(RuntimeError):
    def __init__(self, decision: str, reason: str):
        super().__init__(reason)
        self.decision = decision
        self.reason = reason


def ledger_root() -> Path:
    override = os.environ.get("CURSOR_COST_LEDGER_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        local = str(Path.home() / "AppData/Local")
    return Path(local) / "CursorCostGovernance"


def dashboard_baseline_path() -> Path | None:
    override = os.environ.get("CURSOR_COST_BASELINE")
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        local = str(Path.home() / "AppData/Local")
    directory = Path(local) / "StreamingModelHarness"
    preferred = directory / "cost-baseline-2026-08-04-10.json"
    if preferred.is_file():
        return preferred
    candidates = sorted(directory.glob("cost-baseline-*.json"), reverse=True)
    return candidates[0] if candidates else None


def load_dashboard_baseline() -> dict[str, Any] | None:
    """Load only public-safe aggregate Dashboard facts, never account identity."""
    path = dashboard_baseline_path()
    if path is None or not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    daily_raw = raw.get("daily", [])
    if not isinstance(daily_raw, list) or not daily_raw:
        raise ValueError("Dashboard baseline daily rows are missing")
    daily = []
    for row in daily_raw:
        if not isinstance(row, dict):
            raise ValueError("Dashboard baseline daily row must be an object")
        daily.append({
            "date": str(row["date"]),
            "calls": int(row["calls"]),
            "tokens": int(row["tokens"]),
            "cost_usd": round(float(row["cost_usd"]), 2),
            "partial": bool(row.get("partial", False)),
        })
    complete = [row for row in daily if not row["partial"]]
    if not complete:
        raise ValueError("Dashboard baseline has no complete days")
    total_cost = round(sum(row["cost_usd"] for row in daily), 2)
    total_tokens = sum(row["tokens"] for row in daily)
    total_calls = sum(row["calls"] for row in daily)
    completed_average = sum(row["cost_usd"] for row in complete) / len(complete)
    models = []
    for row in raw.get("model_costs", []):
        if not isinstance(row, dict):
            continue
        models.append({
            "model": str(row.get("model", "")),
            "cost_usd": round(float(row.get("cost_usd", 0)), 2),
            "share": round(float(row.get("share", 0)), 4),
        })
    soft = DEFAULT_SOFT_USD
    hard = DEFAULT_HARD_USD
    return {
        "source": "Cursor Usage Dashboard",
        "source_timezone": str(raw.get("timezone", "UTC")),
        "range": {
            "from": daily[0]["date"], "to": daily[-1]["date"],
            "partial_last_day": daily[-1]["partial"],
            "partial_through": raw.get("range", {}).get("note", ""),
        },
        "daily": daily,
        "totals": {
            "calls": total_calls, "tokens": total_tokens,
            "cost_usd": total_cost, "completed_days": len(complete),
            "completed_days_average_cost_usd": round(completed_average, 2),
        },
        "targets": {
            "soft_usd": soft, "hard_usd": hard,
            "reduction_to_soft_pct": round((1 - soft / completed_average) * 100, 2),
            "reduction_to_hard_pct": round((1 - hard / completed_average) * 100, 2),
        },
        "model_costs": models,
        "primary_cost_driver": max(models, key=lambda row: row["cost_usd"]) if models else None,
        "attribution": {
            "historical_pipeline_stage_available": False,
            "scope": "manual chats/subagents plus scheduled automation",
            "future_attribution": "shared ledger pipeline/stage fields",
        },
        "caveats": [
            str(value) for value in raw.get("caveats", []) if isinstance(value, str)
        ],
    }


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def sha256_text(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def hash_files(paths: Iterable[Path], extra: str = "") -> str:
    digest = hashlib.sha256(extra.encode("utf-8"))
    for path in sorted((Path(item) for item in paths), key=lambda item: str(item)):
        digest.update(str(path).replace("\\", "/").encode("utf-8"))
        if path.is_file():
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        else:
            digest.update(b"<missing>")
    return digest.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def _load_config(root: Path) -> dict[str, Any]:
    value = {
        "soft_usd": DEFAULT_SOFT_USD,
        "hard_usd": DEFAULT_HARD_USD,
        "pools": dict(DEFAULT_POOLS),
        "rates": DEFAULT_RATES,
    }
    path = Path(os.environ.get("CURSOR_COST_CONFIG", root / "cost-policy.json"))
    if path.is_file():
        supplied = json.loads(path.read_text(encoding="utf-8-sig"))
        value.update({key: supplied[key] for key in ("soft_usd", "hard_usd") if key in supplied})
        value["pools"].update(supplied.get("pools", {}))
        if supplied.get("rates"):
            value["rates"] = supplied["rates"]
    if not (0 < float(value["soft_usd"]) < float(value["hard_usd"])):
        raise ValueError("cost policy requires 0 < soft_usd < hard_usd")
    if sum(float(item) for item in value["pools"].values()) > float(value["soft_usd"]) + 1e-9:
        raise ValueError("configured pools exceed the soft budget")
    return value


def parse_agent_output(text: str) -> tuple[dict[str, int] | None, str, int, str]:
    """Return usage, session, tool-call count and result hash from JSON/JSONL."""
    events: list[dict[str, Any]] = []
    stripped = text.strip()
    if not stripped:
        return None, "", 0, sha256_text("")
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            events = [value]
    except json.JSONDecodeError:
        for line in stripped.splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    events.append(value)
            except json.JSONDecodeError:
                continue
    final = next((item for item in reversed(events) if item.get("type") == "result"), {})
    usage_raw = final.get("usage")
    usage = None
    if isinstance(usage_raw, dict):
        aliases = {
            "input_tokens": ("inputTokens", "input_tokens"),
            "output_tokens": ("outputTokens", "output_tokens"),
            "cache_read_tokens": ("cacheReadTokens", "cache_read_tokens"),
            "cache_write_tokens": ("cacheWriteTokens", "cache_write_tokens"),
        }
        usage = {}
        for target, names in aliases.items():
            raw = next((usage_raw[name] for name in names if name in usage_raw), 0)
            usage[target] = max(0, int(raw or 0))
    session = str(final.get("session_id") or next(
        (item.get("session_id") for item in events if item.get("session_id")), ""))
    tool_calls = sum(1 for item in events if item.get("type") in {
        "tool_call", "tool", "tool_use", "tool_result"
    } and item.get("type") != "tool_result")
    result_value = final.get("result", stripped)
    return usage, session, tool_calls, sha256_text(
        result_value if isinstance(result_value, str) else json.dumps(result_value, sort_keys=True))


def calculate_cost(model: str, usage: dict[str, int], rates: dict[str, Any]) -> float | None:
    table = rates.get("per_million_tokens", {}).get(model)
    if not table:
        return None
    total_input = usage["input_tokens"]
    cache_read = min(total_input, usage["cache_read_tokens"])
    cache_write = min(max(0, total_input - cache_read), usage["cache_write_tokens"])
    uncached = max(0, total_input - cache_read - cache_write)
    input_multiplier = 1.0
    output_multiplier = 1.0
    if total_input > int(table.get("long_context_threshold", 10**18)):
        input_multiplier = float(table.get("long_input_multiplier", 1.0))
        output_multiplier = float(table.get("long_output_multiplier", 1.0))
    amount = (
        uncached * float(table["input"]) * input_multiplier
        + cache_read * float(table.get("cache_read", table["input"])) * input_multiplier
        + cache_write * float(table.get("cache_write", table["input"])) * input_multiplier
        + usage["output_tokens"] * float(table["output"]) * output_multiplier
    ) / 1_000_000
    return round(amount, 8)


@dataclass(frozen=True)
class Reservation:
    call_id: str
    decision: str
    reason: str
    date: str
    reservation_usd: float


class CostLedger:
    def __init__(self, root: Path | None = None, now: datetime | None = None):
        self.root = (root or ledger_root()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "cost-ledger.sqlite3"
        self.now = now.astimezone(BEIJING) if now else beijing_now()
        self.config = _load_config(self.root)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @contextmanager
    def connection(self):
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS calls (
                    id TEXT PRIMARY KEY, date TEXT NOT NULL, pipeline TEXT NOT NULL,
                    stage TEXT NOT NULL, pool TEXT NOT NULL, model TEXT NOT NULL,
                    chat_session TEXT NOT NULL DEFAULT '', attempt INTEGER NOT NULL,
                    started_at TEXT NOT NULL, ended_at TEXT, tool_calls INTEGER,
                    input_tokens INTEGER, output_tokens INTEGER,
                    cache_read_tokens INTEGER, cache_write_tokens INTEGER,
                    actual_usd REAL, estimated_usd REAL NOT NULL,
                    usage_source TEXT NOT NULL, input_hash TEXT NOT NULL,
                    result_hash TEXT, status TEXT NOT NULL, error TEXT
                );
                CREATE INDEX IF NOT EXISTS calls_date_idx ON calls(date);
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY, date TEXT NOT NULL, created_at TEXT NOT NULL,
                    pipeline TEXT NOT NULL, stage TEXT NOT NULL, pool TEXT NOT NULL,
                    model TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL,
                    requested_usd REAL NOT NULL, input_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY, kind TEXT NOT NULL, input_hash TEXT NOT NULL,
                    prompt_version TEXT NOT NULL, model TEXT NOT NULL, result_hash TEXT NOT NULL,
                    artifact TEXT NOT NULL, created_at TEXT NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0, last_hit_at TEXT
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(cache)")}
            if "hit_count" not in columns:
                db.execute("ALTER TABLE cache ADD COLUMN hit_count INTEGER NOT NULL DEFAULT 0")
            if "last_hit_at" not in columns:
                db.execute("ALTER TABLE cache ADD COLUMN last_hit_at TEXT")

    @property
    def date(self) -> str:
        return self.now.date().isoformat()

    def reserve(
        self, *, pipeline: str, stage: str, pool: str, model: str,
        chat_session: str, attempt: int, reservation_usd: float, input_hash: str,
    ) -> Reservation:
        if reservation_usd <= 0:
            raise ValueError("reservation_usd must be positive")
        if pool not in self.config["pools"]:
            raise ValueError(f"unknown cost pool: {pool}")
        call_id = str(uuid.uuid4())
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            used = float(db.execute("""
                SELECT COALESCE(SUM(MAX(estimated_usd, COALESCE(actual_usd, 0))), 0)
                FROM calls WHERE date=? AND status IN ('reserved','completed','failed')
            """, (self.date,)).fetchone()[0])
            pool_used = float(db.execute("""
                SELECT COALESCE(SUM(MAX(estimated_usd, COALESCE(actual_usd, 0))), 0)
                FROM calls WHERE date=? AND pool=? AND status IN ('reserved','completed','failed')
            """, (self.date, pool)).fetchone()[0])
            projected = used + reservation_usd
            pool_projected = pool_used + reservation_usd
            decision, reason = "allowed", "within budget"
            if projected > float(self.config["hard_usd"]):
                decision, reason = "blocked", "daily hard budget would be exceeded"
            elif projected > float(self.config["soft_usd"]):
                decision, reason = "queued", "daily soft budget reached; no new Agent calls"
            elif pool_projected > float(self.config["pools"][pool]):
                decision, reason = "queued", f"{pool} pool would be exceeded"
            if decision != "allowed":
                db.execute("""
                    INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    call_id, self.date, self.now.isoformat(), pipeline, stage, pool,
                    model, decision, reason, reservation_usd, input_hash,
                ))
                db.commit()
                raise BudgetDenied(decision, reason)
            db.execute("""
                INSERT INTO calls (
                    id,date,pipeline,stage,pool,model,chat_session,attempt,started_at,
                    estimated_usd,usage_source,input_hash,status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                call_id, self.date, pipeline, stage, pool, model, chat_session,
                attempt, self.now.isoformat(), reservation_usd,
                "pending_cli_usage", input_hash, "reserved",
            ))
            db.commit()
        return Reservation(call_id, decision, reason, self.date, reservation_usd)

    def reconcile(
        self, call_id: str, output: str, *, failed: bool = False, error: str = ""
    ) -> dict[str, Any]:
        usage, session, tool_calls, result_hash = parse_agent_output(output)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if not row:
                raise KeyError(call_id)
            actual = calculate_cost(row["model"], usage, self.config["rates"]) if usage else None
            source = "cursor_cli_final_usage" if actual is not None else "reservation_fallback"
            values = usage or {
                "input_tokens": None, "output_tokens": None,
                "cache_read_tokens": None, "cache_write_tokens": None,
            }
            db.execute("""
                UPDATE calls SET ended_at=?,chat_session=?,tool_calls=?,input_tokens=?,
                    output_tokens=?,cache_read_tokens=?,cache_write_tokens=?,actual_usd=?,
                    usage_source=?,result_hash=?,status=?,error=? WHERE id=?
            """, (
                beijing_now().isoformat(), session or row["chat_session"], tool_calls,
                values["input_tokens"], values["output_tokens"],
                values["cache_read_tokens"], values["cache_write_tokens"], actual,
                source, result_hash, "failed" if failed else "completed",
                error[:1000] if error else None, call_id,
            ))
            db.commit()
        self.write_reports()
        return {
            "call_id": call_id, "actual_usd": actual, "usage_source": source,
            "usage": usage, "result_hash": result_hash, "tool_calls": tool_calls,
        }

    def cache_get(self, kind: str, input_hash: str, prompt_version: str, model: str) -> dict[str, Any] | None:
        key = sha256_text("\0".join((kind, input_hash, prompt_version, model)))
        with self.connection() as db:
            row = db.execute("SELECT * FROM cache WHERE cache_key=?", (key,)).fetchone()
            if row:
                db.execute(
                    "UPDATE cache SET hit_count=hit_count+1,last_hit_at=? WHERE cache_key=?",
                    (beijing_now().isoformat(), key))
            return dict(row) if row else None

    def cache_put(
        self, kind: str, input_hash: str, prompt_version: str, model: str,
        result_hash: str, artifact: str,
    ) -> None:
        key = sha256_text("\0".join((kind, input_hash, prompt_version, model)))
        with self.connection() as db:
            db.execute("""
                INSERT INTO cache (
                    cache_key,kind,input_hash,prompt_version,model,result_hash,
                    artifact,created_at,hit_count,last_hit_at
                ) VALUES (?,?,?,?,?,?,?,?,0,NULL)
                ON CONFLICT(cache_key) DO UPDATE SET
                    result_hash=excluded.result_hash,artifact=excluded.artifact,
                    created_at=excluded.created_at
            """, (
                key, kind, input_hash, prompt_version, model, result_hash,
                artifact, beijing_now().isoformat(),
            ))

    def summary(self, date: str | None = None) -> dict[str, Any]:
        day = date or self.date
        with self.connection() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM calls WHERE date=? ORDER BY started_at", (day,))]
            decisions = [dict(row) for row in db.execute(
                "SELECT * FROM decisions WHERE date=? ORDER BY created_at", (day,))]
            cache_count = int(db.execute("""
                SELECT COALESCE(SUM(hit_count),0) FROM cache
                WHERE substr(COALESCE(last_hit_at,''),1,10)=?
            """, (day,)).fetchone()[0])
        charged = sum(max(row["estimated_usd"], row["actual_usd"] or 0.0) for row in rows)
        actual = sum(row["actual_usd"] or 0.0 for row in rows)
        active = sum(row["estimated_usd"] for row in rows if row["status"] == "reserved")
        by_model: dict[str, int] = {}
        for row in rows:
            by_model[row["model"]] = by_model.get(row["model"], 0) + 1
        return {
            "schema_version": SCHEMA_VERSION, "date": day, "timezone": "Asia/Shanghai",
            "budget": {
                "soft_usd": self.config["soft_usd"], "hard_usd": self.config["hard_usd"],
                "pools": self.config["pools"],
            },
            "actual_usd": round(actual, 8), "active_reservations_usd": round(active, 8),
            "hard_gate_exposure_usd": round(charged, 8),
            "calls": len(rows), "models": by_model, "cache_hits": cache_count,
            "retry_waste_usd": round(sum(
                max(row["estimated_usd"], row["actual_usd"] or 0.0)
                for row in rows if row["attempt"] > 1), 8),
            "blocked_or_queued": decisions,
            "token_accounting": (
                "actual where cursor_cli_final_usage is present; otherwise estimated reservation"
            ),
            "rates": self.config["rates"],
            "dashboard_baseline": load_dashboard_baseline(),
        }

    def write_reports(self, date: str | None = None) -> tuple[Path, Path]:
        report = self.summary(date)
        day = report["date"]
        json_path = self.root / "reports" / f"{day}.json"
        markdown_path = self.root / "reports" / f"{day}.md"
        _atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        lines = [
            f"# Cursor Agent cost report — {day}",
            "",
            f"- Budget: ${report['budget']['soft_usd']:.2f} soft / ${report['budget']['hard_usd']:.2f} hard",
            f"- Actual observed: ${report['actual_usd']:.4f}",
            f"- Active reservations: ${report['active_reservations_usd']:.4f}",
            f"- Hard-gate exposure: ${report['hard_gate_exposure_usd']:.4f}",
            f"- Calls: {report['calls']}; cache hits: {report['cache_hits']}",
            f"- Models: {json.dumps(report['models'], ensure_ascii=False, sort_keys=True)}",
            f"- Retry waste: ${report['retry_waste_usd']:.4f}",
            f"- Budget decisions: {len(report['blocked_or_queued'])}",
        ]
        baseline = report.get("dashboard_baseline")
        if baseline:
            driver = baseline.get("primary_cost_driver") or {}
            lines.extend([
                "",
                "## Cursor Usage Dashboard baseline",
                "",
                f"- Range: {baseline['range']['from']} through {baseline['range']['to']} "
                f"({baseline['source_timezone']}; last day partial={baseline['range']['partial_last_day']})",
                f"- Total: ${baseline['totals']['cost_usd']:.2f}; "
                f"{baseline['totals']['tokens']:,} tokens; {baseline['totals']['calls']} calls",
                f"- Complete-day average: ${baseline['totals']['completed_days_average_cost_usd']:.2f}",
                f"- Required reduction: {baseline['targets']['reduction_to_soft_pct']:.2f}% "
                f"to soft / {baseline['targets']['reduction_to_hard_pct']:.2f}% to hard",
                f"- Primary model cost driver: {driver.get('model', 'unknown')} "
                f"${float(driver.get('cost_usd', 0)):.2f} "
                f"({float(driver.get('share', 0)) * 100:.2f}%)",
                "- Attribution caveat: historical Dashboard totals combine manual chats/subagents "
                "and scheduled automation; exact pipeline/stage attribution begins with this ledger.",
            ])
        lines.extend([
            "",
            "Token accounting is actual only when Cursor CLI final usage is available; "
            "otherwise the report explicitly retains the conservative estimate.",
        ])
        _atomic_write(markdown_path, "\n".join(lines) + "\n")
        return json_path, markdown_path

    def write_public_status(
        self, path: Path, date: str | None = None, extra: dict[str, int] | None = None
    ) -> None:
        report = self.summary(date)
        safe = {
            key: report[key] for key in (
                "schema_version", "date", "timezone", "budget", "actual_usd",
                "active_reservations_usd", "hard_gate_exposure_usd", "calls",
                "models", "cache_hits", "retry_waste_usd", "token_accounting",
            )
        }
        safe["blocked_or_queued_count"] = len(report["blocked_or_queued"])
        safe["dashboard_baseline"] = report.get("dashboard_baseline")
        prior: dict[str, Any] = {}
        if path.is_file():
            try:
                prior = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                prior = {}
        safe["queued_fulltext_papers"] = int(
            prior.get("queued_fulltext_papers", 0))
        safe["queued_harness_candidates"] = int(
            prior.get("queued_harness_candidates", 0))
        safe.update(extra or {})
        _atomic_write(path, json.dumps(safe, ensure_ascii=False, indent=2) + "\n")


def _main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    reserve = sub.add_parser("reserve")
    for name in ("pipeline", "stage", "pool", "model", "chat-session", "input-hash"):
        reserve.add_argument(f"--{name}", required=name not in {"chat-session"})
    reserve.add_argument("--attempt", type=int, required=True)
    reserve.add_argument("--reservation-usd", type=float, required=True)
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--call-id", required=True)
    reconcile.add_argument("--output-file", type=Path, required=True)
    reconcile.add_argument("--failed", action="store_true")
    reconcile.add_argument("--error", default="")
    cache_get = sub.add_parser("cache-get")
    cache_put = sub.add_parser("cache-put")
    for command in (cache_get, cache_put):
        command.add_argument("--kind", required=True)
        command.add_argument("--input-hash", required=True)
        command.add_argument("--prompt-version", required=True)
        command.add_argument("--model", required=True)
    cache_put.add_argument("--result-hash", required=True)
    cache_put.add_argument("--artifact", required=True)
    report = sub.add_parser("report")
    report.add_argument("--public-status", type=Path)
    report.add_argument("--queued-fulltext-papers", type=int)
    report.add_argument("--queued-harness-candidates", type=int)
    args = parser.parse_args()
    ledger = CostLedger()
    if args.command == "reserve":
        try:
            value = ledger.reserve(
                pipeline=args.pipeline, stage=args.stage, pool=args.pool, model=args.model,
                chat_session=args.chat_session or "", attempt=args.attempt,
                reservation_usd=args.reservation_usd, input_hash=args.input_hash,
            )
            print(json.dumps(value.__dict__))
            return 0
        except BudgetDenied as exc:
            print(json.dumps({"decision": exc.decision, "reason": exc.reason}))
            return 4 if exc.decision == "blocked" else 3
    if args.command == "reconcile":
        text = args.output_file.read_text(encoding="utf-8", errors="replace")
        print(json.dumps(ledger.reconcile(
            args.call_id, text, failed=args.failed, error=args.error)))
        return 0
    if args.command == "cache-get":
        value = ledger.cache_get(
            args.kind, args.input_hash, args.prompt_version, args.model)
        print(json.dumps(value or {}))
        return 0 if value else 1
    if args.command == "cache-put":
        ledger.cache_put(
            args.kind, args.input_hash, args.prompt_version, args.model,
            args.result_hash, args.artifact)
        return 0
    ledger.write_reports()
    if args.public_status:
        extra = {}
        if args.queued_fulltext_papers is not None:
            extra["queued_fulltext_papers"] = max(0, args.queued_fulltext_papers)
        if args.queued_harness_candidates is not None:
            extra["queued_harness_candidates"] = max(0, args.queued_harness_candidates)
        ledger.write_public_status(args.public_status, extra=extra)
    print(json.dumps(ledger.summary(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
