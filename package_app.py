import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

FILES = ["LICENSE", "README.md", "requirements.txt", "app.py", "archive_books.py", "bible_html.py",
         "catalog.py", "ingest.py", "local_model.py", "model_options.py", "official_sources.py", "question_policy.py", "web_sources.py", "setup.py", "rag.py", "search.py", "research.py", "research_selection.py", "package_app.py",
         "launcher.py", "build_installer.py", "installer/windows.iss", ".github/workflows/installers.yml",
         "web/index.html", "web/app.js", "web/research.js", "web/setup.html", "docs/deep_research.md", "docs/website_sources.md", "docs/model_and_retrieval.md", "docs/sharing.md", "docs/models.md", "docs/desktop_install.md"]

def package(output):
    root = Path(__file__).resolve().parent
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Choose a new package filename")
    output.parent.mkdir(parents=True, exist_ok=True)
    # A fixed code allowlist never walks a user's book directory
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
