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

from local_model import generate, related_searches, plan_retrieval, request as model_request
from model_options import PROFILES, read_settings, model_profile
from search import SearchIndex, related_topics
from source_diversity import SourceDiversity
from song_meaning import SongMeaning, REVIEW_ERRORS, review_failure
from catalog import author_scope
from research import ResearchJobs
from official_sources import normalize_ministry_question
from question_policy import respectful_question, original_wording

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
    allow_unverified_response: bool = False
    expand_related_topics: bool = True
    answer_original: bool = False
    skip_wording_guidance: bool = False
    song_meaning: bool = True
    song_focus: str = Field(default="either", pattern="^(either|whole)$")
    song_candidates: int = Field(default=32, ge=8, le=60)
    source_diversity: bool = False
    diversity_threshold: float = Field(default=0.92, ge=0.85, le=0.99)
    diversity_checks: int = Field(default=12, ge=1, le=30)

class ResearchStart(Query):
    batch_words: int = Field(default=600, ge=100, le=1200)
    run_minutes: int = Field(default=10, ge=0, le=1440)
    max_batches: int = Field(default=0, ge=0, le=10000)
    research_mode: str = Field(default="full", pattern="^(full|optimized)$")
    candidate_limit: int = Field(default=40, ge=5, le=300)
    min_relevance: int = Field(default=1, ge=0, le=3)
    followup_rounds: int = Field(default=2, ge=0, le=3)

class ResearchRun(BaseModel):
    run_minutes: int = Field(default=10, ge=0, le=1440)
    max_batches: int = Field(default=0, ge=0, le=10000)

