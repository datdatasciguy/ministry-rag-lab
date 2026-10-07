# How the models and RAG pipeline work

This project builds a local retrieval-augmented generation application. It
integrates pretrained models, prepares a private searchable corpus, retrieves
evidence, and generates cited answers. No language-model or embedding-model
weights have been trained or fine-tuned in this repository.

## What was trained, and by whom?

| Component | Role | Training status in this project |
| --- | --- | --- |
| Qwen2.5 / Qwen3 / SmolLM2 Instruct | Generate an answer from retrieved passages | Pretrained and instruction-tuned by its provider; used for local inference |
| Nomic Embed Text v1.5 | Encode passages and queries into vectors | Trained by its provider; used unchanged |
| SQLite FTS5 | Find lexical matches | Builds an inverted index; no neural training |
| Hybrid retrieval and prompts | Select evidence and constrain answers | Implemented and checked here; no learned ranking parameters |

The developer currently uses `qwen2.5:14b`. First-run setup lets each user
choose a model that fits their hardware; the CLI and app honor that choice. The 14B model card describes a
causal Transformer with pretraining and post-training, grouped-query attention,
RoPE positional embeddings, RMSNorm, and SwiGLU. Grouped-query attention shares
key/value heads among query heads, reducing the KV cache cost. These are model
provider choices, not architectures developed in this project.
[Qwen model card](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct)

In causal language-model training, the general objective is to predict the next
token given previous tokens: minimize the negative log probability of the
observed sequence. Fine-tuning would require a training dataset, an objective,
backpropagation, optimizer steps, checkpoints, and held-out evaluation. None of
those weight-update steps happen when this app builds an index or answers a
question. Inference and prompting do not train the model.

Nomic describes a long-context BERT-based embedder trained through contrastive
learning on related text pairs, followed by higher-quality labeled retrieval
data and hard-example mining. Conceptually, contrastive training pulls useful
query/document pairs together and pushes mismatched pairs apart. Version 1.5
uses Matryoshka representation learning to support shorter vector dimensions.
This implementation uses the full default vectors; it does not retrain the
encoder or truncate the representation.
[Nomic model card](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)

## Preparing the corpus

The importer accepts local section exports, readable HTML/text, and an archive's
explicit book-page representation. It preserves title, section, source link,
page metadata, source checksums, and import counts. Identical logical sections
are removed; conflicting versions of the same section are excluded for review.
An archive's scripts, configuration, and unrelated files are not imported.

The Bible adapter parses verse anchors and numbered footnotes separately. It
joins split verse parts, checks that every verse anchor was covered, and retains
verse/note labels. Footnotes are commentary, not Bible text. Original HTML is
read as data; its JavaScript is never executed. Verse and footnote results can
open a safely escaped local source view.

Chunks contain up to **220 whitespace-separated words**, with **40 words of
overlap**, inside a section. Overlap reduces boundary losses, but also repeats
some evidence. This is a word budget, not a tokenizer-exact budget. Title and
heading are included in the embedding input to provide context. A future
token-aware chunker would need a measured comparison before replacing it.

## Building the semantic index

Documents use the `search_document:` prefix and queries use `search_query:`.
These task prefixes follow the encoder's documented usage. Embeddings are
stored as float32 blobs alongside passages in SQLite. The build records the
installed model digest; queries reject a changed embedding model because vectors
from different encoders are not necessarily comparable.

Batches contain 32 passages. Large builds checkpoint every 1,024 passages and
can resume only when source hashes, chunk settings, ordering, and model digest
still match. An incomplete build remains in a separate file and is never served
as complete. HTTP failures have bounded retries. This is operational recovery,
not evidence that a particular failure was caused by input length.

At load time, document vectors are normalized and cached. Query ranking uses
cosine similarity:

```text
similarity(q, d) = dot(q, d) / (norm(q) * norm(d))
```

Search is an exact NumPy matrix scan, not an approximate nearest-neighbor index.
At 768 float32 dimensions, raw vectors use about 3 KB per passage before other
overhead. Startup caching trades memory for lower repeated-query latency.

## Hybrid ranking and scope

Lexical retrieval uses SQLite FTS5's BM25 with column weights **2 for title,
1.5 for heading, and 1 for text**. Semantic retrieval captures related wording
that exact terms can miss. By default the top 100 candidates per method are combined
by reciprocal rank fusion:

```text
RRF(d) = sum(1 / (60 + rank_in_each_result_list(d)))
```

