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

Song-only hybrid searches use weighted RRF: the semantic list contributes
`3 / (60 + rank)`, while the lexical list contributes `1 / (60 + rank)`.
Other collections retain the equal-weight fusion above. This weight is a chosen
retrieval heuristic, not a fitted parameter or a measured optimum.

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

Answer validation failures trigger bounded recovery: first a corrected draft, then alternate lexical or hybrid retrieval within the same collection, author, book and source-count filters. Advanced settings allow 1-5 total generation attempts, defaulting to three. Citation numbering is rebuilt when passages change. A valid abstention is accepted without draft repair; optional related-topic recovery can use the remaining attempt budget. Retries do not manufacture evidence. If all attempts fail, sources remain readable and an unverified draft is shown only when the separate extrapolation or unverified-draft option is enabled, with citation markers removed. Model connection failures are reported directly. Extra attempts add latency; they do not establish semantic correctness.

Answers group equivalent source teachings into one explanation with multiple citations. Distinct contexts and qualifications stay separate. A conservative sentence-similarity check sends substantially repeated or closely paraphrased sentences through the same bounded recovery. This check does not establish semantic equivalence. Short supported answers are accepted without an automatic length-expansion pass; word targets do not justify padding.

## Broad questions and rankings

A lightweight wording heuristic flags broad rankings and collection-wide summaries. The page displays a prominent scope notice independently of the model, with the actual number of supplied passages. The prompt asks for findings from this sample: recurring themes, distinct contexts and cited examples. Unless a source explicitly supplies the requested list, findings are provisional, not an authoritative ranking. Requested counts do not justify inventing items. All examples means all supported examples in the retrieved sample, subject to the selected answer budget. Changes over time require explicit dated evidence. The heuristic may miss unusual wording, and prompting does not verify historical development or ranking claims.

This remains passage-based RAG. Microsoft GraphRAG instead uses collection-wide community summaries for global questions: https://microsoft.github.io/graphrag/query/global_search/ . That architecture has not been implemented here.

## Evidence cautions and related-topic recovery

Exact duplicates from the same source are removed before generation, with citation numbers rebuilt. Repeated text across different titles is retained with a caution: it is not an independent vote for a teaching's importance. Small samples and concentration in one title produce visible notices. Author information remains on source cards without a routine authorship warning. A rough character-based estimate can raise the context setting to the profile limit and warns near capacity; it is not a tokenizer or a guarantee against truncation or overlooked evidence.

Quotations must occur in the cited source set, and inline citation numbers must agree with the supporting-passage list. These checks do not prove that every claim follows from its individual citation. The model is prompted to correct unsupported premises, ignore irrelevant passages and preserve conflicts and differences in context. Model-flagged evidence concerns are labeled as unverified. Sources are supplied as JSON data, never executable instructions; a lightweight injection-pattern warning supplements the existing local-only, no-tool generation design. Neither that heuristic nor prompting provides complete protection against poisoned sources.

When the initial sample provides no answer, one local model call can suggest up to three neutral related search phrases. Those searches keep the original author, book and collection filters. Remaining answer attempts use the original question and the new evidence. The displayed terms are hypotheses, not doctrinal classifications. An unclear term requests clarification instead of a fabricated meaning. An abstention does not summarize unrelated hits. Advanced settings can disable expansion or expose a rejected model draft after the attempt limit; that draft is prominently labeled unverified and has citation markers removed. Inspecting it does not relax source checks or enable cloud inference.

