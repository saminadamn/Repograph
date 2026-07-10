#!/usr/bin/env python3
"""
RepoGraph CLI
Usage:
  python cli.py analyze https://github.com/user/repo
  python cli.py query <graph_id> "how does authentication work?"
  python cli.py savings <graph_id>
"""

import sys
import json
import argparse
from pathlib import Path
import tempfile
import hashlib

# Ensure emoji output doesn't crash on non-UTF-8 terminals (e.g. Windows cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.graph.builder import RepoGraphBuilder, RepoGraph
from src.llm.context_packer import ContextPacker
from src.utils.github_fetcher import GitHubFetcher

CACHE_DIR = Path(tempfile.gettempdir()) / "repograph_cache"
CACHE_DIR.mkdir(exist_ok=True)


def make_graph_id(repo_url: str, branch: str = "main") -> str:
    return hashlib.md5(f"{repo_url}:{branch}".encode()).hexdigest()[:12]


def cmd_analyze(args):
    graph_id = make_graph_id(args.repo_url, args.branch)
    cache_path = CACHE_DIR / f"{graph_id}.json"

    if cache_path.exists() and not args.force:
        print(f"✓ Already analyzed. Graph ID: {graph_id}")
        print(f"  Use: python cli.py query {graph_id} 'your question'")
        return

    print(f"🔍 Analyzing {args.repo_url}...")
    with GitHubFetcher() as fetcher:
        local_path = fetcher.fetch(args.repo_url, args.branch)
        builder = RepoGraphBuilder(local_path)
        graph = builder.build()
        graph.repo_path = args.repo_url
        graph.save(str(cache_path))

    packer = ContextPacker(graph)
    savings = packer.estimate_savings()

    print(f"\n✅ Graph Built Successfully!")
    print(f"   Graph ID:    {graph_id}")
    print(f"   Nodes:       {len(graph.nodes)} files")
    print(f"   Edges:       {len(graph.edges)} dependencies")
    print(f"   Total tokens if full repo: {savings['full_repo_tokens']:,}")
    print(f"   Smart context tokens:      {savings['smart_context_tokens']:,}")
    print(f"   Compression:               {savings['compression_ratio']}")
    print(f"   Savings/100 queries:       {savings['savings_per_100_queries']}")
    print(f"\n💡 Next: python cli.py query {graph_id} 'how does X work?'")


def cmd_query(args):
    cache_path = CACHE_DIR / f"{args.graph_id}.json"
    if not cache_path.exists():
        print(f"❌ Graph '{args.graph_id}' not found. Run analyze first.")
        sys.exit(1)

    graph = RepoGraph.load(str(cache_path))
    packer = ContextPacker(graph, token_budget=args.tokens)
    result = packer.pack_for_query(args.query, include_snippets=not args.no_snippets)

    print(f"📦 Context packed for: '{args.query}'")
    print(f"   Tokens used:     {result.estimated_tokens:,} / {args.tokens:,} budget")
    print(f"   Files included:  {len(result.nodes_included)}")
    print(f"   Compression:     {result.compression_ratio*100:.1f}% reduction vs full repo")
    print(f"\n{'='*60}")
    print(result.context_text)
    print(f"{'='*60}")

    if args.output:
        Path(args.output).write_text(result.context_text)
        print(f"\n💾 Context saved to {args.output}")


def cmd_savings(args):
    cache_path = CACHE_DIR / f"{args.graph_id}.json"
    if not cache_path.exists():
        print(f"❌ Graph '{args.graph_id}' not found.")
        sys.exit(1)

    graph = RepoGraph.load(str(cache_path))
    packer = ContextPacker(graph)
    s = packer.estimate_savings()

    print(f"\n💰 Cost Savings Estimate for this Repo")
    print(f"   Full repo tokens:        {s['full_repo_tokens']:,}")
    print(f"   Smart context tokens:    {s['smart_context_tokens']:,}")
    print(f"   Compression ratio:       {s['compression_ratio']}")
    print(f"   Cost/query (naive):      {s['cost_per_query_naive']}")
    print(f"   Cost/query (RepoGraph):  {s['cost_per_query_smart']}")
    print(f"   Savings per 100 queries: {s['savings_per_100_queries']}")


def main():
    parser = argparse.ArgumentParser(
        description="RepoGraph: Graph-based GitHub repo analyzer. Reduce LLM costs 50-70%."
    )
    subs = parser.add_subparsers(dest="command")

    # analyze
    p_analyze = subs.add_parser("analyze", help="Analyze a GitHub repo")
    p_analyze.add_argument("repo_url", help="GitHub repo URL")
    p_analyze.add_argument("--branch", default="main")
    p_analyze.add_argument("--force", action="store_true", help="Re-analyze even if cached")

    # query
    p_query = subs.add_parser("query", help="Query analyzed repo")
    p_query.add_argument("graph_id", help="Graph ID from analyze step")
    p_query.add_argument("query", help="Your question about the codebase")
    p_query.add_argument("--tokens", type=int, default=8000, help="Token budget (default: 8000)")
    p_query.add_argument("--no-snippets", action="store_true")
    p_query.add_argument("--output", help="Save context to file")

    # savings
    p_savings = subs.add_parser("savings", help="Show cost savings estimate")
    p_savings.add_argument("graph_id")

    args = parser.parse_args()
    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "query":
        cmd_query(args)
    elif args.command == "savings":
        cmd_savings(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
