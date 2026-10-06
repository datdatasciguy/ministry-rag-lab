# Ministry Search RAG

A local reading assistant for a book collection. Find passages first, then ask
a small local model to explain them with numbered sources. The books stay on
your computer. This repository contains the application code and documentation;
you supply the collection.

## Try it

Python 3.11+ and [Ollama](https://ollama.com/) for model features.

```bash
python -m pip install -r requirements.txt
python rag.py build --source /path/to/your/book-export --index data/books.sqlite
python rag.py search "Your question" --index data/books.sqlite
python app.py --index data/books.sqlite
```

Open `http://127.0.0.1:8766`. Keyword search works without a model.

For semantic search and generated answers, run the first-run model picker:

```bash
python setup.py
python rag.py build --source /path/to/your/book-export --index data/books-hybrid.sqlite --embedding-model nomic-embed-text:v1.5
python app.py --index data/books-hybrid.sqlite
```

Setup describes eight options from a 271 MB mobile-scale model to a 20 GB
workstation model, with hardware suggestions and quality tradeoffs. It downloads
only the chosen answer model and embeddings. See [model choices](docs/models.md).
The Model control switches among installed options and adjusts answer budgets.

The interface combines word matching with vector similarity and shows the
passages behind an answer. You can filter to a book or just read the results.
Mixed results show Bible verses and footnotes on the left and ministry on the
right. Smaller screens stack the columns. Citation numbers stay the same across
both columns; supporting-citation links jump to the corresponding passage.
Each result has an **Expand context** control. It starts with 300 words on each
side, then lets you request 900, 2,700 and 8,100 words. It includes neighboring
sections from the same book when available. Changing a search scope clears the
old results; Bible verses and footnotes stay within their selected collections.
Set **Search results** from 1–100 for Find passages, and **Answer sources** from
1–40 for Answer, depending on the selected model. The model receives only those retrieved passages; it does not
read the entire corpus. The answer panel shows how many passages were supplied.
Larger requests can take longer and include weaker matches. For CLI questions,
use `--limit`, for example `python rag.py ask "Your question" --index data/books.sqlite --mode hybrid --limit 20`.
Choose **Short** (about 100 words), **Medium** (250), or **Detailed** (600).
The advanced option accepts a target from 50–1,500 words, within the model budget. Targets are approximate;
the answer panel shows the actual length. These controls are independent from
source count. In the CLI, use `--length detailed` or `--length custom --words 400`.
**Balanced** collection mode reserves about half the evidence for ministry books
and half for Bible verses plus footnotes. It includes both verses and notes when
available and alternates source types. Book/author filters apply to ministry;
Scripture and commentary stay labeled separately. The actual counts are shown.
The model is asked to give both groups comparable attention, while avoiding
irrelevant citations or forced agreement. Use `--collection balanced` in the CLI.
Source cards highlight query word matches and show their word/meaning ranks.
Expanded context marks the retrieved span in green. Semantic similarity ranks
the whole passage; word highlights are not a token-level explanation of that score.

“The ministry” searches the whole corpus. Questions naming Brother Lee or
Watchman Nee use verified author metadata, including jointly authored works.
Use the Author control to override that scope. Titles without verified metadata
remain searchable across the whole corpus and are excluded from author filters.

For more room to synthesize a broad topic, try the larger local model:

```bash
ollama pull qwen2.5:14b
python app.py --index data/books-hybrid.sqlite --model qwen2.5:14b
```

It needs more memory and is slower than 7B. Better source coverage and retrieval
still matter: a larger model cannot explain a book that was never indexed.

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

An archive with `books/clean_html/<title>/page_NNN.html` can be supplied directly
as `--source /path/to/books.zip`. The importer reads that page representation,
keeps export page numbers and member checksums, and ignores the archive's other
files. A `books/html_books/*.html` companion is used when a book has no page export.
Some older iSilo collections have both PDB books and matching HTML exports;
use their HTML companions. Direct decoding of iSilo PDB files is not implemented.

For a local Jubilee HTML Bible export, keep verses and numbered footnotes separate:

```bash
python bible_html.py --source /path/to/local/bible-html --output data/bible.jsonl
python rag.py build --source data/bible.jsonl --index data/bible.sqlite --embedding-model nomic-embed-text:v1.5
```

Repeat `--source` in the build command to include book exports as well. The
interface offers Bible verses and Bible footnotes as separate search scopes.
Exact references such as `John 6:63` prioritize that verse and its notes. Each
result links to the full local verse or footnote; commentary is labeled separately
from Bible text. The importer checks verse anchors and joins split verse parts.
It does not execute the export's scripts or copy its media and navigation pages.

To attach an explicit publisher title/author catalog you already have:

```bash
python catalog.py --index data/books.sqlite --source /path/to/title-author-catalog.html --output data/books-with-authors.sqlite
```

Catalogs are matched by normalized title, never by names mentioned in a passage.
Supply several catalogs in priority order with repeated `--source`. Ambiguous
author matches stay unverified. Metadata and its checksums stay in the private index.

Build to a new index filename each time. Indexes keep source checksums, chunk
settings, an audit and the embedding model digest. An embedding model change requires a
new index; changing the answer model does not. Private exports, indexes and model files belong in ignored folders;
check staged filenames before publishing.

Large builds checkpoint every 1,024 passages. If a build is interrupted, repeat
the same build command with `--resume`. It checks source checksums and model
settings before continuing; an unfinished index is never served as complete.

## What it does

SQLite FTS5 provides keyword ranking. Nomic embeddings provide semantic ranking;
reciprocal rank fusion combines the ranked lists. Chunks retain book, section,
page and link information, so you can go back to the source. Inference uses
Ollama on this computer and rejects cloud model names.

Questions such as "What does an author say about a topic?" search the topic,
so the author's name does not crowd out relevant teaching. Broad answers use
up to eight passages by default (within the model budget), preferring two per title when searching across books.
If that leaves too few results, other ranked sections fill the requested count.
You can increase that evidence count with the Answer sources control. Vectors
are normalized and cached in memory to avoid rereading the full index per query.
Allow roughly 3 KB of vector memory per passage with the default embedding model.

Generated answers must cite supplied passages or abstain. The code checks citation
numbers and quoted phrases against the supplied text. The prompt asks for close
source terminology and phrasing, with minimal connecting wording. These checks
do not establish that every claim is supported. Please read
the sources. Local development checks cover retrieval, filtering, quotations,
context expansion and generated answers. These are selected checks, not a
quality score for a ministry collection. A reviewed question
set from the real collection is the next evaluation step.

This is retrieval and model integration work. It does not train a new LLM.
See [how the models and RAG pipeline work](docs/model_and_retrieval.md) for the
training distinction, equations, retrieval settings, generation controls,
validation evidence, limitations, and an accurate experience description.
The code is MIT licensed. Book rights remain with their owners and book text is
not distributed here. The optional [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)
and [Nomic Embed](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) models have
their own Apache 2.0 licenses. Model weights are downloaded separately.
The optional [Qwen2.5-14B-Instruct](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct)
model also has its own Apache 2.0 license.

## Share the app code

```bash
python package_app.py --output outputs/ministry-search-rag-code.zip
```

This uses a fixed list of application code and documentation. It excludes your
books, Bible export, footnotes, indexes, models, query history, and private reports.
Recipients install the requirements and supply their own permitted collection
using the commands above. The app binds to this PC's loopback address. Preparing
a package does not send it anywhere or grant rights to redistribute book content.
See [friend setup](docs/sharing.md) for the complete installation and collection
requirements. Your localhost address is only accessible on your own computer.
