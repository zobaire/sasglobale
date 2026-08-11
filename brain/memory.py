"""Long-term memory: ChromaDB semantic facts + SQLite conversation summaries."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from sqlalchemy import create_engine, text

from brain.config import load_config


_FACT_TRIGGERS = [
    "my name is", "i am", "i'm", "i work", "i like", "i hate",
    "i love", "i prefer", "i need", "i want", "i use", "i have",
    "i live", "i go to", "i study", "i play", "i own",
    "my favorite", "my email", "my phone", "my address",
    "my birthday", "my password", "my project", "my computer",
    "remember that", "remember this", "don't forget", "keep in mind",
    "call me", "i usually", "i always", "i never",
]


def _repo_root() -> Path:
    return Path(__file__).parent.parent


class Memory:
    """Semantic fact store + conversation summary store."""

    def __init__(
        self,
        db_path: str | None = None,
        chroma_path: str | None = None,
        top_k: int | None = None,
    ):
        cfg = load_config().get("memory", {})
        self._top_k = top_k if top_k is not None else cfg.get("top_k", 3)

        db_path = db_path or str(_repo_root() / cfg.get("db_path", "memory_data/memory.db"))
        chroma_path = chroma_path or str(_repo_root() / cfg.get("chroma_path", "memory_data/chroma"))

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(chroma_path).mkdir(parents=True, exist_ok=True)

        self._engine = create_engine(f"sqlite:///{db_path}")
        self._chroma = chromadb.PersistentClient(path=chroma_path)
        self._facts = self._chroma.get_or_create_collection("facts")
        self._setup_db()

    def _setup_db(self) -> None:
        with self._engine.connect() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS summaries "
                "(id INTEGER PRIMARY KEY, content TEXT, created_at TEXT)"
            ))
            conn.commit()

    def store_fact(self, fact: str) -> None:
        """Store a semantic fact. Identical facts are deduplicated by hash ID."""
        fact_id = hashlib.md5(fact.encode()).hexdigest()
        self._facts.upsert(ids=[fact_id], documents=[fact])

    def search_facts(self, query: str, top_k: int | None = None) -> list[str]:
        """Return semantically relevant facts for the query."""
        k = top_k if top_k is not None else self._top_k
        count = self._facts.count()
        if count == 0:
            return []
        results = self._facts.query(query_texts=[query], n_results=min(k, count))
        return [d for d in results.get("documents", [[]])[0] if d]

    def save_conversation_summary(self, summary: str) -> None:
        with self._engine.connect() as conn:
            conn.execute(
                text("INSERT INTO summaries (content, created_at) VALUES (:c, :t)"),
                {"c": summary, "t": datetime.now(timezone.utc).isoformat()},
            )
            conn.commit()

    def get_recent_summaries(self, n: int = 5) -> list[str]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT content FROM summaries ORDER BY id DESC LIMIT :n"),
                {"n": n},
            ).fetchall()
        return [r[0] for r in rows]

    def extract_and_store_facts(self, assistant_response: str, user_message: str) -> None:
        """Store user message as a fact when it contains personal info or preferences."""
        lowered = user_message.lower()
        if any(t in lowered for t in _FACT_TRIGGERS):
            self.store_fact(user_message)

    def load_legacy_facts(self) -> list[str]:
        """Load facts from legacy facts.json and notes.md into the prompt."""
        facts_path = _repo_root() / "memory_data" / "facts.json"
        notes_path = _repo_root() / "memory_data" / "notes.md"
        lines: list[str] = []
        if facts_path.exists():
            try:
                facts = json.loads(facts_path.read_text(encoding="utf-8"))
                for f in facts:
                    lines.append(f"- {f.get('text', '')}")
            except Exception:
                pass
        if notes_path.exists():
            try:
                for line in notes_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("- "):
                        lines.append(line)
            except Exception:
                pass
        return lines

    def load_routines(self) -> list[dict]:
        """Load learned routines from memory_data/routines/*.json."""
        routines_dir = _repo_root() / "memory_data" / "routines"
        routines: list[dict] = []
        if routines_dir.exists():
            for rf in sorted(routines_dir.glob("*.json")):
                try:
                    d = json.loads(rf.read_text(encoding="utf-8"))
                    if d.get("name"):
                        routines.append(d)
                except Exception:
                    pass
        return routines
