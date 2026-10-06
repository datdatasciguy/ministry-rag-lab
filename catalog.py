import re
import argparse
import hashlib
import json
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path
from collections import defaultdict
from html.parser import HTMLParser

def title_key(title):
    text = unicodedata.normalize("NFKC", title).casefold().replace("&", " and ")
    text = re.sub(r"[,\s]+(the|an|a)$", "", text)
    text = re.sub(r"^(the|an|a)\s+", "", text)
    text = re.sub(r"\b(first|second|third)\b", lambda match: {"first": "1", "second": "2", "third": "3"}[match[0]], text)
    return re.sub(r"[^a-z0-9]", "", text)

class CatalogHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag in {"td", "th"} and self.row is not None:
            self.cell = {"attrs": dict(attrs), "parts": []}

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["parts"].append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.cell["text"] = " ".join("".join(self.cell.pop("parts")).split())
            self.row.append(self.cell)
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

def read_catalog(html):
    parser = CatalogHTML()
    parser.feed(html)
    records = []
    for row in parser.rows:
        cells = {cell["attrs"].get("headers"): cell["text"] for cell in row}
        if cells.get("book-title"):
            records.append({"title": cells["book-title"], "author": cells.get("author", ""),
                            "volume": cells.get("year-vol", "")})
        elif len(row) == 2 and row[1]["text"] not in {"Author", ""}:
            records.append({"title": row[0]["text"], "author": row[1]["text"], "volume": ""})
    return records

def match_authors(titles, catalogs):
    # Prefer the archived edition's explicit attribution over a newer edition
    result = {}
    for records, source in catalogs:
        lookup = defaultdict(set)
        for row in records:
            if row["author"] and row["author"] != "Lee":
                lookup[title_key(row["title"])].add(row["author"])
        for title in titles:
            authors = lookup[title_key(title)]
            if title not in result and len(authors) == 1:
                result[title] = {"author": next(iter(authors)), "source": source}
    return result

def author_scope(question, selected="auto"):
    if selected != "auto":
        return selected
    subject = re.split(r"\b(?:about|on)\b", question, maxsplit=1, flags=re.I)[0]
    lee = bool(re.search(r"\b(?:witness|brother|bro\.)\s+lee\b", subject, re.I))
    nee = bool(re.search(r"\b(?:watchman|brother|bro\.)\s+nee\b", subject, re.I))
    return "all" if lee == nee else "Witness Lee" if lee else "Watchman Nee"

def has_author(label, author):
    return author.casefold() in re.split(r"\s*(?:/|\band\b|&)\s*", label.casefold())

def main():
    parser = argparse.ArgumentParser(description="Attach verified title/author catalog metadata to a new copy of an index.")
    parser.add_argument("--index", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source", action="append", required=True)
    args = parser.parse_args()
    source, output = Path(args.index).resolve(), Path(args.output).resolve()
    pending = output.with_suffix(output.suffix + ".building")
    if output.exists() or pending.exists():
        parser.error("Choose a new output path")
    catalogs, records = [], []
    for path in args.source:
        raw = Path(path).read_bytes()
        catalogs.append((read_catalog(raw.decode("utf-8-sig")), str(Path(path).resolve())))
        records.append({"path": str(Path(path).resolve()), "sha256": hashlib.sha256(raw).hexdigest()})
    output.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(pending)) as target, target:
            original.backup(target)
            manifest = json.loads(target.execute("SELECT value FROM metadata WHERE name='manifest'").fetchone()[0])
            if not manifest["complete"]:
                raise ValueError("Source index is incomplete")
            titles = [row[0] for row in target.execute("SELECT DISTINCT title FROM chunks")]
            manifest["authors"] = match_authors(titles, catalogs)
            manifest["author_sources"] = records
            target.execute("UPDATE metadata SET value=? WHERE name='manifest'", (json.dumps(manifest),))
    pending.rename(output)
    print(f"Verified author metadata for {len(manifest['authors'])} of {len(titles)} title labels.")

if __name__ == "__main__":
    main()