def create_app(index_path, model, desktop=False):
    index = SearchIndex(index_path)
    research = ResearchJobs(index)
    diversity = SourceDiversity(index)
    songs = SongMeaning(index)
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

    @app.get("/research.js")
    def research_script():
        return FileResponse(web / "research.js", media_type="application/javascript")

    @app.get("/api/books")
    def books():
        return {"books": index.titles(), "chunks": index.manifest["chunks"],
                "hybrid": bool(index.manifest["embedding_model"]), "model": model,
                "verified_authors": len(index.authors), "collections": index.collections,
                "display_verse": index.manifest.get("display_verse"), "desktop": desktop,
                "songbase": index.manifest.get("songbase")}

    @app.post("/api/query")
    def query(body: Query):
        try:
            question, original = original_wording(body.question, body.answer_original)
            corrected = normalize_ministry_question(question)
            correction = corrected if corrected.casefold() != question.casefold().replace("’", "'") else ""
            question = corrected
            body = body.model_copy(update={"question": question, "answer_original": original})
            guidance = None if body.skip_wording_guidance else respectful_question(body.question, body.answer_original)
            interpretation = ({"policy_notice": "Wording guidance skipped. Original question wording retained; evidence checks still apply."}
                              if body.skip_wording_guidance else {})
            if correction:
                interpretation["query_correction"] = correction
            search_question = body.question
            if guidance and guidance.get('query_rewrite'):
                interpretation = {key: guidance[key] for key in ['interpreted_question', 'policy_notice']}
                body = body.model_copy(update={'question': guidance['query_rewrite']})
                search_question = guidance['search_question']
            elif guidance:
                return {**guidance, "scope": author_scope(body.question, body.author),
                        "collection": body.collection, "answer_sources": 0, "source_counts": {}, "related_topics": []}
            scope = author_scope(body.question, body.author)
            selected_model = body.model or model
            preferred_topics = None
            planning_warning = ''
            if body.answer and body.collection != 'songs':
                try:
                    plan = plan_retrieval(body.question, selected_model)
                    search_question = plan['search_question']
                    preferred_topics = plan['topics']
                    if body.author == 'auto' and plan['intent'] in {'definition', 'overview'} and set(preferred_topics) & {'witness_lee', 'watchman_nee', 'publisher'}:
                        # A biography asks about a person, rather than only texts authored by them.
                        scope = 'all'
                    interpretation['retrieval_topics'] = preferred_topics
                except (ValueError, RuntimeError, KeyError):
                    planning_warning = 'Search planning could not complete; used the original question.'
            search_author = scope if body.author == 'auto' else body.author
            selection_reports = []
            song_reports = []
            song_notices = []
            def song_status(count):
                return {'song_matching': {**song_reports[-1], 'selected': count} if song_reports else None,
                        'song_matching_notice': song_notices[-1] if song_notices else ''}
            limit = min(body.answer_sources, model_profile(selected_model)['sources']) if body.answer and body.source_diversity else body.answer_sources if body.answer else body.limit
            pool_limit = min(100, max(limit * 3, limit + 8)) if body.answer and body.source_diversity else limit
            def select_sources(pool):
                if not body.answer or not body.source_diversity:
                    return pool
                selected, report = diversity.select(pool, limit, body.question, selected_model,
                    body.diversity_threshold, body.diversity_checks, body.collection == 'balanced')
                selection_reports.append(report)
                return selected
            def retrieve(mode):
                if body.collection == 'songs' and body.song_meaning:
                    try:
                        pool, report = songs.search(body.question, mode, pool_limit, body.book,
                            search_author, selected_model, body.song_candidates, body.song_focus)
                    except REVIEW_ERRORS as error:
                        song_reports.clear()
                        failure = review_failure('song matching', error)
                        song_notices.append('Song meaning review could not complete. ' + failure['cause'] +
                            ' These results use ordinary retrieval; their contextual fit has not been reviewed.')
                    else:
                        song_notices.clear()
                        song_reports.clear()
                        if report:
                            song_reports.append(report)
                            if report['omitted']:
                                song_notices.append(f"Meaning review completed for {report['reviewed']} of {report['candidates']} candidates; {report['omitted']} could not be reviewed and were omitted.")
                            elif not report['comparative'] and report['reviewed']:
                                song_notices.append('Songs were reviewed for contextual fit; the final comparison failed, so they are ordered by their reviewed fit scores.')
                        return select_sources(pool)
                pool = index.search(search_question, mode, pool_limit, body.book, search_author, body.collection, preferred_topics)
                return select_sources(pool)
            hits = retrieve(body.mode)
            counts = dict(Counter(hit["kind"] for hit in hits))
            related = related_topics(body.question)
            if body.answer:
                selected_model = body.model or model
                retry_mode = "lexical" if body.mode == "hybrid" else (
                    "hybrid" if index.manifest["embedding_model"] else "lexical")
                retry_search = lambda: retrieve(retry_mode)
                if hits:
                    result = generate(body.question, hits, selected_model, body.answer_length,
                                      body.answer_words, body.allow_extrapolation,
                                      body.max_answer_attempts, retry_search, body.allow_unverified_response)
                else:
                    result = {"sources": [], "answer": "No matching passages found in this scope.",
                              "citations": [], "abstain": True, "support_level": "none", "attempts": 0}
                used_attempts = result["attempts"]
                if body.expand_related_topics and result["abstain"] and used_attempts < body.max_answer_attempts:
                    try:
                        terms = related_searches(body.question, selected_model)
                        # Keep the author resolved from the original question during expansion.
                        pools = [index.search(term, body.mode, pool_limit, body.book,
                                              scope if body.author == "auto" else body.author, body.collection, preferred_topics)
                                 for term in terms]
                        expanded = []
                        seen = set()
                        for rank in range(pool_limit):
                            for pool in pools:
                                if rank < len(pool):
                                    hit = pool[rank]
                                    key = hit.get("section_id", hit["id"])
                                    if key not in seen and len(expanded) < pool_limit:
                                        seen.add(key)
                                        expanded.append(hit)
                        if expanded:
                            expanded = select_sources(expanded)
                        if expanded:
                            result = generate(body.question, expanded, selected_model, body.answer_length,
                                              body.answer_words, body.allow_extrapolation,
                                              body.max_answer_attempts - used_attempts, None,
                                              body.allow_unverified_response)
                            result["attempts"] += used_attempts
                            result["recovery_notice"] = f"Used {result['attempts']} answer attempts across the initial and related-topic searches."
                            result.setdefault("evidence_warnings", []).append("Related-topic search was used because the first sample did not address the question. These search hypotheses do not establish the ministry's position on the original topic.")
                        if terms:
                            related = list(dict.fromkeys([*related, *terms]))
                    except (ValueError, RuntimeError) as error:
                        result.setdefault("evidence_warnings", []).append("Related-topic search could not complete. The first response and its sources are shown.")
                if selection_reports:
                    result["source_diversity"] = {**selection_reports[-1], "selected": len(result["sources"])}
                if planning_warning:
                    result.setdefault("evidence_warnings", []).append(planning_warning)
                counts = dict(Counter(hit["kind"] for hit in result["sources"]))
                return {**result, **interpretation, **song_status(len(result["sources"])), "scope": scope, "collection": body.collection,
                        "answer_sources": len(result["sources"]), "source_counts": counts, "related_topics": related}
            return {"sources": hits, **interpretation, **song_status(len(hits)), "answer": "No matching passages found in this scope." if not hits else "", "citations": [], "abstain": not hits, "scope": scope, "collection": body.collection, "source_counts": counts, "related_topics": related}
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

    def research_call(action, *args, **kwargs):
        try:
            return action(*args, **kwargs)
        except (ValueError, RuntimeError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/research")
    def research_jobs():
        return {"jobs": research_call(research.jobs)}

    @app.post("/api/research")
    def start_research(body: ResearchStart):
        if not body.skip_wording_guidance and respectful_question(body.question, body.answer_original):
            raise HTTPException(status_code=400, detail="Use Answer from passages to clarify this question's wording before starting a corpus scan.")
        job = research_call(research.create, body.question, body.model or model, body.book,
                            body.author, body.collection, body.batch_words, body.research_mode,
                            body.candidate_limit, body.min_relevance, body.followup_rounds)
        return research_call(research.resume, job["id"], body.run_minutes, body.max_batches)

    @app.get("/api/research/{job_id}")
    def research_status(job_id: str):
        return research_call(research.status, job_id)

    @app.post("/api/research/{job_id}/pause")
    def pause_research(job_id: str):
        return research_call(research.pause, job_id)

    @app.post("/api/research/{job_id}/resume")
    def resume_research(job_id: str, body: ResearchRun):
        return research_call(research.resume, job_id, body.run_minutes, body.max_batches)

    @app.post("/api/research/{job_id}/report")
    def summarize_research(job_id: str, body: ResearchRun):
        return research_call(research.resume, job_id, body.run_minutes, body.max_batches, True)

    @app.get("/api/research/{job_id}/findings")
    def research_findings(job_id: str, offset: int = 0, limit: int = 50, node_id: int | None = None,
                          finding_id: int | None = None):
        return research_call(research.findings, job_id, offset, limit, node_id,
                             [finding_id] if finding_id is not None else None)

    @app.get("/api/research/{job_id}/selection")
    def research_selection(job_id: str, offset: int = 0, limit: int = 20):
        return research_call(research.selection, job_id, offset, limit)

    @app.get("/api/research/{job_id}/source/{finding_id}")
    def research_source(job_id: str, finding_id: int):
        source = research_call(research.section, job_id, finding_id)
        title, heading, author, text = (html.escape(source[key]) for key in ["title", "heading", "author", "text"])
        return HTMLResponse(f'<!doctype html><meta charset="utf-8"><title>{title}</title><main style="max-width:850px;margin:40px auto;padding:20px;font:18px/1.6 system-ui"><a href="/">Ministry Search RAG</a><h1>{title}</h1><h2>{heading}</h2><p>{author} · Original stored section</p><p style="white-space:pre-wrap">{text}</p></main>')

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
