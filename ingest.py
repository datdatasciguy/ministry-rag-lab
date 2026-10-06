import hashlib
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def normalize(text):
    return re.sub(r"\s+", " ", text).strip()

def read_sources(roots):
    audit = Counter()
    files = []
    sections = {}
    conflicts = set()
    for root in roots:
        root = Path(root).resolve()
        if not root.exists():
            raise ValueError("Source does not exist: " + str(root))
        paths = [root] if root.is_file() else sorted(root.rglob("sections.jsonl"))
        if not paths and root.is_dir():
            paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in {".txt", ".md", ".html"}
                           and not any(part.startswith(".") or part == "debug" for part in p.relative_to(root).parts))
        for path in paths:
            if root.is_dir() and not path.resolve().is_relative_to(root):
                audit["outside_links_skipped"] += 1
                continue
            raw = path.read_bytes()
            files.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
            if path.suffix.lower() == ".jsonl":
                rows = []
                for line in raw.decode("utf-8-sig").splitlines():
                    if line.strip():
                        rows.append(json.loads(line))
            else:
                text = raw.decode("utf-8-sig")
                if path.suffix.lower() == ".html":
                    parser = TextHTML()
                    parser.feed(text)
                    text = " ".join(parser.parts)
                rows = [{"book_id": digest(str(path)), "book_title": path.stem, "text": text}]
            for row in rows:
                audit["source_rows"] += 1
                if row.get("status", "ok") != "ok":
                    audit["failed_rows_skipped"] += 1
                    continue
                text = normalize(row.get("text", ""))
                if not text:
                    audit["empty_rows_skipped"] += 1
                    continue
                book = str(row.get("book_id") or row.get("book_title") or path.stem)
                key = (book, str(row.get("chapter_index", "")), str(row.get("section_index", "")))
                if key in sections:
                    if sections[key]["text"] == text:
                        audit["identical_sections_removed"] += 1
                    else:
                        conflicts.add(key)
                    continue
                sections[key] = {
                    "section_id": digest(json.dumps(key)), "title": row.get("book_title") or path.stem,
                    "heading": " / ".join(str(row.get(k) or "") for k in ("chapter_label", "section_label")).strip(" /"),
                    "url": row.get("section_canonical_url") or row.get("section_page_url") or "",
                    "pages": [row.get("page_start"), row.get("page_end")], "text": text,
                }
    for key in conflicts:
        sections.pop(key, None)
    audit["conflicting_sections_excluded"] = len(conflicts)
    audit["accepted_sections"] = len(sections)
    return list(sections.values()), files, dict(audit)

def chunk_sections(sections, size=220, overlap=40):
    if size < 50 or not 0 <= overlap < size:
        raise ValueError("Chunk size must be at least 50 words; overlap must be smaller than size")
    chunks = []
    for section in sections:
        words = section["text"].split()
        for start in range(0, len(words), size - overlap):
            text = " ".join(words[start:start + size])
            chunks.append({**section, "id": digest(section["section_id"] + str(start) + text), "text": text})
            if start + size >= len(words):
                break
    return chunks
