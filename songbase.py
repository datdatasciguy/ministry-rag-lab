import argparse
import hashlib
import html
import json
import re
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np

from ingest import chunk_sections, digest
from local_model import embed, model_digest

API = 'https://songbase.life/api/v2/app_data'

def download(output, language='english'):
    path = Path(output)
    if path.exists():
        raise ValueError('Choose a new dump filename, or import the existing dump directly')
    url = API + ('?' + urlencode({'language': language}) if language != 'all' else '')
    with urlopen(Request(url, headers={'User-Agent': 'MinistrySearchRAG (local song search)', 'Accept': 'application/json'}), timeout=90) as response:
        if response.url.split('?')[0] != API:
            raise ValueError('Unexpected Songbase export redirect')
        raw = response.read(40_000_001)
    if len(raw) > 40_000_000:
        raise ValueError('Songbase dump exceeds the 40 MB import limit')
    data = json.loads(raw)
    sections, catalog, details = read_dump(data)
    if not sections:
        raise ValueError('No usable songs in this export')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path

def clean_lyrics(text):
    versions = []
    for version in re.split(r'^###.*$', text, flags=re.M):
        # Songbase stores chords inside words; remove them without inserting spaces.
        version = re.sub(r'\[[^\]\n]*\]', '', version)
        version = re.sub(r'^#.*$', '', version, flags=re.M)
        version = re.sub(r'<[^>]+>', '', version)
        version = html.unescape(version).replace('**', '').replace('*', '')
        version = '\n'.join(line.rstrip() for line in version.splitlines()).strip()
        if version and ' '.join(version.split()) not in [' '.join(v.split()) for v in versions]:
            versions.append(version)
    return '\n\n'.join(versions)

def read_dump(data):
    if not isinstance(data, dict) or not isinstance(data.get('songs'), list) or not isinstance(data.get('books'), list):
        raise ValueError('Expected a full Songbase app_data export with songs and books')
    if data.get('songCount') not in (None, len(data['songs'])):
        raise ValueError('Song count does not match the full export')
    if data.get('data_updated_between', ['1970'])[0][:4] != '1970':
        raise ValueError('Use a full export, not an incremental update')
    memberships = defaultdict(list)
    for book in data['books']:
        if not isinstance(book.get('songs'), dict) or not isinstance(book.get('name'), str):
            raise ValueError('Invalid Songbase songbook')
        # The export maps song ID to its number in the book, not the reverse.
        for song_id, number in book['songs'].items():
            memberships[str(song_id)].append((book['name'], str(number)))
    sections, catalog, details = [], [], {}
    seen = set()
    for song in data['songs']:
        if type(song.get('id')) is not int or song['id'] <= 0 or not all(isinstance(song.get(key), str) for key in ['title', 'lyrics', 'lang']):
            raise ValueError('Invalid Songbase song record')
        song_id = str(song['id'])
        if song_id in seen:
            raise ValueError('Duplicate Songbase song ID: ' + song_id)
        seen.add(song_id)
        lyrics = clean_lyrics(song['lyrics'])
        if not lyrics:
            continue
        title = 'Songbase / ' + song['title'].strip() + ' / ' + song_id
        labels = [name + ' #' + number for name, number in memberships[song_id]]
        heading = ' · '.join([song['title'].strip(), *labels, song['lang']])
        section_id = 'songbase-' + song_id
        url = 'https://songbase.life/' + song_id
        sections.append({'section_id': section_id, 'title': title, 'heading': heading,
                         'text': lyrics, 'url': url, 'pages': [None, None], 'kind': 'songs'})
        details[title] = {'song_id': song_id, 'language': song['lang'], 'songbooks': labels, 'url': url}
        catalog.extend((name, number, song_id, section_id, title) for name, number in memberships[song_id])
    return sections, catalog, details