Relevant research: [irrelevant-context robustness](https://arxiv.org/abs/2310.01558), [Lost in the Middle](https://arxiv.org/abs/2307.03172), [conflicting evidence](https://arxiv.org/abs/2504.13079), [citation evaluation](https://aclanthology.org/2023.emnlp-main.398/), and [PoisonedRAG](https://arxiv.org/abs/2402.07867). These motivate the safeguards; their training methods and benchmarks have not been reproduced here.

## Deep research extension

Normal RAG answers use the ranked passages supplied in their context. The optional [Deep research mode](deep_research.md) scans all scoped stored sections through resumable word windows, validates exact excerpts, and builds a saved hierarchy of question-focused summaries. Its final citations link through evidence groups to original sections. This uses inference, not fine-tuning, and is not a GraphRAG knowledge graph or RAPTOR clustering implementation. Complete scan coverage does not guarantee that the model recognized every relevant teaching or preserved every nuance during reduction.

## Introductory and FAQ retrieval

Website and FAQ text is part of the local searchable index. Before ordinary answers, one local model call identifies the question's intent, suggests concise retrieval wording and selects up to three relevant topic categories. Categories map to reviewed source-page URLs, not canned answers. For definitions, biographies, statements of faith and introductory topics, matching source pages receive retrieval priority within the existing author, book and collection filters. Only matching pages in those categories are promoted; unrelated website pages are not substituted. The answer is generated from the retrieved passages with ordinary source checks and clickable citations. Find passages keeps lightweight word/topic matching without the additional planner call.

The prompt directs the answer to explain directly supported teaching in the ministry's own voice and vocabulary, using explicit definitions as the basis when available. It does not describe the teaching as an outsider's conceptual analysis or insert routine controversy notices. Missing evidence, background applications and actual conflicts remain qualified. A passage about one practice does not define the entire subject. Publisher and author provenance remain on the source cards. Topic planning, retrieval weights and prompting are inference-time behavior; no model weights were trained.

The [website importer](website_sources.md) copies the existing private index into a new file and adds public article sections, FTS rows and embeddings using the unchanged embedding model. Publisher/URL/time/hash provenance and explicit FAQ routing support a limited website retrieval preference. These are deterministic rules, not trained ranking weights. Answer prompts present directly supported teaching naturally and constructively, retaining evidence qualifications. The generic long-evidence notice has been removed; actual context-capacity cautions remain.

## Advanced response overrides

Both controls are off by default. **Show a response even if source checks fail** exposes the last rejected draft after the attempt limit, with an unverified warning and citation markers removed. It does not label the draft as verified. **Skip inappropriate-wording guidance** skips the app’s wording rewrite and early refusal, sending the original question to the local model. A notice identifies the override; model behavior and evidence checks remain active. This wording option also applies when starting Deep research. The options do not change source filters, localhost access checks or source-as-data handling.

Known misspellings of the Lord's recovery are normalized for routing and retrieval, with a visible search-wording notice when corrected. The local query planner can also improve retrieval wording for other introductory questions.

## Poetic meaning in song recommendations

For topical Songs & hymns queries, the app uses the local answer model as a
retrieval planner and relevance judge before answer generation:

1. Interpret the requested topic or listener situation and produce up to two
   complementary conceptual queries. Retain the original query. Merge retrieved
   candidates across queries with rank-based scores, giving the original query
   a weight of 1.5 and each expansion a weight of 1.
2. Read each candidate's **complete lyrics**, independently of the user question.
   Interpret the central subject, imagery, emotional direction and temporal or
   experiential setting. The model selects supporting line numbers; code checks
   their bounds and resolves them to actual stored lines. This prevents invented
   anchor quotations, but does not prove that the interpretation is correct.
3. Compare that interpretation with the request. Purpose and situation each get
   an ordinal 0–3 fit judgment. The smaller score controls initial eligibility;
   a shared emotion cannot compensate for a weak purpose score. Only scores of
   at least 2 proceed to a side-by-side comparison that orders the best matches
   and can omit weaker candidates rather than filling a quota.
4. Supply the selected complete lyrics to generation, with the existing citation
   and quotation checks. Keep the original song URLs and lyric formatting.

This is inference with pretrained models, not a trained cross-encoder or new
embedding model. The default review pool is 32 songs, adjustable from 8 to 60.
Review calls are bounded by that pool and model context, with validated JSON IDs
and private caches keyed by model digest, content and query. Exact number and
complete-title lookups bypass the review. Users can disable it in Advanced;
review failures label the ordinary-retrieval fallback.

The development check used a loneliness/church-home request: O home in the
church ranked first, and a song about awaiting the Lord's return was omitted.
A different query about longing for the Lord's return selected songs on that
subject. These are targeted checks, not an accuracy benchmark. Poetic
interpretation, candidate recall, ranking judgments and query expansion can
still be wrong. No rule assigns those example songs a preferred position.
