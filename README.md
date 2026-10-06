# Ministry RAG Lab

A local reading assistant for a book collection. Find passages first, then ask
a small local model to explain them with numbered sources. The books stay on
your computer; the public demo uses text written for this project.

## Try it

Python 3.11+ and [Ollama](https://ollama.com/) for model features.

```bash
python -m pip install -r requirements.txt
python rag.py build --source examples --index data/demo.sqlite
python rag.py search "How do citations help check an answer?" --index data/demo.sqlite
python app.py --index data/demo.sqlite
```

Open `http://127.0.0.1:8766`. Keyword search works without a model.

For semantic search and generated answers, download two local models:

```bash
ollama pull nomic-embed-text:v1.5
ollama pull qwen2.5:7b
python rag.py build --source examples --index data/demo-hybrid.sqlite --embedding-model nomic-embed-text:v1.5
python app.py --index data/demo-hybrid.sqlite
```

The interface combines word matching with vector similarity and shows the
passages behind an answer. You can filter to a book or just read the results.

## Use a collection

```bash
python rag.py build --source /path/to/export --index data/books.sqlite --embedding-model nomic-embed-text:v1.5
python rag.py ask "Your question" --index data/books.sqlite --mode hybrid
```

Repeat `--source` for several exports. The importer reads `sections.jsonl`
exports with text, book titles, chapter labels and source links. If none are
present, it can read text, Markdown and HTML files. It skips empty/failed rows,
removes identical sections, and excludes conflicting versions instead of picking
one quietly. HTML extraction is basic; scanned PDFs and Palm PDB books need a
separate conversion step.

Build to a new index filename each time. Indexes keep source checksums, chunk
settings, an audit and the embedding model digest. A model change requires a
new index. Private exports, indexes and model files belong in ignored folders;
check staged filenames before publishing.

## What it does

SQLite FTS5 provides keyword ranking. Nomic embeddings provide semantic ranking;
reciprocal rank fusion combines the ranked lists. Chunks retain book, section,
page and link information, so you can go back to the source. Inference uses
Ollama on this computer and rejects cloud model names.

Generated answers must cite supplied passages or abstain. The code checks citation
numbers, but that does not establish that every claim is supported. Please read
the sources. The [notebook](notebooks/retrieval_baseline.ipynb) and
`evaluate.py` check retrieval on eight original demo questions. These are small
diagnostics, not a quality score for a ministry collection. A reviewed question
set from the real collection is the next evaluation step.

This is retrieval and model integration work. It does not train a new LLM.
The code is MIT licensed. Book rights remain with their owners and book text is
not distributed here. The optional [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)
and [Nomic Embed](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) models have
their own Apache 2.0 licenses. Model weights are downloaded separately.
