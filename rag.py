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
    for name in ("search", "ask"):
        query = commands.add_parser(name)
        query.add_argument("question")
        query.add_argument("--index", required=True)
        query.add_argument("--mode", choices=["lexical", "hybrid"], default="lexical")
        query.add_argument("--book", default="")
        query.add_argument("--limit", type=int, default=4)
        if name == "ask":
            query.add_argument("--model", default="qwen2.5:7b")
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_index(args.source, args.index, args.embedding_model)
        else:
            hits = SearchIndex(args.index).search(args.question, args.mode, args.limit, args.book)
            result = generate(args.question, hits, args.model) if args.command == "ask" and hits else {"sources": hits}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, str(error) + "\n")

if __name__ == "__main__":
    main()
