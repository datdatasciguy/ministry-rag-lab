import argparse
import html
from collections import Counter
from contextlib import closing
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from local_model import generate, request as model_request
from model_options import PROFILES, read_settings
from search import SearchIndex, related_topics
from catalog import author_scope

class Query(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: str = "lexical"
    book: str = ""
    author: str = "auto"
    collection: str = "all"
    answer: bool = False
    limit: int = Field(default=6, ge=1, le=100)
    answer_sources: int = Field(default=8, ge=1, le=40)
    answer_length: str = Field(default="medium", pattern="^(short|medium|detailed|custom)$")
    answer_words: int = Field(default=250, ge=50, le=1500)
    model: str = Field(default="", max_length=120)
    allow_extrapolation: bool = False
    max_answer_attempts: int = Field(default=3, ge=1, le=5)

def create_app(index_path, model, desktop=False):
    index = SearchIndex(index_path)
    app = FastAPI(title="Ministry Search RAG", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    web = Path(__file__).parent / "web"

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        expected = "http://" + request.headers.get("host", "")
        if request.method == "POST" and origin and origin != expected:
            return JSONResponse({"detail": "Use the local search page"}, status_code=403)
        return await call_next(request)

    @app.get("/")
    def home():
        return FileResponse(web / "index.html")

    @app.get("/app.js")
    def script():
        return FileResponse(web / "app.js", media_type="application/javascript")

    @app.get("/api/books")
    def books():
        return {"books": index.titles(), "chunks": index.manifest["chunks"],
                "hybrid": bool(index.manifest["embedding_model"]), "model": model,
                "verified_authors": len(index.authors), "collections": index.collections,
                "display_verse": index.manifest.get("display_verse"), "desktop": desktop}

    @app.post("/api/query")
    def query(body: Query):
        try:
            hits = index.search(body.question, body.mode, body.answer_sources if body.answer else body.limit, body.book, body.author, body.collection)
            scope = author_scope(body.question, body.author)
            counts = dict(Counter(hit["kind"] for hit in hits))
            related = related_topics(body.question)
            if body.answer and hits:
                selected_model = body.model or model
                retry_mode = "lexical" if body.mode == "hybrid" else (
                    "hybrid" if index.manifest["embedding_model"] else "lexical")
                retry_search = lambda: index.search(body.question, retry_mode, body.answer_sources,
                                                   body.book, body.author, body.collection)
                result = generate(body.question, hits, selected_model, body.answer_length,
                                  body.answer_words, body.allow_extrapolation,
                                  body.max_answer_attempts, retry_search)
                counts = dict(Counter(hit["kind"] for hit in result["sources"]))
                return {**result, "scope": scope, "collection": body.collection,
                        "answer_sources": len(result["sources"]), "source_counts": counts, "related_topics": related}
            return {"sources": hits, "answer": "No matching passages found in this scope." if not hits else "", "citations": [], "abstain": not hits, "scope": scope, "collection": body.collection, "source_counts": counts, "related_topics": related}
        except (ValueError, RuntimeError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/models")
    def models():
        try:
            installed = {row["name"] for row in model_request("/api/tags")["models"]
                         if not row.get("remote_host") and not row.get("remote_model") and "cloud" not in row["name"].casefold()}
            return {"default": model, "models": [{**profile, "installed": profile["model"] in installed} for profile in PROFILES]}
        except RuntimeError:
            return {"default": model, "models": [], "notice": "Start Ollama to choose installed answer models. Keyword search still works."}

    @app.get("/api/context/{chunk_id}")
    def context(chunk_id: str, words: int = 300):
        try:
            return index.context(chunk_id, words)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/reference/{section_id}")
    def reference(section_id: str):
        with closing(index.connect()) as db:
            if not db.execute("SELECT name FROM sqlite_master WHERE name='reference_passages'").fetchone():
                raise HTTPException(status_code=404, detail="No Bible references in this index")
            row = db.execute("SELECT reference, kind, text FROM reference_passages WHERE id=?", (section_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Reference not found")
        label, kind, text = map(html.escape, row)
        return HTMLResponse(f'<!doctype html><meta charset="utf-8"><title>{label}</title><main style="max-width:800px;margin:48px auto;padding:24px;font:18px/1.6 system-ui"><a href="/">Ministry Search RAG</a><h1>{label}</h1><p>{kind} · Recovery Version · © Living Stream Ministry</p><p style="white-space:pre-wrap">{text}</p></main>')

    return app

def main():
    # Arguments
    parser = argparse.ArgumentParser(description="Open a local book search interface.")
    parser.add_argument("--index")
    parser.add_argument("--model")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    settings = read_settings()
    index = args.index or settings.get("index", "data/books.sqlite")
    model = args.model or settings.get("model", "qwen2.5:7b")
    if not Path(index).is_file():
        parser.error("Build your collection index first; see docs/sharing.md")
    uvicorn.run(create_app(index, model), host="127.0.0.1", port=args.port, access_log=False)

if __name__ == "__main__":
    main()