def enrich(source, output, dump):
    source, output, dump = Path(source).resolve(), Path(output).resolve(), Path(dump).resolve()
    pending = output.with_suffix(output.suffix + '.building')
    if output.exists() or pending.exists():
        raise ValueError('Choose a new output index to preserve existing indexes')
    sections, catalog, details = read_dump(json.loads(dump.read_text(encoding='utf-8')))
    if not sections:
        raise ValueError('No usable songs')
    output.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        manifest = json.loads(original.execute("SELECT value FROM metadata WHERE name='manifest'").fetchone()[0])
        if not manifest['complete'] or manifest.get('songbase'):
            raise ValueError('Use a complete base index without an existing Songbase import')
        model = manifest['embedding_model']
        if model and model_digest(model) != manifest['embedding_digest']:
            raise ValueError('Embedding model changed; restore it before adding songs')
        stat = source.stat()
        fingerprint = hashlib.sha256(json.dumps([str(source), stat.st_size, stat.st_mtime_ns, manifest], sort_keys=True).encode()).hexdigest()
        with closing(sqlite3.connect(pending)) as db:
            original.backup(db)
    data = json.loads(dump.read_text(encoding='utf-8'))
    song_ids = {str(song['id']) for song in data['songs']}
    unavailable = [{'book': book['name'], 'song_id': song_id, 'number': str(number)}
                   for book in data['books'] for song_id, number in book['songs'].items()
                   if str(song_id) not in song_ids]
    chunks = chunk_sections(sections)
    with closing(sqlite3.connect(pending)) as db, db:
        db.execute('CREATE TABLE song_catalog(book TEXT, number TEXT, song_id TEXT, section_id TEXT, title TEXT)')
        db.execute('CREATE INDEX song_number ON song_catalog(number,book)')
        db.executemany('INSERT INTO song_catalog VALUES (?,?,?,?,?)', catalog)
        for section in sections:
            if section['title'] in manifest.get('collections', {}):
                raise ValueError('Song title collides with an existing collection')
            db.execute('INSERT INTO source_sections VALUES (?,?,?,?,?)', (section['section_id'], section['title'], section['heading'], 1, section['text']))
            manifest.setdefault('collections', {})[section['title']] = 'songs'
            manifest.setdefault('authors', {})[section['title']] = {'author': 'Songbase (catalog)', 'method': 'Catalog provenance; lyric authors not supplied by export'}
        for start in range(0, len(chunks), 32):
            batch = chunks[start:start + 32]
            vectors = embed([row['title'] + '\n' + row['heading'] + '\n' + row['text'] for row in batch], model) if model else [None] * len(batch)
            if len(vectors) != len(batch):
                raise ValueError('Embedding count does not match song batch')
            for row, vector in zip(batch, vectors):
                blob = np.asarray(vector, dtype=np.float32).tobytes() if vector is not None else None
                cursor = db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)', (row['id'], row['section_id'], row['title'], row['heading'], row['text'], row['url'], '[null,null]', blob))
                db.execute('INSERT INTO passages(rowid,title,heading,text) VALUES (?,?,?,?)', (cursor.lastrowid, row['title'], row['heading'], row['text']))
            if start % 1024 == 0:
                print(f'Embedded {min(start + len(batch),len(chunks))}/{len(chunks)} song passages', flush=True)
        manifest['songs'] = details
        manifest['songbase'] = {'api': API, 'dump_sha256': hashlib.sha256(dump.read_bytes()).hexdigest(),
                               'imported_at': datetime.now(timezone.utc).isoformat(), 'songs': len(sections), 'chunks': len(chunks), 'unavailable_songbook_entries': unavailable}
        # Adding new titles preserves the exact sources and scope of saved research jobs.
        manifest.setdefault('compatible_research_fingerprints', []).append(fingerprint)
        manifest['chunks'] = db.execute('SELECT count(*) FROM chunks').fetchone()[0]
        db.execute("UPDATE metadata SET value=? WHERE name='manifest'", (json.dumps(manifest),))
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Song index integrity check failed')
    pending.rename(output)
    return {'index': str(output), 'songs': len(sections), 'added_chunks': len(chunks), 'unavailable_songbook_entries': len(unavailable)}

def main():
    parser = argparse.ArgumentParser(description='Add a private Songbase dump to a new local search index.')
    parser.add_argument('--index', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--dump', default='data/songbase/english.json')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--language', default='english', help='Export language, or all')
    args = parser.parse_args()
    if args.download:
        download(args.dump, args.language)
    print(json.dumps(enrich(args.index, args.output, args.dump)))

if __name__ == '__main__':
    main()
