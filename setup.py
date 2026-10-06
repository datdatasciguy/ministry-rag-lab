import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from model_options import PROFILES, read_settings

def choose_model():
    print("Choose a local answer model. RAM/GPU suggestions are planning estimates, not minimum guarantees.")
    print("Mobile-scale describes model size; this app runs with Python/Ollama on a computer.")
    for number, profile in enumerate(PROFILES, 1):
        print(f"\n{number}. {profile['label']} - {profile['model']} ({profile['download']})")
        print(profile["hardware"])
        print(profile["tradeoff"])
        print(f"App budget: {profile['sources']} sources; up to {profile['words']} target words.")
    while True:
        selection = input("\nModel number [3 for a basic laptop]: ").strip() or "3"
        if selection.isdigit() and 1 <= int(selection) <= len(PROFILES):
            return PROFILES[int(selection) - 1]
        print("Choose a number from the list.")

def ollama_executable():
    found = shutil.which("ollama")
    if found:
        return found
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"
    if candidate.is_file():
        return str(candidate)
    raise ValueError("Install and start Ollama from https://ollama.com/download, then run setup again.")

def configure(profile, path, download=True):
    if download:
        executable = ollama_executable()
        for model in ["nomic-embed-text:v1.5", profile["model"]]:
            subprocess.run([executable, "pull", model], check=True)
    path = Path(path)
    settings = read_settings(path)
    settings.update(model=profile["model"])
    settings.setdefault("index", "data/books.sqlite")
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(".json.tmp")
    pending.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)
    return settings

def main():
    parser = argparse.ArgumentParser(description="First-run local model selection and downloads.")
    parser.add_argument("--model", choices=[profile["model"] for profile in PROFILES])
    parser.add_argument("--list", action="store_true", help="Show options without downloading or saving")
    parser.add_argument("--no-download", action="store_true", help="Save the choice only; does not verify model availability")
    parser.add_argument("--settings", default="data/settings.json")
    args = parser.parse_args()
    if args.list:
        for profile in PROFILES:
            print(json.dumps(profile, ensure_ascii=False))
        return
    profile = next((row for row in PROFILES if row["model"] == args.model), None) if args.model else choose_model()
    try:
        configure(profile, args.settings, not args.no_download)
    except (ValueError, subprocess.CalledProcessError, OSError) as error:
        parser.exit(1, str(error) + "\n")
    print("Saved model choice." if args.no_download else "Selected model and embeddings downloaded; preference saved.")
    print("Next: build an index from your own permitted collection, then run python app.py --index data/books.sqlite.")

if __name__ == "__main__":
    main()
