import argparse
import json
import time

from search import SearchIndex

def evaluate(index_path, questions, mode, limit):
    index = SearchIndex(index_path)
    results = []
    for row in questions:
        start = time.perf_counter()
        hits = index.search(row["question"], mode, limit)
        ranks = [rank for rank, hit in enumerate(hits, 1) if hit["title"] in row["relevant_titles"]]
        results.append({"question": row["question"], "hit": bool(ranks),
                        "reciprocal_rank": 1 / min(ranks) if ranks else 0,
                        "seconds": round(time.perf_counter() - start, 4)})
    if not results:
        raise ValueError("No evaluation questions supplied")
    return {"mode": mode, "queries": len(results), "limit": limit,
            "hit_at_k": sum(row["hit"] for row in results) / len(results),
            "mean_reciprocal_rank": sum(row["reciprocal_rank"] for row in results) / len(results),
            "results": results}

def main():
    parser = argparse.ArgumentParser(description="Measure retrieval against supplied relevant titles.")
    parser.add_argument("--index", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--mode", choices=["lexical", "hybrid"], default="lexical")
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()
    with open(args.questions, encoding="utf-8") as stream:
        questions = [json.loads(line) for line in stream if line.strip()]
    print(json.dumps(evaluate(args.index, questions, args.mode, args.limit), indent=2))

if __name__ == "__main__":
    main()