Fusion uses rank positions because BM25 and cosine scores have different scales.
Neither score is a probability that an answer is correct.
[SQLite FTS5](https://www.sqlite.org/fts5.html),
[original RRF paper](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf)

Book, collection, and verified-author filters apply before candidate selection
in both retrieval paths. Names mentioned inside a passage do not establish its
author. Title/author catalog matches normalize spelling and article position;
ambiguous attribution stays unverified. Joint authorship can match either author.
“The ministry” means the whole corpus; explicit UI filters can narrow it.

Conversational questions keep their original wording for generation but remove
the leading author/question wrapper for topic retrieval. Exact Bible references
receive a separate retrieval priority. Answers normally use eight passages,
with one chunk per section and a preference for two per title across broad topic
searches. If that leaves too few results, other ranked sections fill the count.
Reference lookups can retain several notes from the same title. There is no
cross-encoder reranker or trained query classifier in this version.

## Grounded generation

Ollama runs on a fixed loopback endpoint. The adapter checks installed model
metadata and rejects cloud models. Passages are numbered and supplied as quoted
evidence, together with author and source-kind metadata. The prompt asks for a
short synthesis supported by these passages, or an abstention when evidence is
missing. It distinguishes footnote commentary from Scripture.
Answers are instructed to preserve the retrieved passages' terminology and
distinctions, use short cited quotations where useful, and keep connecting prose
close to the evidence. Quoted phrases must occur in supplied source text
or labels after normalizing case, whitespace, and apostrophes. A mismatch is
rejected. This favors source-faithful wording over creative paraphrases; it is
prompting and string validation, not style fine-tuning. Quote presence alone
does not establish that the associated citation or interpretation is correct.

Generation requests use temperature 0. The output token cap is `max(1024, 4 * target_words + 512)`,
allowing space for JSON and citations. Length presets request 100, 250 or 600 words;
the custom target supports 50–1,500. Word counts are approximate and the interface
shows the actual count; source support takes priority over padding an answer.
Short supported drafts are accepted without a length-expansion pass. Detail targets request substantive distinctions rather than repeated summaries.
The context setting starts at 8,192 tokens for up to eight passages and targets
up to 600 words, or 32,768 for larger requests, then is capped by the selected
model profile. Small profiles use 4,096 or 8,192; larger profiles allow 16,384
or 32,768. Source and word budgets are also checked before inference. See
[model choices](models.md) for the per-model settings.
Those are this application's settings, not the model's
advertised maximum context. A JSON schema constrains the answer, citation array,
and abstention flag. Page markers are removed from prompt text to reduce their
confusion with passage IDs. Returned citation IDs and inline citations are checked
against the supplied passages.

Valid citation numbers prove that an ID exists. They do **not** prove entailment,
complete coverage, or a hallucination-free answer. Temperature 0 also does not
guarantee identical outputs across runtimes or correctness. Retrieved text is
treated as evidence rather than instructions, but that prompt alone is not a
complete prompt-injection defense.

## Reading more context

The private index also stores complete normalized source sections. Each passage
can expand to 300 words before and after it, then 900, 2,700 and 8,100 on request.
Context stays in the same book and includes neighboring sections when available.
This reading window is separate from the passages supplied to the model;
expanding it does not silently regenerate an answer or broaden a source filter.
Source HTML is never executed, and the browser renders text through `textContent`.
Source cards highlight query words that occur in their title, heading or text,
and expose each passage's lexical, semantic and exact-reference ranks when present.
The expanded reading window highlights the retrieved span. These are match/rank
signals, not token-level causal explanations of a dense embedding score.

Search result count is configurable from 1 to 100; answer evidence count is
configurable from 1 to 40, with eight as the default. A generated answer uses the
returned evidence set, not every matching passage in the corpus. Retrieval takes
up to `max(100, 4 * requested_count)` candidates per ranked list before fusion
and diversity selection. Source filters apply before candidate selection. More
evidence increases prompt cost and can include less relevant matches; it does not
guarantee better answers. Citation cards show the actual supplied set and the
context setting so this boundary is visible.

Balanced collection mode uses source quotas rather than pretending raw BM25 or
vector scores from different collections are directly comparable: roughly half
the selected passages are ministry and half are Bible verses plus footnotes,
split between those two types. Each collection is ranked separately, then passages
are interleaved. Book/author filters apply to ministry, so a Witness Lee question
can still receive Bible evidence. When a collection lacks candidates, other
available sources fill the slots; actual counts are displayed. The prompt asks
for comparable attention and citations to both groups where relevant. Quotas
control evidence representation, not factual support or exact prose proportions.

## What the checks establish

Development checks used eight original diagnostic passages and questions, plus
format fixtures for author routing, split verses, footnotes and exact references.
Those diagnostic scripts, fixtures and notebooks are now kept privately; the
public repository contains runtime code and documentation. Hit@k measures
whether a labeled title appears, and mean reciprocal rank measures the position
of the first relevant title. These diagnostics are not independent corpus-wide
retrieval or answer-accuracy benchmarks.

Real-collection checks remain private. They verify selected queries, author
exclusion, book filters, source references, semantic-mode availability, citation
handling, and an unsupported-question case. Improving the broad life question
involved better retrieval and corpus coverage as well as a larger local model;
the observed improvement cannot be attributed to model size alone.

Next evaluation should label relevant passages for real queries, compare lexical
and hybrid retrieval on the same held-out set, measure latency, and review answer
support and abstentions separately. Actual fine-tuning would be a separate
experiment on appropriately licensed data, with a baseline and explicit training
configuration. Books, indexes, query logs, and model weights stay outside GitHub.

## A precise experience statement

“Built a local RAG application with BM25 and dense retrieval, metadata-based
author filtering, reference-aware Bible/footnote search, resumable corpus indexing,
and source-cited generation using pretrained models. Implemented retrieval
diagnostics and local inference without publishing the private corpus.”

## Automatic answer recovery

Answer validation failures trigger bounded recovery: first a corrected draft, then alternate lexical or hybrid retrieval within the same collection, author, book and source-count filters. Advanced settings allow 1-5 total generation attempts, defaulting to three. Citation numbering is rebuilt when passages change. A valid abstention is accepted immediately; retries do not manufacture evidence. If all attempts fail, sources remain readable and an unverified draft is shown only when separate extrapolation is enabled, with citation markers removed. Model connection failures are reported directly. Extra attempts add latency; they do not establish semantic correctness.

Answers group equivalent source teachings into one explanation with multiple citations. Distinct contexts and qualifications stay separate. A conservative sentence-similarity check sends substantially repeated or closely paraphrased sentences through the same bounded recovery. This check does not establish semantic equivalence. Short supported answers are accepted without an automatic length-expansion pass; word targets do not justify padding.
