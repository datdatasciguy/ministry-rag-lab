import hashlib
import re
from html.parser import HTMLParser
from zipfile import ZipFile

class PageHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.headings = []
        self.heading = None
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")
        if tag in {"h1", "h2", "h3"}:
            self.heading = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"h1", "h2", "h3"} and self.heading is not None:
            self.headings.append(" ".join("".join(self.heading).split()))
            self.heading = None

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.heading is not None:
                self.heading.append(data)

def read_archive(path):
    # Read one page representation; leave PDBs and other archive files untouched
    rows = []
    records = []
    pattern = re.compile(r"(?:^|/)books/clean_html/([^/]+)/page_(\d+)\.html$", re.I)
    title_key = lambda title: re.sub(r"[^a-z0-9]", "", title.casefold())
    page_titles = set()
    with ZipFile(path) as archive:
        for member in sorted(archive.namelist()):
            match = pattern.search(member)
            if not match:
                continue
            raw = archive.read(member)
            parser = PageHTML()
            parser.feed(raw.decode("utf-8-sig"))
            title, page = match.groups()
            page_titles.add(title_key(title))
            rows.append({"book_id": "archive:" + title.casefold(), "book_title": title,
                         "section_index": int(page), "section_label": " / ".join(parser.headings[:3]),
                         "page_start": int(page), "page_end": int(page), "text": " ".join(parser.parts)})
            records.append({"member": member, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        # A few collections have whole-book HTML without matching page exports
        for member in sorted(archive.namelist()):
            if not re.search(r"(?:^|/)books/html_books/[^/]+\.html$", member, re.I):
                continue
            stem = member.rsplit("/", 1)[-1][:-5]
            if title_key(stem) in page_titles:
                continue
            raw = archive.read(member)
            parser = PageHTML()
            parser.feed(raw.decode("utf-8-sig"))
            first_heading = parser.headings[0] if parser.headings else ""
            title = first_heading if first_heading and first_heading.upper() != "CONTENTS" else stem.replace("_", " ")
            rows.append({"book_id": "archive:" + title.casefold(), "book_title": title,
                         "section_index": 0, "section_label": "Whole-book HTML export",
                         "text": " ".join(parser.parts)})
            records.append({"member": member, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    if not rows:
        raise ValueError("Archive has no books/clean_html/<title>/page_NNN.html pages")
    return rows, records
