import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ingest import read_sources, chunk_sections
from local_model import embed, model_digest

STOPWORDS = set("a an and are as at be by can do does for from how i in is it of on or that the this to was what when where which who why with you".split())

def build_index(sources, output, embedding_model=None):
    output = Path(output)
    if output.exists():
        raise ValueError("Choose a new index path to preserve the previous version")
    sections, files, audit = read_sources(sources)
    chunks = chunk_sections(sections)
    if not chunks:
        raise ValueError("No usable text found")
    model_hash = model_digest(embedding_model) if embedding_model else None
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(output.suffix + ".building")
    if pending.exists():
        raise ValueError("An unfinished build exists at " + str(pending))
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "files": files,
                "audit": audit, "chunks": len(chunks), "chunk_words": 220, "overlap_words": 40,
                "embedding_model": embedding_model, "embedding_digest": model_hash, "complete": False}
    with closing(sqlite3.connect(pending)) as db, db:
        db.executescript("CREATE TABLE chunks (id TEXT PRIMARY KEY, section_id TEXT, title TEXT, heading TEXT, text TEXT, url TEXT, pages TEXT, vector BLOB);"
                         "CREATE VIRTUAL TABLE passages USING fts5(title, heading, text, content='chunks', content_rowid='rowid');"
                         "CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT);")
        for start in range(0, len(chunks), 32):
            batch = chunks[start:start + 32]
            vectors = embed([row["title"] + "\n" + row["heading"] + "\n" + row["text"] for row in batch], embedding_model) if embedding_model else [None] * len(batch)
            if len(vectors) != len(batch):
                raise ValueError("Embedding count does not match the batch")
            for row, vector in zip(batch, vectors):
                blob = None if vector is None else np.asarray(vector, dtype=np.float32).tobytes()
                db.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)", (row["id"], row["section_id"], row["title"], row["heading"], row["text"], row["url"], json.dumps(row["pages"]), blob))
        db.execute("INSERT INTO passages(passages) VALUES ('rebuild')")
        manifest["complete"] = True
        db.execute("INSERT INTO metadata VALUES ('manifest', ?)", (json.dumps(manifest),))
    pending.rename(output)
    return {key: manifest[key] for key in ("audit", "chunks", "embedding_model", "complete")}

class SearchIndex:
    def __init__(self, path):
        self.path = Path(path).resolve()
        with closing(self.connect()) as db:
            self.manifest = json.loads(db.execute("SELECT value FROM metadata WHERE name='manifest'").fetchone()[0])
        if not self.manifest["complete"]:
            raise ValueError("Index is incomplete")

    def connect(self):
        return sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)

    def titles(self):
        with closing(self.connect()) as db:
            return [row[0] for row in db.execute("SELECT DISTINCT title FROM chunks ORDER BY title")]

    def search(self, question, mode="lexical", limit=5, book=""):
        if not question.strip() or len(question) > 2000 or not 1 <= limit <= 20:
            raise ValueError("Enter a question up to 2,000 characters and a limit from 1 to 20")
        if mode not in {"lexical", "hybrid"}:
            raise ValueError("Search mode must be lexical or hybrid")
        terms = [word for word in re.findall(r"\w+", question.casefold()) if word not in STOPWORDS]
        scores = Counter()
        with closing(self.connect()) as db:
            db.row_factory = sqlite3.Row
            if terms:
                expression = " OR ".join('"' + word + '"' for word in dict.fromkeys(terms))
                lexical = db.execute("SELECT c.rowid FROM passages JOIN chunks c ON c.rowid=passages.rowid WHERE passages MATCH ? AND instr(lower(c.title), lower(?)) > 0 ORDER BY bm25(passages, 2, 1.5, 1) LIMIT 100", (expression, book)).fetchall()
                for rank, row in enumerate(lexical, 1):
                    scores[row[0]] += 1 / (60 + rank)
            if mode == "hybrid":
                model = self.manifest["embedding_model"]
                if not model:
                    raise ValueError("Build an index with an embedding model for hybrid search")
                if model_digest(model) != self.manifest["embedding_digest"]:
                    raise ValueError("Embedding model changed; rebuild the index")
                rows = db.execute("SELECT rowid, vector FROM chunks WHERE instr(lower(title), lower(?)) > 0", (book,)).fetchall()
                if rows:
                    matrix = np.stack([np.frombuffer(row["vector"], dtype=np.float32) for row in rows])
                    query = np.asarray(embed([question], model, query=True)[0], dtype=np.float32)
                    similarity = (matrix @ query) / np.maximum(np.linalg.norm(matrix, axis=1) * np.linalg.norm(query), 1e-12)
                    for rank, index in enumerate(np.argsort(-similarity, kind="stable")[:100], 1):
                        scores[rows[index]["rowid"]] += 1 / (60 + rank)
            hits = []
            seen = set()
            for rowid, score in scores.most_common():
                row = dict(db.execute("SELECT id, section_id, title, heading, text, url, pages FROM chunks WHERE rowid=?", (rowid,)).fetchone())
                if row["section_id"] in seen:
                    continue
                seen.add(row["section_id"])
                row.update(score=round(score, 6), pages=json.loads(row["pages"]))
                hits.append(row)
                if len(hits) == limit:
                    break
        return hits
