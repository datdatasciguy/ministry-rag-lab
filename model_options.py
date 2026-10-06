import json
from pathlib import Path

PROFILES = [
    {"model": "smollm2:360m-instruct-q4_K_M", "label": "Tiny / mobile-scale", "download": "271 MB",
     "hardware": "4 GB RAM for a small collection; 8 GB for the full index. CPU, no GPU needed.",
     "tradeoff": "Lowest memory use; weak instruction following and citation reliability. Prefer short answers and read the passages.",
     "sources": 4, "words": 250, "context": 4096},
    {"model": "qwen3:0.6b", "label": "Low-memory", "download": "523 MB",
     "hardware": "8 GB RAM, modern 64-bit CPU; GPU optional.",
     "tradeoff": "Small download and short-answer use; complex theology and multi-source synthesis need careful checking.",
     "sources": 4, "words": 250, "context": 4096},
    {"model": "qwen3:1.7b", "label": "Basic laptop", "download": "1.4 GB",
     "hardware": "8-16 GB RAM; CPU works, optional 2-4 GB GPU for speed.",
     "tradeoff": "A modest starting point for a weaker laptop. More room than 0.6B, but still limited evidence synthesis.",
     "sources": 6, "words": 600, "context": 8192},
    {"model": "qwen2.5:3b", "label": "Everyday laptop", "download": "1.9 GB",
     "hardware": "16 GB RAM; CPU works, optional 4 GB GPU.",
     "tradeoff": "Middle ground for memory and source-based answers. Slower on CPU; review terminology and citations.",
     "sources": 8, "words": 600, "context": 8192},
    {"model": "qwen3:4b-instruct", "label": "Stronger laptop", "download": "2.5 GB",
     "hardware": "16 GB RAM; optional 6-8 GB GPU for larger context.",
     "tradeoff": "More capacity with a modest download; source grounding is still checked rather than assumed.",
     "sources": 12, "words": 800, "context": 16384},
    {"model": "qwen2.5:7b", "label": "Balanced desktop", "download": "4.7 GB",
     "hardware": "16-32 GB RAM; 8-12 GB GPU recommended for speed, or 16+ GB unified memory.",
     "tradeoff": "Useful local reading and synthesis option; heavier than laptop models. Verified on selected project queries.",
     "sources": 20, "words": 1000, "context": 16384},
    {"model": "qwen2.5:14b", "label": "Larger desktop", "download": "9 GB",
     "hardware": "32 GB RAM; 16-24 GB GPU recommended, or 32 GB unified memory.",
     "tradeoff": "Current developer model, checked with 40 evidence passages. More memory and latency; no general accuracy guarantee.",
     "sources": 40, "words": 1500, "context": 32768},
    {"model": "qwen2.5:32b", "label": "Workstation", "download": "20 GB",
     "hardware": "64 GB RAM; 32 GB GPU preferred, or 64 GB unified memory. CPU offload can be slow.",
     "tradeoff": "Largest option here; expensive memory/context. No project quality benchmark establishes a gain over 14B.",
     "sources": 40, "words": 1500, "context": 32768}
]

def model_profile(name):
    for profile in PROFILES:
        if name == profile["model"]:
            return profile
    return {"model": name, "sources": 8, "words": 600, "context": 8192}

def read_settings(path="data/settings.json"):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
