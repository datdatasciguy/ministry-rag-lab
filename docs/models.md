# Choose a local model

Run `python setup.py` during installation. It explains each option, asks which
one to use, downloads that answer model plus Nomic embeddings, and saves the
choice in ignored `data/settings.json`. It does not download every option.
Keep Ollama running. Run setup again to add or change a model; the app's Model
control lets you switch among downloaded choices without rebuilding the index.

## Size and hardware

These are conservative **planning suggestions**, not measured minimums or speed
benchmarks. RAM must also cover the OS, Python and your collection. A large
collection needs more memory than a few books. GPU memory includes the weights
and context cache; the download size alone is not the runtime requirement.
CPU inference is supported but can be slow. Apple unified memory is shared.

| Option | Download | Suggested hardware | Tradeoff |
| --- | --- | --- | --- |
| SmolLM2 360M Q4 | 271 MB | 4 GB RAM for a small collection, 8 GB for the full index; CPU | Tiny, mobile-scale; weak instruction and citation reliability. Prefer reading search results. |
| Qwen3 0.6B | 523 MB | 8 GB RAM; modern CPU, GPU optional | Short answers with few sources; limited synthesis. |
| Qwen3 1.7B | 1.4 GB | 8–16 GB RAM; optional 2–4 GB GPU | Initial suggestion for a weaker laptop; check complex answers carefully. |
| Qwen2.5 3B | 1.9 GB | 16 GB RAM; optional 4 GB GPU | More capacity while keeping the download small. |
| Qwen3 4B Instruct | 2.5 GB | 16 GB RAM; optional 6–8 GB GPU | Stronger laptop option with more evidence room. |
| Qwen2.5 7B | 4.7 GB | 16–32 GB RAM; 8–12 GB GPU or 16+ GB unified memory | Balanced desktop option, checked on selected project queries. |
| Qwen2.5 14B | 9 GB | 32 GB RAM; 16–24 GB GPU or 32 GB unified memory | Developer's current model; checked with up to 40 passages. |
| Qwen2.5 32B | 20 GB | 64 GB RAM; 32 GB GPU or 64 GB unified memory | Workstation option; more memory and latency. A quality gain has not been established here. |

Download sizes come from [SmolLM2's tag](https://ollama.com/library/smollm2:360m-instruct-q4_K_M),
[Qwen3 tags](https://ollama.com/library/qwen3/tags) and
[Qwen2.5 tags](https://ollama.com/library/qwen2.5/tags). Tags can change.
Nomic v1.5 adds about 274 MB separately. See
[Ollama's hardware support](https://docs.ollama.com/gpu) for supported GPUs.

Mobile-scale describes the model's size. This application still requires a
computer running Python and Ollama; it is not a native phone application.
The 1.7B, 7B and 14B options have passed selected local answer checks; the other
profiles have not been benchmarked here. Keyword search works without an answer model. Semantic search needs Nomic;
generating an answer also needs the chosen model. Small models may return an
invalid quotation/citation or abstain. The app reports validation failures;
use the retrieved passages directly or switch models.

## Evidence and answer budgets

| Model size | Maximum answer sources | Maximum target words | Context ceiling |
| --- | ---: | ---: | ---: |
| 360M / 0.6B | 4 | 250 | 4,096 tokens |
| 1.7B | 6 | 600 | 8,192 tokens |
| 3B | 8 | 600 | 8,192 tokens |
| 4B Instruct | 12 | 800 | 16,384 tokens |
| 7B | 20 | 1,000 | 16,384 tokens |
| 14B / 32B | 40 | 1,500 | 32,768 tokens |

These are app budgets, not model architecture limits or guarantees that every
source influences an answer. Search can still return up to 100 passages for
reading. The UI adjusts its answer controls when the model changes; the server
rejects requests over the selected budget. Word targets remain approximate.
More sources and longer context consume more memory and can dilute relevance.
Use `ollama ps` to inspect loaded context and CPU/GPU placement; see
[Ollama's context guide](https://docs.ollama.com/context-length).

## Change the choice

```bash
python setup.py
python app.py --index data/books.sqlite
```

For a scripted choice, use `python setup.py --model qwen2.5:3b`.
`--list` shows options without downloading or saving. `--no-download` saves a
preference only and does not verify that the model is available. An explicit
`app.py --model` overrides the saved preference. Changing the answer model does
not change embeddings; changing the embedding model requires a new index.

The code license does not cover model weights. Check each provider's model card
and terms before using it: [SmolLM2](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct),
[Qwen3](https://huggingface.co/Qwen/Qwen3-1.7B), and
[Qwen2.5 3B](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct).
In particular, Qwen2.5 3B uses the Qwen research license; do not assume all
options have the same license. No models are redistributed with this repo.
