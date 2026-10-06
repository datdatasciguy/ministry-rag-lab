import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

FILES = ["LICENSE", "README.md", "requirements.txt", "app.py", "archive_books.py", "bible_html.py",
         "catalog.py", "evaluate.py", "ingest.py", "local_model.py", "rag.py", "search.py", "package_app.py",
         "web/index.html", "web/app.js", "examples/sections.jsonl", "examples/questions.jsonl",
         "docs/model_and_retrieval.md"]

def package(output):
    root = Path(__file__).resolve().parent
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Choose a new package filename")
    output.parent.mkdir(parents=True, exist_ok=True)
    # A fixed code/demo allowlist never walks a user's book directory
    with ZipFile(output, "x", ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(root / name, "ministry-search-rag/" + name)
    return output

def main():
    parser = argparse.ArgumentParser(description="Prepare a code-only app package. Books, indexes and models are excluded.")
    parser.add_argument("--output", default="outputs/ministry-search-rag-code.zip")
    args = parser.parse_args()
    print(package(args.output))

if __name__ == "__main__":
    main()
