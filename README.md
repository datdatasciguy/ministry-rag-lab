# Ministry Search RAG

A local reading assistant for a book collection. Find passages first, then ask
a small local model to explain them with numbered sources. The books stay on
your computer. This repository contains the application code and documentation;
you supply the collection.

## Desktop download

For setup without Python or terminal commands, use the
[desktop installer previews](https://github.com/datdatasciguy/ministry-rag-lab/releases).
Windows x64 and Mac Apple Silicon/Intel packages bundle the app runtime.
You still supply a private collection index and install the local model runtime.
See [desktop setup](docs/desktop_install.md) for the first-run steps and preview
limitations.

## Reading controls

Quick, Standard and Detailed presets set the answer length and source count to fit your selected model. Keep Collection visible to choose ministry, Bible, footnotes or balanced evidence. Open Advanced for book and author filters, model selection, search mode and exact limits. Changing a numeric limit marks the preset as Custom.

Answers render headings, lists, emphasis and inline passage citations. Click a reference such as [14] to jump to its numbered source card, then expand context for more surrounding text. Model text is rendered as text and safe formatting, never executable HTML.

Answers require direct support for the actual question. Related themes alone do not establish a spiritual meaning. When the retrieved passages lack that support, the model should say so and ask for clarification; this does not prove the whole corpus lacks an answer. Advanced includes an optional extrapolation switch, off by default. Any speculation appears in a separate labeled box with no direct-evidence citations or attribution to the ministry.

Validation checks citation bounds, quotation text, unsupported-answer citations and explicit admissions of missing direct support. These checks do not prove that every claim follows from its passage; model errors remain possible. The local check for the reported ambiguous term and a supported life question is a focused check, not a general accuracy benchmark.

If a draft admits missing direct evidence but still offers a cited answer, strict mode rejects it. With separate extrapolation enabled, you can inspect that draft in the warning box instead. Citation markers are removed, supporting citations are empty, and the retrieved source cards remain available for comparison. This does not validate the draft as ministry teaching.

Answers distinguish direct support, related background teachings and no useful evidence. Related teachings can have citations for their broader principles while acknowledging they do not establish the specific conclusion. Any application beyond those principles belongs in the separate opt-in extrapolation section. If the draft mixes them, the app tries one separation pass and otherwise shows the rejected draft only as unverified extrapolation.

Searches mentioning masturbation also retrieve the background topics sexual immorality, fornication, sexual purity and self-control. The UI reports these extra topics. This is a limited, explicit query expansion, not a declaration that the conduct belongs to any particular category. Existing collection, book and author filters still apply.

## Run from source

For questions that need a wider view, open **Deep research** below the search controls. It reads the selected collection in saved batches, collects verified excerpts, then combines small summaries into a final cited report. You can pause, resume and summarize the findings so far. Start with a short time or batch budget; a full collection run can take hours or days. See [how Deep research works](docs/deep_research.md).

Finding a wife, husband, mate or spouse searches related wording together, so a different term in a book does not hide a useful passage. These extra terms broaden retrieval; the answer still needs evidence.

Identity questions about Witness Lee, Watchman Nee, Living Stream Ministry and the local churches show short introductions and verified official or associated links. Questions about controversies defer to their own statements and the Defense and Confirmation Project, clearly labeled as their presentation. Teaching questions continue through the local RAG. The app does not generate biographies or decide allegations from a small passage sample.

General label questions such as **What is a cult?** also show an introduction to stated faith and church life, rather than making accusations the introduction. This tool does not classify religious groups from retrieved snippets.

[Reviewed website references](docs/website_sources.md) can be added to a new local index. Relevant LSM, DCP, A Faithful Word and localchurches.org pages receive a limited retrieval preference, with targeted introductions and FAQs prioritized for common questions. Website publisher labels distinguish these from individual authors' books. Downloaded text stays local.

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
