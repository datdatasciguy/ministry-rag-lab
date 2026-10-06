import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from local_model import generate
from search import SearchIndex

class Query(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: str = "lexical"
    book: str = ""
    answer: bool = False

def create_app(index_path, model):
    index = SearchIndex(index_path)
    app = FastAPI(title="Local book search", docs_url=None, redoc_url=None)
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
                "hybrid": bool(index.manifest["embedding_model"]), "model": model}

    @app.post("/api/query")
    def query(body: Query):
        try:
            hits = index.search(body.question, body.mode, 4, body.book)
            if body.answer and hits:
                return generate(body.question, hits, model)
            return {"sources": hits, "answer": "No matching passages found." if not hits else "", "citations": [], "abstain": not hits}
        except (ValueError, RuntimeError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return app

def main():
    # Arguments
    parser = argparse.ArgumentParser(description="Open a local book search interface.")
    parser.add_argument("--index", required=True)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    uvicorn.run(create_app(args.index, args.model), host="127.0.0.1", port=args.port, access_log=False)

if __name__ == "__main__":
    main()
