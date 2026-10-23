"""Run the fixed Agent comparison without credentials or model calls."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from labs.live_data.query import open_database, seed

from .loop import answer_once, run_agent
from .planner import EvidencePlanner
from .tools import SourceDocument, code_tool, inventory_tool, lexical_tool, read_tool


def documents() -> tuple[SourceDocument, ...]:
    root = Path.cwd() / "fixtures" / "agent"
    return (
        SourceDocument("deploy", "v1", (root / "deployment-v1.txt").read_text().rstrip("\n"), ("limits",)),
        SourceDocument("limits", "v1", (root / "limits-v1.txt").read_text().rstrip("\n")),
        SourceDocument("e104", "v1", (root / "errors-v1.txt").read_text().rstrip("\n")),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fixed retrieval Agent experiment")
    parser.add_argument("--question", default="rolling deployment")
    parser.add_argument("--single", action="store_true")
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()
    sources = documents()
    search = lexical_tool(sources)
    connection = open_database()
    try:
        seed(connection, [("SKU_1", "widget", 12)])
        tools = [search, read_tool(sources), inventory_tool(connection), code_tool(Path.cwd() / "fixtures" / "code_search" / "repository", source_version="fixture-v1")]
        if args.single:
            answer = answer_once(args.question, search, {"query": args.question})
        else:
            answer = run_agent(args.question, tools, EvidencePlanner(), max_steps=args.max_steps)
    finally:
        connection.close()
    print(json.dumps(asdict(answer), ensure_ascii=False, indent=2))
    return 0 if answer.answerable or answer.stop_reason == "no_evidence" else 1


if __name__ == "__main__":
    raise SystemExit(main())
