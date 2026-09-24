"""SQLite adatbázis réteg – ORM nélkül (stdlib sqlite3).

- Kérésenként új kapcsolat, WAL + foreign_keys.
- Séma létrehozása idempotensen.
- Szavazat: egy tranzakció, teljes backend validálás.
- Duplikált szavazat: UNIQUE(question_id, voter_id) megsértése -> 409.
"""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  text       TEXT NOT NULL,
  type       TEXT NOT NULL CHECK (type IN ('single','multi')),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS options (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  text        TEXT NOT NULL,
  position    INTEGER NOT NULL,
  UNIQUE (question_id, position)
);

CREATE TABLE IF NOT EXISTS votes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  voter_id    TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (question_id, voter_id)
);

CREATE TABLE IF NOT EXISTS vote_options (
  vote_id   INTEGER NOT NULL REFERENCES votes(id)   ON DELETE CASCADE,
  option_id INTEGER NOT NULL REFERENCES options(id) ON DELETE CASCADE,
  PRIMARY KEY (vote_id, option_id)
);

CREATE TABLE IF NOT EXISTS state (
  id                 INTEGER PRIMARY KEY CHECK (id = 1),
  active_question_id INTEGER REFERENCES questions(id) ON DELETE SET NULL
);
"""


class VoteError(Exception):
    """Szavazati hiba: status_code + magyar üzenet."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class AlreadyVotedError(VoteError):
    def __init__(self, message: str = "Erre a kérdésre már szavaztál."):
        super().__init__(409, message)


class InvalidVoteError(VoteError):
    def __init__(self, message: str):
        super().__init__(400, message)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO state (id, active_question_id) VALUES (1, NULL)")
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Kérdések (admin)
# --------------------------------------------------------------------------

def create_question(text: str, qtype: str, options: list[str]) -> int:
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute("INSERT INTO questions (text, type) VALUES (?, ?)", (text, qtype))
            qid = cur.lastrowid
            for i, opt in enumerate(options, 1):
                conn.execute(
                    "INSERT INTO options (question_id, text, position) VALUES (?, ?, ?)",
                    (qid, opt, i),
                )
        return qid
    finally:
        conn.close()


def list_questions() -> list[dict]:
    """Minden kérdés opciókkal és szavazatszámokkal (admin állapot)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT q.id, q.text, q.type, s.active_question_id,
                   (SELECT COUNT(*) FROM votes v WHERE v.question_id = q.id) AS total_votes
            FROM questions q, state s
            WHERE s.id = 1
            ORDER BY q.id
            """
        ).fetchall()
        result: list[dict] = []
        for q in rows:
            options = conn.execute(
                """
                SELECT o.id, o.text, o.position,
                       (SELECT COUNT(*)
                          FROM vote_options vo JOIN votes v ON v.id = vo.vote_id
                         WHERE vo.option_id = o.id AND v.question_id = ?) AS votes
                  FROM options o
                 WHERE o.question_id = ?
                 ORDER BY o.position
                """,
                (q["id"], q["id"]),
            ).fetchall()
            total = q["total_votes"] or 0
            result.append(
                {
                    "id": q["id"],
                    "text": q["text"],
                    "type": q["type"],
                    "is_active": q["active_question_id"] == q["id"],
                    "total_votes": total,
                    "options": [
                        {
                            "id": o["id"],
                            "text": o["text"],
                            "votes": o["votes"],
                            "pct": round((o["votes"] / total) * 100, 1) if total else 0,
                        }
                        for o in options
                    ],
                }
            )
        return result
    finally:
        conn.close()


def publish_question(question_id: int) -> bool:
    """Az adott kérdés lesz az aktív; a state egysoros tábla garantálja az egyediséget."""
    conn = get_conn()
    try:
        with conn:
            exists = conn.execute("SELECT 1 FROM questions WHERE id = ?", (question_id,)).fetchone()
            if exists is None:
                return False
            conn.execute("UPDATE state SET active_question_id = ? WHERE id = 1", (question_id,))
        return True
    finally:
        conn.close()


def reset_all() -> None:
    """Minden kérdés (és vele a szavazatok) törlése; aktív kérdés visszaállítása."""
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM questions")
            conn.execute("UPDATE state SET active_question_id = NULL WHERE id = 1")
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Résztvevő: állapot + szavazat
# --------------------------------------------------------------------------

def get_active_question() -> dict | None:
    """Az aktív kérdés opciókkal, vagy None."""
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT q.id, q.text, q.type
              FROM questions q, state s
             WHERE s.id = 1 AND s.active_question_id = q.id
            """
        ).fetchone()
        if row is None:
            return None
        options = conn.execute(
            "SELECT id, text FROM options WHERE question_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        return {
            "id": row["id"],
            "text": row["text"],
            "type": row["type"],
            "options": [{"id": o["id"], "text": o["text"]} for o in options],
        }
    finally:
        conn.close()


def has_voted(question_id: int, voter_id: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM votes WHERE question_id = ? AND voter_id = ?",
            (question_id, voter_id),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def submit_vote(question_id: int, voter_id: str, option_ids: list[int]) -> None:
    """Szavazat mentése egyetlen tranzakcióban, teljes validálással.

    Hiba esetén VoteError kivételt dob; ütköző UNIQUE -> 409.
    """
    if not option_ids:
        raise InvalidVoteError("Legalább egy opciót ki kell választani.")
    if len(set(option_ids)) != len(option_ids):
        raise InvalidVoteError("Egy opció csak egyszer választható.")

    conn = get_conn()
    try:
        with conn:
            # Csak az aktuálisan publikált kérdésre lehet szavazni
            q = conn.execute(
                """
                SELECT q.id, q.type
                  FROM questions q, state s
                 WHERE s.id = 1 AND s.active_question_id = q.id
                """
            ).fetchone()
            if q is None or q["id"] != question_id:
                raise InvalidVoteError("Ez a kérdés jelenleg nem aktív – nem lehet rá szavazni.")

            if q["type"] == "single" and len(option_ids) != 1:
                raise InvalidVoteError("Single kérdésnél pontosan egy opciót kell választani.")

            # A megadott opciók ehhez a kérdéshez tartoznak-e
            placeholders = ",".join("?" * len(option_ids))
            found = conn.execute(
                f"SELECT id FROM options WHERE question_id = ? AND id IN ({placeholders})",
                [question_id, *option_ids],
            ).fetchall()
            if len(found) != len(set(option_ids)):
                raise InvalidVoteError("Érvénytelen opció – nem tartozik ehhez a kérdéshez.")

            # Duplikátum (backend kényszerítés, UI függetlenül)
            dup = conn.execute(
                "SELECT 1 FROM votes WHERE question_id = ? AND voter_id = ?",
                (question_id, voter_id),
            ).fetchone()
            if dup is not None:
                raise AlreadyVotedError()

            cur = conn.execute(
                "INSERT INTO votes (question_id, voter_id) VALUES (?, ?)",
                (question_id, voter_id),
            )
            vote_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO vote_options (vote_id, option_id) VALUES (?, ?)",
                [(vote_id, oid) for oid in option_ids],
            )
    except VoteError:
        raise
    except sqlite3.IntegrityError as exc:
        # UNIQUE(question_id, voter_id) – versenyhelyzetben is 409
        raise AlreadyVotedError() from exc
    finally:
        conn.close()