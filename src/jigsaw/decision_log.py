"""Decision log component for Jigsaw game AI."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any
from pydantic import BaseModel, Field


# The log file's layout version, stored in SQLite's PRAGMA user_version.
# 1: v0.1.0's table. Those files never set user_version, so they read as 0.
# 2: adds cheap_choice and cheap_rung.
SCHEMA_VERSION = 2

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game TEXT NOT NULL,
    turn INTEGER NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    situation TEXT NOT NULL,
    options TEXT NOT NULL,
    rung INTEGER NOT NULL,
    escalated_because TEXT NOT NULL,
    choice TEXT NOT NULL,
    primitives TEXT NOT NULL,
    legality TEXT NOT NULL,
    outcome TEXT,
    outcome_turn INTEGER,
    created_at TEXT NOT NULL,
    cheap_choice TEXT,
    cheap_rung INTEGER
)
"""

# Steps that move a file from version N-1 to N, keyed by N.
_MIGRATIONS: dict[int, list[str]] = {
    2: [
        "ALTER TABLE decisions ADD COLUMN cheap_choice TEXT",
        "ALTER TABLE decisions ADD COLUMN cheap_rung INTEGER",
    ],
}


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class Option(BaseModel):
    """Candidate option considered for a decision."""

    name: str
    score: float | None = None
    note: str = ""


class Decision(BaseModel):
    """A single recorded game decision across any rung."""

    id: int | None = None
    game: str
    turn: int
    actor: str
    kind: str
    situation: str
    options: list[Option] = Field(default_factory=list)
    rung: int = Field(ge=0, le=7)
    escalated_because: str = ""
    choice: str
    primitives: list[dict[str, Any]] = Field(default_factory=list)
    legality: list[dict[str, Any]] = Field(default_factory=list)
    outcome: str | None = None
    outcome_turn: int | None = None
    created_at: str = Field(default_factory=_utc_now_iso)
    # What the cheap rung chose when the gate escalated past it. None when the decision did
    # not escalate, or when no cheap rung answered. Comparing these with choice and rung gives
    # the agreement rate between cheap and strong rungs.
    cheap_choice: str | None = None
    cheap_rung: int | None = Field(default=None, ge=0, le=7)


class DecisionLog:
    """SQLite-backed decision log for recording and querying game decisions.

    Safe to share between threads: a game loop that decides for several factions at once
    (Parley answers each seat on its own thread) uses one log. One connection, one lock.
    """

    def __init__(self, path: str | Path) -> None:
        """Open the decision log database at path and ensure schema exists."""
        if isinstance(path, (str, Path)) and str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _schema_version(self) -> int:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"decision log {self._path} is schema version {version}, newer than this "
                f"Jigsaw supports ({SCHEMA_VERSION}); upgrade Jigsaw to open it"
            )
        return version

    def _init_db(self) -> None:
        """Create the table in a new file, or migrate an older file up to SCHEMA_VERSION.

        A file that is already current is opened without taking a write lock, so read-only
        copies open and a busy writer elsewhere does not block the open. Otherwise the work
        runs in one write transaction (BEGIN IMMEDIATE): a second process opening the same
        file waits, then sees the finished result instead of migrating it twice.
        """
        with self._lock:
            if self._schema_version() == SCHEMA_VERSION:
                return
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                version = self._schema_version()
                has_table = self._conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'decisions'"
                ).fetchone()
                if not has_table:
                    self._conn.execute(_CREATE_TABLE)
                else:
                    # A file with the table but no version number is version 1.
                    for step in range(max(version, 1) + 1, SCHEMA_VERSION + 1):
                        for sql in _MIGRATIONS[step]:
                            self._conn.execute(sql)
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_decisions_query "
                    "ON decisions(game, actor, kind, rung, turn)"
                )
                self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise

    def _row_to_decision(self, row: sqlite3.Row) -> Decision:
        """Convert a database row into a Decision model instance."""
        options_raw = json.loads(row["options"])
        options = [Option.model_validate(opt) for opt in options_raw]
        return Decision(
            id=row["id"],
            game=row["game"],
            turn=row["turn"],
            actor=row["actor"],
            kind=row["kind"],
            situation=row["situation"],
            options=options,
            rung=row["rung"],
            escalated_because=row["escalated_because"],
            choice=row["choice"],
            primitives=json.loads(row["primitives"]),
            legality=json.loads(row["legality"]),
            outcome=row["outcome"],
            outcome_turn=row["outcome_turn"],
            created_at=row["created_at"],
            cheap_choice=row["cheap_choice"],
            cheap_rung=row["cheap_rung"],
        )

    def record(self, d: Decision) -> int:
        """Record a decision and return the newly assigned decision ID."""
        options_json = json.dumps([opt.model_dump() for opt in d.options])
        primitives_json = json.dumps(d.primitives)
        legality_json = json.dumps(d.legality)

        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO decisions (
                    game, turn, actor, kind, situation, options, rung,
                    escalated_because, choice, primitives, legality,
                    outcome, outcome_turn, created_at, cheap_choice, cheap_rung
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d.game,
                    d.turn,
                    d.actor,
                    d.kind,
                    d.situation,
                    options_json,
                    d.rung,
                    d.escalated_because,
                    d.choice,
                    primitives_json,
                    legality_json,
                    d.outcome,
                    d.outcome_turn,
                    d.created_at,
                    d.cheap_choice,
                    d.cheap_rung,
                ),
            )
            new_id = cursor.lastrowid
            if new_id is None:
                raise RuntimeError("Failed to retrieve row id after insert.")
            d.id = new_id
            return new_id

    def set_outcome(self, id: int, outcome: str, turn: int | None = None) -> None:
        """Update the outcome and outcome turn for an existing decision."""
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE decisions SET outcome = ?, outcome_turn = ? WHERE id = ?",
                (outcome, turn, id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Decision with id {id} not found.")

    def get(self, id: int) -> Decision:
        """Fetch a single decision by its ID."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM decisions WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise KeyError(f"Decision with id {id} not found.")
        return self._row_to_decision(row)

    def query(
        self,
        game: str | None = None,
        actor: str | None = None,
        kind: str | None = None,
        rung: int | None = None,
        since_turn: int | None = None,
    ) -> list[Decision]:
        """Query decisions with optional filters, returning newest first."""
        clauses: list[str] = []
        params: list[Any] = []

        if game is not None:
            clauses.append("game = ?")
            params.append(game)
        if actor is not None:
            clauses.append("actor = ?")
            params.append(actor)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if rung is not None:
            clauses.append("rung = ?")
            params.append(rung)
        if since_turn is not None:
            clauses.append("turn >= ?")
            params.append(since_turn)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query_sql = f"SELECT * FROM decisions {where_clause} ORDER BY id DESC"

        with self._lock:
            rows = self._conn.execute(query_sql, params).fetchall()
        return [self._row_to_decision(row) for row in rows]

    def rung_counts(self, game: str) -> dict[int, int]:
        """Return the count of decisions per rung for the specified game."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT rung, COUNT(*) FROM decisions WHERE game = ? GROUP BY rung",
                (game,),
            ).fetchall()
        return {int(row[0]): int(row[1]) for row in rows}

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "DecisionLog":
        """Support context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Support context manager exit by closing the database."""
        self.close()
