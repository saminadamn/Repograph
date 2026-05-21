"""
RepoGraph - FastAPI Backend
Exposes the graph builder + context packer as a REST API.

Endpoints:
  POST /analyze      - Analyze a GitHub repo, build graph, cache it
  POST /query        - Query the graph, get optimized LLM context
  GET  /graph/{id}   - Get full graph data (for visualization)
  GET  /savings/{id} - Get cost savings estimate
"""

import os
import json
import hashlib
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from ..graph.builder import RepoGraphBuilder, RepoGraph
from ..llm.context_packer import ContextPacker
from ..utils.github_fetcher import GitHubFetcher

app = FastAPI(
    title="RepoGraph API",
    description="Graph-based GitHub repo analyzer. Reduces LLM token usage by 50-70%.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple file-based cache (production: use Redis)
CACHE_DIR = Path(tempfile.gettempdir()) / "repograph_cache"
CACHE_DIR.mkdir(exist_ok=True)


# --- Request/Response Models ---

class AnalyzeRequest(BaseModel):
    repo_url: str
    branch: str = "main"
    max_file_size_kb: int = 500

class AnalyzeResponse(BaseModel):
    graph_id: str
    repo_url: str
    node_count: int
    edge_count: int
    estimated_total_tokens: int
    message: str

class QueryRequest(BaseModel):
    graph_id: str
    query: str
    token_budget: int = 8000
    include_snippets: bool = True

class QueryResponse(BaseModel):
    context: str
    nodes_included: list[str]
    estimated_tokens: int
    total_repo_tokens: int
    compression_ratio: float
    savings_summary: str


# --- Helpers ---

def _graph_cache_path(graph_id: str) -> Path:
    return CACHE_DIR / f"{graph_id}.json"

def _make_graph_id(repo_url: str, branch: str) -> str:
    return hashlib.md5(f"{repo_url}:{branch}".encode()).hexdigest()[:12]

def _load_graph(graph_id: str) -> RepoGraph:
    path = _graph_cache_path(graph_id)
    if not path.exists():
        raise HTTPException(404, f"Graph '{graph_id}' not found. Run /analyze first.")
    return RepoGraph.load(str(path))


# --- Endpoints ---

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repo(req: AnalyzeRequest):
    """
    Clone a GitHub repo, build its dependency graph, and cache it.
    This is the expensive one-time step. Subsequent queries are cheap.
    """
    graph_id = _make_graph_id(req.repo_url, req.branch)
    cache_path = _graph_cache_path(graph_id)

    # Return cached result if exists
    if cache_path.exists():
        graph = RepoGraph.load(str(cache_path))
        total_tokens = sum(n.size_bytes for n in graph.nodes.values()) // 4
        return AnalyzeResponse(
            graph_id=graph_id,
            repo_url=req.repo_url,
            node_count=len(graph.nodes),
            edge_count=len(graph.edges),
            estimated_total_tokens=total_tokens,
            message="Loaded from cache (already analyzed)"
        )

    # Clone and analyze
    with GitHubFetcher() as fetcher:
        try:
            local_path = fetcher.fetch(req.repo_url, req.branch)
        except RuntimeError as e:
            raise HTTPException(400, str(e))

        builder = RepoGraphBuilder(local_path, req.max_file_size_kb)
        graph = builder.build()
        graph.repo_path = req.repo_url  # Store URL, not temp path
        graph.save(str(cache_path))

    total_tokens = sum(n.size_bytes for n in graph.nodes.values()) // 4
    return AnalyzeResponse(
        graph_id=graph_id,
        repo_url=req.repo_url,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        estimated_total_tokens=total_tokens,
        message=f"Graph built and cached. {len(graph.nodes)} files analyzed."
    )


@app.post("/query", response_model=QueryResponse)
async def query_graph(req: QueryRequest):
    """
    Query the cached graph. Returns optimized context for your LLM.
    This is the cheap, repeated operation — only sends relevant nodes.
    """
    graph = _load_graph(req.graph_id)
    packer = ContextPacker(graph, token_budget=req.token_budget)
    result = packer.pack_for_query(req.query, req.include_snippets)
    savings = packer.estimate_savings()

    savings_summary = (
        f"Sending {result.estimated_tokens:,} tokens instead of "
        f"{result.total_repo_tokens:,} full-repo tokens. "
        f"Saved ~{result.compression_ratio*100:.0f}% — "
        f"approx {savings['savings_per_100_queries']} per 100 queries."
    )

    return QueryResponse(
        context=result.context_text,
        nodes_included=result.nodes_included,
        estimated_tokens=result.estimated_tokens,
        total_repo_tokens=result.total_repo_tokens,
        compression_ratio=result.compression_ratio,
        savings_summary=savings_summary
    )


@app.get("/graph/{graph_id}")
async def get_graph(graph_id: str):
    """Get full graph data for visualization (nodes + edges)."""
    graph = _load_graph(graph_id)
    return graph.to_dict()


@app.get("/savings/{graph_id}")
async def get_savings(graph_id: str):
    """Estimate cost savings for this repo."""
    graph = _load_graph(graph_id)
    packer = ContextPacker(graph)
    return packer.estimate_savings()


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
async def root():
    return {
        "name": "RepoGraph",
        "tagline": "Graph-based repo context. 50-70% fewer LLM tokens.",
        "docs": "/docs"
    }
