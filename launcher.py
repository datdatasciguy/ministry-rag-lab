import argparse
import json
import logging
import os
import secrets
import shutil
import socket
import sqlite3
import sys
import threading
import time
import uuid
import webbrowser
from contextlib import closing
from pathlib import Path
import platform
from urllib.request import ProxyHandler, Request, build_opener

import uvicorn
from fastapi import FastAPI, HTTPException, Request as WebRequest
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import create_app
from local_model import model_digest
from model_options import PROFILES, read_settings

def check_index(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Choose a complete SQLite collection index.')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        manifest = json.loads(db.execute("SELECT value FROM metadata WHERE name='manifest'").fetchone()[0])
        if not manifest.get('complete'):
            raise ValueError('This collection index is unfinished.')
        db.execute('SELECT id, title, heading, text, vector FROM chunks LIMIT 1').fetchone()
    if manifest.get('embedding_model') not in (None, 'nomic-embed-text:v1.5'):
        raise ValueError('This installer supports keyword indexes or Nomic v1.5 indexes.')
    return manifest

def pull_model(model, progress):
    body = json.dumps({'model': model, 'stream': True}).encode('utf-8')
    request = Request('http://127.0.0.1:11434/api/pull', data=body, headers={'Content-Type': 'application/json'})
    with build_opener(ProxyHandler({})).open(request, timeout=180) as response:
        for line in response:
            row = json.loads(line)
            if row.get('error'):
                raise ValueError(row['error'])
            percent = int(100 * row.get('completed', 0) / row['total']) if row.get('total') else None
            progress(model + ': ' + row.get('status', '') + (f' ({percent}%)' if percent is not None else ''))

class SearchGateway:
    def __init__(self, state):
        self.state = state

    async def __call__(self, scope, receive, send):
        if self.state.get('app'):
            await self.state['app'](scope, receive, send)
        else:
            await RedirectResponse('/setup')(scope, receive, send)

class Selection(BaseModel):
    model: str

def setup_app(data_dir, initial_index=None):
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    settings_path = data_dir / 'settings.json'
    saved = read_settings(settings_path)
    state = {'index': initial_index or saved.get('index', ''), 'model': saved.get('model', 'qwen3:1.7b'),
             'busy': False, 'message': 'Choose your collection and model.', 'ready': False, 'app': None}
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()
    app = FastAPI(docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
    app.state.setup_state = state

    @app.middleware('http')
    async def local_changes(request: WebRequest, call_next):
        if request.method == 'POST' and request.url.path.startswith('/setup/'):
            origin = request.headers.get('origin')
            if request.headers.get('x-setup-token') != token or (origin and origin != 'http://' + request.headers.get('host', '')):
                return HTMLResponse('Use the local setup page.', status_code=403)
        return await call_next(request)

    @app.get('/setup')
    def page():
        source = (Path(__file__).parent / 'web/setup.html').read_text(encoding='utf-8')
        return HTMLResponse(source.replace('__SETUP_TOKEN__', token))

    @app.get('/setup/status')
    def status():
        return {'index': Path(state['index']).name if state['index'] else '', 'model': state['model'],
                'busy': state['busy'], 'message': state['message'], 'ready': state['ready'], 'models': PROFILES, 'platform': platform.system()}

    @app.post('/setup/index')
    async def import_index(request: WebRequest):
        with lock:
            if state['busy'] or state['ready']:
                raise HTTPException(409, 'Restart the app before changing collections.')
            state['busy'] = True
        path = data_dir / ('collection-' + uuid.uuid4().hex + '.sqlite')
        pending = path.with_suffix('.partial')
        try:
            length = int(request.headers.get('content-length', '0'))
            free = shutil.disk_usage(data_dir).free
            if length <= 0 or length > 12 * 1024**3 or length + 512 * 1024**2 > free:
                raise ValueError('Choose an index under 12 GB and leave at least 512 MB free after copying it.')
            size = 0
            with pending.open('xb') as output:
                async for block in request.stream():
                    size += len(block)
                    if size > length:
                        raise ValueError('The upload exceeded its declared size.')
                    output.write(block)
            if size != length:
                raise ValueError('The index transfer did not finish. Try again.')
            manifest = check_index(pending)
            pending.replace(path)
            state.update(index=str(path), message=f"Collection ready: {manifest['chunks']:,} passages.")
            return {'message': state['message']}
        except (ValueError, sqlite3.Error, OSError, TypeError, KeyError) as error:
            pending.unlink(missing_ok=True)
            raise HTTPException(400, str(error)) from error
        finally:
            state['busy'] = False

    def prepare(model):
        try:
            manifest = check_index(state['index'])
            def progress(message):
                state['message'] = message
            models = [model]
            if manifest.get('embedding_model'):
                models.insert(0, manifest['embedding_model'])
            for name in models:
                try:
                    model_digest(name)
                except ValueError:
                    pull_model(name, progress)
            if manifest.get('embedding_model') and model_digest(manifest['embedding_model']) != manifest['embedding_digest']:
                raise ValueError('The downloaded embedding version differs from this index. Ask for a matching index or rebuild it.')
            progress('Opening the collection. A large index can take a moment.')
            search = create_app(state['index'], model, desktop=True)
            saved.update(index=state['index'], model=model)
            pending = settings_path.with_suffix('.json.tmp')
            pending.write_text(json.dumps(saved, indent=2) + '\n', encoding='utf-8')
            pending.replace(settings_path)
            state.update(app=search, model=model, ready=True, message='Ready. Open search.')
        except Exception as error:
            logging.exception('Setup failed')
            state['message'] = 'Setup failed: ' + str(error) + ' Start Ollama and retry if it is unavailable.'
        finally:
            state['busy'] = False

    @app.post('/setup/start')
    def start(body: Selection):
        if body.model not in {profile['model'] for profile in PROFILES}:
            raise HTTPException(400, 'Choose a listed local model.')
        with lock:
            if state['busy'] or state['ready']:
                raise HTTPException(409, 'Setup is already running or ready.')
            if not state['index']:
                raise HTTPException(400, 'Choose the private collection index first.')
            state.update(busy=True, message='Checking local models…')
        threading.Thread(target=prepare, args=(body.model,), daemon=True).start()
        return {'message': state['message']}

    @app.post('/setup/quit')
    def quit_app():
        if state['busy']:
            raise HTTPException(409, 'Wait for setup to finish before quitting.')
        if hasattr(app.state, 'shutdown'):
            app.state.shutdown()
        return {'message': 'App closed. Reopen it from the Start menu or Applications.'}

    app.mount('/', SearchGateway(state))
    return app

def main():
    parser = argparse.ArgumentParser(description='Start the installed Ministry Search RAG app.')
    default_data = Path.home() / 'Library/Application Support/MinistrySearchRAG' if sys.platform == 'darwin' else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'MinistrySearchRAG'
    parser.add_argument('--data-dir', default=str(default_data))
    parser.add_argument('--index')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    # Windowed bundles have no console streams
    log = (data_dir / 'launcher.log').open('a', encoding='utf-8', buffering=1)
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
    logging.basicConfig(filename=data_dir / 'launcher.log', level=logging.INFO)
    sock = socket.socket()
    try:
        sock.bind(('127.0.0.1', args.port))
    except OSError:
        sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    application = setup_app(data_dir, args.index)
    server = uvicorn.Server(uvicorn.Config(application, host='127.0.0.1', port=port,
                                           access_log=False, log_config=None))
    application.state.shutdown = lambda: setattr(server, 'should_exit', True)
    if not args.no_browser:
        def open_page():
            while not server.started and not server.should_exit:
                time.sleep(.1)
            if server.started:
                webbrowser.open(f'http://127.0.0.1:{port}/setup')
        threading.Thread(target=open_page, daemon=True).start()
    server.run(sockets=[sock])

if __name__ == '__main__':
    main()
