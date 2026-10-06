import json
import re
import sqlite3
import time
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ingest import read_sources, chunk_sections
from local_model import embed, model_digest

STOPWORDS = set("a an and are as at be by can do does for from how i in is it of on or that the this to was what when where which who why with you".split())

def retrieval_question(question):
    # An author's name in a question should not drown out the requested topic
    match = re.match(r"^(?:what|how)\s+(?:does|did|do)\s+.+?\s+(?:say|teach|write|explain)\s+(?:about|on)\s+(.+)", question.strip(), re.I)
    return match.group(1).strip(" ?.!") if match else question.strip()

def build_index(sources, output, embedding_model=None, progress=None, resume=False):
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
    if pending.exists() and not resume:
        raise ValueError("An unfinished build exists at " + str(pending))
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "files": files,
                "audit": audit, "chunks": len(chunks), "chunk_words": 220, "overlap_words": 40,
                "embedding_model": embedding_model, "embedding_digest": model_hash,
                "embedding_retries": 0, "complete": False}
    with closing(sqlite3.connect(pending)) as db, db:
        if db.execute("SELECT name FROM sqlite_master WHERE name='metadata'").fetchone():
            row = db.execute("SELECT value FROM metadata WHERE name='manifest'").fetchone()
            if not resume or not row:
                raise ValueError("This unfinished index has no resumable manifest; choose a new path")
            previous = json.loads(row[0])
            keys = ("files", "chunks", "chunk_words", "overlap_words", "embedding_model", "embedding_digest")
            if previous["complete"] or any(previous[key] != manifest[key] for key in keys):
                raise ValueError("Sources or model settings changed; choose a new index path")
            manifest = previous
        else:
            db.executescript("CREATE TABLE chunks (id TEXT PRIMARY KEY, section_id TEXT, title TEXT, heading TEXT, text TEXT, url TEXT, pages TEXT, vector BLOB);"
                         "CREATE VIRTUAL TABLE passages USING fts5(title, heading, text, content='chunks', content_rowid='rowid');"
                         "CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT);")
            db.execute("INSERT INTO metadata VALUES ('manifest', ?)", (json.dumps(manifest),))
            db.commit()
        completed = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
        if completed and db.execute("SELECT id FROM chunks ORDER BY rowid DESC LIMIT 1").fetchone()[0] != chunks[completed - 1]["id"]:
            raise ValueError("Unfinished index does not match the source ordering")
        for start in range(completed, len(chunks), 32):
            batch = chunks[start:start + 32]
            vectors = [None] * len(batch)
            if embedding_model:
                inputs = [row["title"] + "\n" + row["heading"] + "\n" + row["text"] for row in batch]
                for attempt in range(3):
                    try:
                        vectors = embed(inputs, embedding_model)
                        break
                    except RuntimeError:
                        if attempt == 2:
                            raise
                        manifest["embedding_retries"] += 1
                        time.sleep(0.5 * (attempt + 1))
            if len(vectors) != len(batch):
                raise ValueError("Embedding count does not match the batch")
            for row, vector in zip(batch, vectors):
                blob = None if vector is None else np.asarray(vector, dtype=np.float32).tobytes()
                db.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)", (row["id"], row["section_id"], row["title"], row["heading"], row["text"], row["url"], json.dumps(row["pages"]), blob))
            if (start + len(batch)) % 1024 == 0 or start + len(batch) == len(chunks):
                db.execute("UPDATE metadata SET value=? WHERE name='manifest'", (json.dumps(manifest),))
                db.commit()
            if progress:
                progress(min(start + len(batch), len(chunks)), len(chunks))
        db.execute("INSERT INTO passages(passages) VALUES ('rebuild')")
        manifest["complete"] = True
        db.execute("UPDATE metadata SET value=? WHERE name='manifest'", (json.dumps(manifest),))
    pending.rename(output)
    return {key: manifest[key] for key in ("audit", "chunks", "embedding_model", "complete")}

class SearchIndex:
    def __init__(self, path):
        self.path = Path(path).resolve()
        with closing(self.connect()) as db:
            self.manifest = json.loads(db.execute("SELECT value FROM metadata WHERE name='manifest'").fetchone()[0])
        if not self.manifest["complete"]:
            raise ValueError("Index is incomplete")
        self.vector_rows = []
        self.matrix = None
        if self.manifest["embedding_model"]:
            with closing(self.connect()) as db:
                self.vector_rows = db.execute("SELECT rowid, title, vector FROM chunks").fetchall()
            self.matrix = np.stack([np.frombuffer(row[2], dtype=np.float32) for row in self.vector_rows])
            self.matrix /= np.maximum(np.linalg.norm(self.matrix, axis=1, keepdims=True), 1e-12)
            self.vector_rows = [(row[0], row[1]) for row in self.vector_rows]

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
        focused = retrieval_question(question)
        terms = [word for word in re.findall(r"\w+", focused.casefold()) if word not in STOPWORDS]
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
                query = np.asarray(embed([focused], model, query=True)[0], dtype=np.float32)
                similarity = (self.matrix @ query) / max(np.linalg.norm(query), 1e-12)
                eligible = np.array([i for i, row in enumerate(self.vector_rows) if book.casefold() in row[1].casefold()], dtype=int)
                for rank, index in enumerate(eligible[np.argsort(-similarity[eligible], kind="stable")[:100]], 1):
                    scores[self.vector_rows[index][0]] += 1 / (60 + rank)
            hits = []
            seen = set()
            title_counts = Counter()
            for rowid, score in scores.most_common():
                row = dict(db.execute("SELECT id, section_id, title, heading, text, url, pages FROM chunks WHERE rowid=?", (rowid,)).fetchone())
                if row["section_id"] in seen:
                    continue
                if not book and limit >= 6 and title_counts[row["title"]] >= 2:
                    continue
                seen.add(row["section_id"])
                title_counts[row["title"]] += 1
                row.update(score=round(score, 6), pages=json.loads(row["pages"]))
                hits.append(row)
                if len(hits) == limit:
                    break
        return hits
