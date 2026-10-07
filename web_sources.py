import argparse
import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse, urljoin
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.robotparser import RobotFileParser

import numpy as np

from ingest import chunk_sections, digest
from local_model import embed, model_digest
from official_sources import PAGES

AGENT = 'MinistrySearchRAG/0.1 (local study index)'
PUBLISHERS = {'www.lsm.org': 'Living Stream Ministry', 'www.livingstream.com': 'Living Stream Ministry',
              'localchurches.org': 'The local churches', 'contendingforthefaith.org': 'Defense and Confirmation Project',
              'afaithfulword.org': 'Defense and Confirmation Project', 'www.afaithfulword.org': 'Defense and Confirmation Project'}

class ApprovedRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        approved_url(target)
        return super().redirect_request(request, response, code, message, headers, target)

def approved_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in PUBLISHERS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Use an approved HTTPS ministry website: ' + url)
    return parsed

class ArticleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.parts, self.article, self.links = [], [], [], []
        self.title = ''

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        hidden = tag in {'script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript'}
        content = tag in {'main', 'article'} or any(name in attributes.get('class', '').split() for name in ['entry-content', 'page-content'])
        if tag not in {'br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'wbr'}:
            self.stack.append((tag, hidden, content))
        if tag in {'p', 'div', 'h1', 'h2', 'h3', 'li', 'blockquote', 'br'}:
            self.parts.append('\n')
            if any(item[2] for item in self.stack):
                self.article.append('\n')
        if tag == 'a' and attributes.get('href'):
            self.links.append(attributes['href'])

    def handle_endtag(self, tag):
        for position in range(len(self.stack) - 1, -1, -1):
            if self.stack[position][0] == tag:
                self.stack = self.stack[:position]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1][0] == 'title':
            self.title += data
        if not any(item[1] for item in self.stack):
            self.parts.append(data)
            if any(item[2] for item in self.stack):
                self.article.append(data)

    def text(self):
        return re.sub(r'\s+', ' ', ''.join(self.article or self.parts)).strip()

def collect(cache, urls, delay=2):
    if delay < 1:
        raise ValueError('Use at least one second between public page requests')
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    opener = build_opener(ApprovedRedirects())
    robots = {}
    pages = []
    for url in dict.fromkeys(urls):
        parsed = approved_url(url)
        saved = cache / (digest(url) + '.json')
        if saved.exists():
            pages.append(json.loads(saved.read_text(encoding='utf-8')))
            continue
        if parsed.hostname not in robots:
            rules = RobotFileParser()
            try:
                time.sleep(delay)
                with opener.open(Request('https://' + parsed.hostname + '/robots.txt', headers={'User-Agent': AGENT}), timeout=30) as response:
                    rules.parse(response.read(512000).decode('utf-8', errors='replace').splitlines())
            except HTTPError as error:
                if error.code != 404:
                    raise ValueError('Could not confirm robots policy; stopped for ' + parsed.hostname) from error
                rules.parse([])
            robots[parsed.hostname] = rules
        rules = robots[parsed.hostname]
        if not rules.can_fetch(AGENT, url):
            raise ValueError('Robots policy excludes this page: ' + url)
        time.sleep(max(delay, rules.crawl_delay(AGENT) or 0))
        with opener.open(Request(url, headers={'User-Agent': AGENT}), timeout=30) as response:
            final_url = response.url
            approved_url(final_url)
            if 'text/html' not in response.headers.get('Content-Type', ''):
                raise ValueError('Expected a public HTML article: ' + url)
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError('Page too large for this importer: ' + url)
            charset = response.headers.get_content_charset() or 'utf-8'
        article = ArticleHTML()
        article.feed(raw.decode(charset, errors='replace'))
        text = article.text()
        if len(text.split()) < 30:
            raise ValueError('No usable article text: ' + url)
        page = {'url': final_url, 'requested_url': url, 'title': article.title.strip() or final_url,
                'publisher': PUBLISHERS[urlparse(final_url).hostname], 'text': text,
                'fetched_at': datetime.now(timezone.utc).isoformat(), 'sha256': hashlib.sha256(raw).hexdigest(),
                'links': [urljoin(final_url, link) for link in article.links]}
        saved.write_text(json.dumps(page, ensure_ascii=False), encoding='utf-8')
        pages.append(page)
        print('Cached: ' + final_url, flush=True)
    return pages

