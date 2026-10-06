import argparse
import json

from local_model import generate
from search import SearchIndex, build_index

def main():
    # Arguments
    parser = argparse.ArgumentParser(description="Search local books and ask a local model about passages.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--source", action="append", required=True)
    build.add_argument("--index", required=True)
    build.add_argument("--embedding-model")
    build.add_argument("--resume", action="store_true")
    for name in ("search", "ask"):
        query = commands.add_parser(name)
        query.add_argument("question")
        query.add_argument("--index", required=True)
        query.add_argument("--mode", choices=["lexical", "hybrid"], default="lexical")
        query.add_argument("--book", default="")
        query.add_argument("--author", choices=["auto", "all", "Witness Lee", "Watchman Nee"], default="auto")
        query.add_argument("--collection", choices=["all", "ministry", "bible", "notes", "balanced"], default="all")
        query.add_argument("--limit", type=int, default=8 if name == "ask" else 6,
                           help="Passages to return (search: 1–100; ask: 1–40)")
        if name == "ask":
            query.add_argument("--model", default="qwen2.5:7b")
            query.add_argument("--length", choices=["short", "medium", "detailed", "custom"], default="medium")
            query.add_argument("--words", type=int, default=250, help="Custom word target (50–1,500)")
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_index(args.source, args.index, args.embedding_model, resume=args.resume)
        else:
            hits = SearchIndex(args.index).search(args.question, args.mode, args.limit, args.book, args.author, args.collection)
            result = generate(args.question, hits, args.model, args.length, args.words) if args.command == "ask" and hits else {"sources": hits}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, str(error) + "\n")

if __name__ == "__main__":
    main()
