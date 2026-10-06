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
from catalog import author_scope, has_author
from bible_html import BOOKS

STOPWORDS = set("a an and are as at be by can do does for from how i in is it of on or that the this to was what when where which who why with you".split())

def retrieval_question(question):
    # An author's name in a question should not drown out the requested topic
    match = re.match(r"^(?:what|how)\s+(?:does|did|do)\s+.+?\s+(?:say|teach|write|explain)\s+(?:about|on)\s+(.+)", question.strip(), re.I)
    return match.group(1).strip(" ?.!") if match else question.strip()

def related_topics(question):
    # Related search topics are background, not a classification of the conduct.
    if re.search(r"\bmasturbat(?:ion|ing|e|es)\b", question, re.I):
        return ["sexual immorality", "fornication", "sexual purity", "self-control"]
    return []

def verse_reference(question):
    for code, name in BOOKS.items():
        match = re.search(r"(?<!\w)(?:" + re.escape(name) + "|" + re.escape(code) + r")\.?\s+(\d+):(\d+)\b", question, re.I)
        if match:
            return f"{name} {int(match[1])}:{int(match[2])}"
    return ""

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
                "embedding_retries": 0, "complete": False,
                "collections": {row["title"]: row.get("kind", "ministry") for row in sections}}
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
        db.execute("CREATE TABLE IF NOT EXISTS reference_passages (id TEXT PRIMARY KEY, reference TEXT, kind TEXT, text TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS source_sections (id TEXT PRIMARY KEY, title TEXT, heading TEXT, position INTEGER, text TEXT)")
        db.execute("CREATE INDEX IF NOT EXISTS source_order ON source_sections(title, position)")
        positions = Counter()
        for row in sections:
            positions[row["title"]] += 1
            db.execute("INSERT OR IGNORE INTO source_sections VALUES (?,?,?,?,?)", (row["section_id"], row["title"], row["heading"], positions[row["title"]], row["text"]))
            if row.get("kind") in {"bible", "notes"}:
                db.execute("INSERT OR IGNORE INTO reference_passages VALUES (?,?,?,?)", (row["section_id"], row["heading"], row["kind"], row["text"]))
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
        self.authors = self.manifest.get("authors", {})
        self.collections = self.manifest.get("collections", {})
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

    def result(self, row, score, terms, ranks):
        row.update(score=round(score, 6), pages=json.loads(row["pages"]),
                   author=self.authors.get(row["title"], {}).get("author", "Unverified"),
                   kind=self.collections.get(row["title"], "ministry"))
        searchable = " ".join(row[key] for key in ["title", "heading", "text"])
        row["matched_terms"] = [term for term in terms if re.search(r"\b" + re.escape(term) + r"\b", searchable, re.I)]
        row["retrieval_ranks"] = ranks
        if row["kind"] in {"bible", "notes"}:
            row["url"] = "/api/reference/" + row["section_id"]
        return row

    def context(self, chunk_id, words=300):
        if not 300 <= words <= 8100:
            raise ValueError("Choose 300 to 8,100 words of context on each side")
        with closing(self.connect()) as db:
            db.row_factory = sqlite3.Row
            chunk = db.execute("SELECT section_id, text FROM chunks WHERE id=?", (chunk_id,)).fetchone()
            if not chunk:
                raise ValueError("Passage not found")
            if not db.execute("SELECT name FROM sqlite_master WHERE name='source_sections'").fetchone():
                raise ValueError("Rebuild this older index to enable expanded context")
            section = db.execute("SELECT * FROM source_sections WHERE id=?", (chunk["section_id"],)).fetchone()
            if not section:
                raise ValueError("Source section unavailable")
            start = section["text"].find(chunk["text"])
            if start < 0:
                raise ValueError("Passage does not match its stored source")
            start = len(section["text"][:start].split())
            end = start + len(chunk["text"].split())
            text = section["text"].split()
            left, right = max(0, start - words), min(len(text), end + words)
            blocks = [{"heading": section["heading"], "text": " ".join(text[left:right])}]
            more = left > 0 or right < len(text)
            for before, remaining in [(True, words - (start - left)), (False, words - (right - end))]:
                operator, direction = ("<", "DESC") if before else (">", "ASC")
                rows = db.execute(f"SELECT heading, text FROM source_sections WHERE title=? AND position {operator} ? ORDER BY position {direction}", (section["title"], section["position"]))
                for row in rows:
                    if remaining <= 0:
                        more = True
                        break
                    neighbor = row["text"].split()
                    excerpt = neighbor[-remaining:] if before else neighbor[:remaining]
                    block = {"heading": row["heading"], "text": " ".join(excerpt)}
                    blocks.insert(0, block) if before else blocks.append(block)
                    remaining -= len(excerpt)
                    if len(excerpt) < len(neighbor):
                        more = True
            return {"title": section["title"], "sections": blocks, "more": more, "words_each_side": words}

    def search(self, question, mode="lexical", limit=5, book="", author="auto", collection="all"):
        if not question.strip() or len(question) > 2000 or not 1 <= limit <= 100:
            raise ValueError("Enter a question up to 2,000 characters and a limit from 1 to 100")
        if mode not in {"lexical", "hybrid"}:
            raise ValueError("Search mode must be lexical or hybrid")
        scope = author_scope(question, author)
        if scope not in {"all", "Witness Lee", "Watchman Nee"}:
            raise ValueError("Choose all authors, Witness Lee or Watchman Nee")
        if collection not in {"all", "ministry", "bible", "notes", "balanced"}:
            raise ValueError("Choose a supported collection")
        if collection == "balanced":
            if limit < 3:
                raise ValueError("Choose at least three passages for balanced sources")
            groups = {kind: self.search(question, mode, limit, book if kind == "ministry" else "",
                                       author if kind == "ministry" else "all", kind)
                      for kind in ["ministry", "bible", "notes"]}
            selected = []
            # Two ministry slots for each Bible + footnote pair
            order = ["ministry", "bible", "notes"] if limit == 3 else ["ministry", "bible", "ministry", "notes"]
            while len(selected) < limit and any(groups.values()):
                for kind in order:
                    if groups[kind]:
                        selected.append(groups[kind].pop(0))
                    if len(selected) == limit:
                        break
            return selected
        titles = [title for title in self.titles() if book.casefold() in title.casefold()
                  and (scope == "all" or has_author(self.authors.get(title, {}).get("author", ""), scope))
                  and (collection == "all" or self.collections.get(title, "ministry") == collection)]
        if not titles:
            return []
        eligible_titles = set(titles)
        focused = retrieval_question(question)
        topics = related_topics(question)
        if topics:
            focused += " " + " ".join(topics)
        reference = verse_reference(question)
        terms = [word for word in re.findall(r"\w+", focused.casefold()) if word not in STOPWORDS]
        scores = Counter()
        ranks = {}
        candidates = max(100, limit * 4)
        direct = []
        with closing(self.connect()) as db:
            db.row_factory = sqlite3.Row
            if reference:
                placeholders = ",".join("?" for title in titles)
                direct = db.execute("SELECT rowid FROM chunks WHERE title IN (" + placeholders + ") AND (heading=? OR heading LIKE ?) ORDER BY length(heading), rowid LIMIT ?", [*titles, reference, reference + " footnote %", candidates]).fetchall()
                for rank, row in enumerate(direct, 1):
                    scores[row[0]] += 1 / rank
                    ranks.setdefault(row[0], {})["reference"] = rank
            if terms:
                expression = " OR ".join('"' + word + '"' for word in dict.fromkeys(terms))
                placeholders = ",".join("?" for title in titles)
                lexical = db.execute("SELECT c.rowid FROM passages JOIN chunks c ON c.rowid=passages.rowid WHERE passages MATCH ? AND c.title IN (" + placeholders + ") ORDER BY bm25(passages, 2, 1.5, 1) LIMIT ?", [expression, *titles, candidates]).fetchall()
                for rank, row in enumerate(lexical, 1):
                    scores[row[0]] += 1 / (60 + rank)
                    ranks.setdefault(row[0], {})["words"] = rank
            if mode == "hybrid":
                model = self.manifest["embedding_model"]
                if not model:
                    raise ValueError("Build an index with an embedding model for hybrid search")
                if model_digest(model) != self.manifest["embedding_digest"]:
                    raise ValueError("Embedding model changed; rebuild the index")
                query = np.asarray(embed([focused], model, query=True)[0], dtype=np.float32)
                similarity = (self.matrix @ query) / max(np.linalg.norm(query), 1e-12)
                eligible = np.array([i for i, row in enumerate(self.vector_rows) if row[1] in eligible_titles], dtype=int)
                for rank, index in enumerate(eligible[np.argsort(-similarity[eligible], kind="stable")[:candidates]], 1):
                    scores[self.vector_rows[index][0]] += 1 / (60 + rank)
                    ranks.setdefault(self.vector_rows[index][0], {})["meaning"] = rank
            hits = []
            seen = set()
            title_counts = Counter()
            ranked = scores.most_common()
            # Prefer varied books, then fill the requested count from other sections
            deferred = []
            for rowid, score in ranked:
                if direct and rowid not in {row[0] for row in direct}:
                    continue
                row = dict(db.execute("SELECT id, section_id, title, heading, text, url, pages FROM chunks WHERE rowid=?", (rowid,)).fetchone())
                if row["section_id"] in seen:
                    continue
                if not book and not reference and limit >= 6 and title_counts[row["title"]] >= 2:
                    deferred.append((rowid, score))
                    continue
                seen.add(row["section_id"])
                title_counts[row["title"]] += 1
                hits.append(self.result(row, score, terms, ranks[rowid]))
                if len(hits) == limit:
                    break
            if len(hits) < limit and deferred:
                for rowid, score in deferred:
                    row = dict(db.execute("SELECT id, section_id, title, heading, text, url, pages FROM chunks WHERE rowid=?", (rowid,)).fetchone())
                    if row["section_id"] in seen:
                        continue
                    seen.add(row["section_id"])
                    hits.append(self.result(row, score, terms, ranks[rowid]))
                    if len(hits) == limit:
                        break
        return hits
