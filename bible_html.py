import hashlib
import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path

BOOKS = dict(zip(
    "Gen Exo Lev Num Deu Jos Jdg Rut 1Sa 2Sa 1Ki 2Ki 1Ch 2Ch Ezr Neh Est Job Psa Prv Ecc SoS Isa Jer Lam Ezk Dan Hos Joe Amo Oba Jon Mic Nah Hab Zep Hag Zec Mal Mat Mrk Luk Joh Act Rom 1Co 2Co Gal Eph Phi Col 1Th 2Th 1Ti 2Ti Tit Phm Heb Jam 1Pe 2Pe 1Jo 2Jo 3Jo Jud Rev".split(),
    "Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|1 Samuel|2 Samuel|1 Kings|2 Kings|1 Chronicles|2 Chronicles|Ezra|Nehemiah|Esther|Job|Psalms|Proverbs|Ecclesiastes|Song of Songs|Isaiah|Jeremiah|Lamentations|Ezekiel|Daniel|Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|Zephaniah|Haggai|Zechariah|Malachi|Matthew|Mark|Luke|John|Acts|Romans|1 Corinthians|2 Corinthians|Galatians|Ephesians|Philippians|Colossians|1 Thessalonians|2 Thessalonians|1 Timothy|2 Timothy|Titus|Philemon|Hebrews|James|1 Peter|2 Peter|1 John|2 John|3 John|Jude|Revelation".split("|")))

class BibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"s", "script", "style", "head"}:
            self.hidden += 1
        if tag in {"br", "p", "q"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"s", "script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "q"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

def plain_text(html):
    parser = BibleText()
    parser.feed(html)
    return " ".join("".join(parser.parts).split())

def read_bible(root):
    # Jubilee exports keep verse text and numbered notes in separate files
    root = Path(root)
    rows, files = [], []
    for code, name in BOOKS.items():
        for suffix, kind in (("", "bible"), ("N", "notes")):
            path = root / (code + suffix + ".htm")
            if not path.exists():
                continue
            raw = path.read_bytes()
            try:
                html = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                html = raw.decode("cp1252")
            files.append({"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
            if kind == "bible":
                pattern = r'<b>(?:(?!</b>).)*?<a\b[^>]*\bname=["\']?v(\d+)_(\d+)[a-z]*["\']?[^>]*>.*?</b>'
                markers = list(re.finditer(pattern, html, re.I | re.S))
                entries = []
                for index, marker in enumerate(markers):
                    end = markers[index + 1].start() if index + 1 < len(markers) else len(html)
                    fragment = re.split(r'<div\b|<h[1-6]\b|</body>', html[marker.end():end], maxsplit=1, flags=re.I)[0]
                    entries.append((*marker.groups(), "", fragment))
            else:
                entries = []
                for anchors, fragment in re.findall(r'((?:<a\b[^>]*\bname=n[^>]*>\s*</a>\s*)+)<p\b[^>]*>(.*?)</p>', html, re.I | re.S):
                    names = re.findall(r'\bname=["\']?n(\d+)_(\d+)x(\d+)[a-z]*', anchors, re.I)
                    if names:
                        chapter, verse, number = names[0]
                        entries.append((chapter, verse, number, fragment))
            grouped = {}
            for chapter, verse, number, fragment in entries:
                parts = grouped.setdefault((chapter, verse, number), [])
                if fragment not in parts:
                    parts.append(fragment)
            entries = [(*key, " ".join(parts)) for key, parts in grouped.items()]
            if kind == "bible":
                expected = set(re.findall(r'\bname=["\']?v(\d+)_(\d+)', html, re.I))
                if expected != {(chapter, verse) for chapter, verse, _, _ in entries}:
                    raise ValueError("Verse extraction does not cover all anchors in " + str(path))
            seen = set()
            for chapter, verse, number, fragment in entries:
                key = (chapter, verse, number)
                if key in seen:
                    raise ValueError("Duplicate Bible reference in " + str(path))
                seen.add(key)
                reference = f"{name} {chapter}:{verse}"
                heading = reference + (" footnote " + number if number else "")
                text = plain_text(fragment).lstrip("- ")
                if not text:
                    raise ValueError("Empty Bible passage: " + heading)
                rows.append({"book_id": "recovery:" + code + ":" + kind,
                             "book_title": f"Recovery Version — {name} ({kind})",
                             "chapter_index": int(chapter), "section_index": verse + (":" + number if number else ""),
                             "section_label": heading, "text": text, "kind": kind,
                             "reference": reference, "note": number,
                             "local_source": str(path.resolve()), "anchor": f"n{chapter}_{verse}x{number}" if number else f"v{chapter}_{verse}"})
    if not rows:
        raise ValueError("No recognized Recovery Version verse/footnote HTML files")
    return rows, files

def main():
    parser = argparse.ArgumentParser(description="Convert your local Jubilee Bible HTML into private searchable rows.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error("Choose a new output path to preserve the previous export")
    rows, files = read_bible(args.source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    output.with_suffix(".sources.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    print(f"Converted {len(rows)} verse/footnote records from {len(files)} files. Keep the output private.")

if __name__ == "__main__":
    main()