def enrich(source, output, pages):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists() or output.with_suffix(output.suffix + '.building').exists():
        raise ValueError('Choose a new index filename to preserve prior indexes')
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(output.suffix + '.building')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        manifest = json.loads(original.execute("SELECT value FROM metadata WHERE name='manifest'").fetchone()[0])
        if not manifest['complete']:
            raise ValueError('The original index is incomplete')
        model = manifest['embedding_model']
        if model and model_digest(model) != manifest['embedding_digest']:
            raise ValueError('Embedding model changed; restore it before adding pages')
        with closing(sqlite3.connect(pending)) as db:
            original.backup(db)
    added = 0
    with closing(sqlite3.connect(pending)) as db, db:
        website_pages = manifest.setdefault('website_pages', {})
        for page in pages:
            title = page['publisher'] + ' website / ' + page['title']
            if urlparse(page['url']).query:
                title += ' / ' + urlparse(page['url']).query
            section_id = 'web-' + digest(page['url'])
            if db.execute('SELECT 1 FROM source_sections WHERE id=?', (section_id,)).fetchone():
                continue
            section = {'section_id': section_id, 'title': title, 'heading': page['title'],
                       'text': page['text'], 'url': page['url'], 'pages': [None, None], 'kind': 'ministry'}
            db.execute('INSERT INTO source_sections VALUES (?,?,?,?,?)', (section_id, title, page['title'], 1, page['text']))
            chunks = chunk_sections([section])
            for start in range(0, len(chunks), 32):
                batch = chunks[start:start + 32]
                vectors = embed([row['text'] for row in batch], model) if model else [None] * len(batch)
                if len(vectors) != len(batch):
                    raise ValueError('Embedding count did not match website chunks')
                for row, vector in zip(batch, vectors):
                    blob = np.asarray(vector, dtype=np.float32).tobytes() if vector is not None else None
                    cursor = db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)', (row['id'], section_id, title, page['title'], row['text'], page['url'], '[null,null]', blob))
                    db.execute('INSERT INTO passages(rowid,title,heading,text) VALUES (?,?,?,?)', (cursor.lastrowid, title, page['title'], row['text']))
                    added += 1
            manifest.setdefault('collections', {})[title] = 'ministry'
            manifest.setdefault('authors', {})[title] = {'author': page['publisher'] + ' (website)', 'method': 'publisher provenance; not individual book authorship'}
            website_pages[title] = {key: page[key] for key in ['url', 'publisher', 'fetched_at', 'sha256']}
        manifest['chunks'] = db.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
        manifest['website_updated_at'] = datetime.now(timezone.utc).isoformat()
        db.execute("UPDATE metadata SET value=? WHERE name='manifest'", (json.dumps(manifest),))
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Website index integrity check failed')
    pending.rename(output)
    return {'index': str(output), 'pages': len(manifest['website_pages']), 'added_chunks': added, 'chunks': manifest['chunks']}

def main():
    parser = argparse.ArgumentParser(description='Cache reviewed public ministry pages locally and add them to a new index.')
    parser.add_argument('--index', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--cache', default='data/website-cache')
    parser.add_argument('--url', action='append', help='Approved public page URL; default is the reviewed introductory seed set')
    parser.add_argument('--delay', type=float, default=2)
    args = parser.parse_args()
    urls = args.url or [*[page[1] for page in PAGES.values()], 'https://afaithfulword.org/']
    pages = collect(args.cache, urls, args.delay)
    print(json.dumps(enrich(args.index, args.output, pages)))

if __name__ == '__main__':
    main()
