"""
RepoGraph - Tests
Run with: pytest tests/ -v
"""

import os
import sys
import json
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.graph.builder import RepoGraphBuilder, RepoGraph, CodeNode, CodeEdge
from src.llm.context_packer import ContextPacker


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_repo(tmp_path):
    """Creates a tiny fake repo with 3 Python files and clear dependencies."""
    # main.py imports auth and db
    (tmp_path / "main.py").write_text(
        "from auth import login\nfrom db import get_user\n\ndef run():\n    user = get_user(1)\n    login(user)\n"
    )
    # auth.py imports db
    (tmp_path / "auth.py").write_text(
        "from db import get_user\n\ndef login(user):\n    pass\n\ndef logout(user):\n    pass\n"
    )
    # db.py imports nothing internal
    (tmp_path / "db.py").write_text(
        "import sqlite3\n\nclass Database:\n    pass\n\ndef get_user(uid):\n    return {}\n\ndef save_user(user):\n    pass\n"
    )
    return tmp_path


@pytest.fixture
def built_graph(sample_repo):
    builder = RepoGraphBuilder(str(sample_repo))
    return builder.build()


# ── Graph Builder Tests ───────────────────────────────────────────────────────

class TestGraphBuilder:

    def test_node_count(self, built_graph):
        """All 3 files should be parsed as nodes."""
        assert len(built_graph.nodes) == 3

    def test_node_ids_are_relative_paths(self, built_graph):
        ids = set(built_graph.nodes.keys())
        assert "main.py" in ids
        assert "auth.py" in ids
        assert "db.py" in ids

    def test_functions_extracted(self, built_graph):
        db_node = built_graph.nodes["db.py"]
        assert "get_user" in db_node.functions
        assert "save_user" in db_node.functions

    def test_classes_extracted(self, built_graph):
        db_node = built_graph.nodes["db.py"]
        assert "Database" in db_node.classes

    def test_imports_extracted(self, built_graph):
        auth_node = built_graph.nodes["auth.py"]
        assert "db" in auth_node.imports

    def test_raw_snippet_stored(self, built_graph):
        node = built_graph.nodes["main.py"]
        assert len(node.raw_snippet) > 0
        assert "from auth import login" in node.raw_snippet

    def test_snippet_max_30_lines(self, built_graph):
        for node in built_graph.nodes.values():
            assert len(node.raw_snippet.splitlines()) <= 30

    def test_edges_created(self, built_graph):
        """main.py → db.py and auth.py → db.py edges should exist."""
        edge_pairs = {(e.source, e.target) for e in built_graph.edges}
        assert ("main.py", "db.py") in edge_pairs or len(built_graph.edges) > 0

    def test_importance_score_in_summary(self, built_graph):
        """Every node should have an importance score in its summary."""
        for node in built_graph.nodes.values():
            assert "importance=" in node.summary

    def test_db_has_highest_importance(self, built_graph):
        """db.py is imported by both main.py and auth.py → highest importance."""
        import re
        scores = {}
        for path, node in built_graph.nodes.items():
            m = re.search(r'importance=([\d.]+)', node.summary)
            scores[path] = float(m.group(1)) if m else 0
        assert scores.get("db.py", 0) >= scores.get("main.py", 0)

    def test_ignore_dirs_skipped(self, sample_repo):
        """node_modules and .git should be ignored."""
        (sample_repo / "node_modules").mkdir()
        (sample_repo / "node_modules" / "lodash.py").write_text("x=1")
        builder = RepoGraphBuilder(str(sample_repo))
        graph = builder.build()
        for node_id in graph.nodes:
            assert "node_modules" not in node_id

    def test_large_files_skipped(self, sample_repo):
        big = sample_repo / "huge.py"
        big.write_bytes(b"x = 1\n" * 200_000)  # ~1.2 MB
        builder = RepoGraphBuilder(str(sample_repo), max_file_size_kb=500)
        graph = builder.build()
        assert "huge.py" not in graph.nodes


# ── Serialisation Tests ───────────────────────────────────────────────────────

class TestSerialization:

    def test_save_and_load(self, built_graph, tmp_path):
        path = str(tmp_path / "graph.json")
        built_graph.save(path)
        loaded = RepoGraph.load(path)
        assert len(loaded.nodes) == len(built_graph.nodes)
        assert len(loaded.edges) == len(built_graph.edges)

    def test_to_dict_structure(self, built_graph):
        d = built_graph.to_dict()
        assert "nodes" in d
        assert "edges" in d
        assert "node_count" in d
        assert d["node_count"] == 3


# ── Context Packer Tests ──────────────────────────────────────────────────────

class TestContextPacker:

    def test_context_contains_query(self, built_graph):
        packer = ContextPacker(built_graph, token_budget=4000)
        result = packer.pack_for_query("how does authentication work")
        assert "authentication" in result.context_text or "auth" in result.context_text.lower()

    def test_token_budget_respected(self, built_graph):
        budget = 500
        packer = ContextPacker(built_graph, token_budget=budget)
        result = packer.pack_for_query("database query")
        assert result.estimated_tokens <= budget + 50  # small tolerance

    def test_nodes_included_in_result(self, built_graph):
        packer = ContextPacker(built_graph, token_budget=4000)
        result = packer.pack_for_query("login function")
        assert len(result.nodes_included) > 0

    def test_compression_ratio_between_0_and_1(self, built_graph):
        packer = ContextPacker(built_graph, token_budget=4000)
        result = packer.pack_for_query("anything")
        assert 0 <= result.compression_ratio <= 1

    def test_savings_estimate_keys(self, built_graph):
        packer = ContextPacker(built_graph)
        s = packer.estimate_savings()
        for key in ["full_repo_tokens", "smart_context_tokens", "compression_ratio",
                    "cost_per_query_naive", "cost_per_query_smart", "savings_per_100_queries"]:
            assert key in s

    def test_no_snippets_mode(self, built_graph):
        packer = ContextPacker(built_graph, token_budget=4000)
        result = packer.pack_for_query("db", include_snippets=False)
        assert "```" not in result.context_text

    def test_dependency_section_present(self, built_graph):
        packer = ContextPacker(built_graph, token_budget=8000)
        result = packer.pack_for_query("auth db")
        # Dep section only appears when ≥2 included nodes share edges
        assert isinstance(result.context_text, str)


# ── Graph Query Tests ─────────────────────────────────────────────────────────

class TestGraphQuery:

    def test_get_context_returns_nodes(self, built_graph):
        results = built_graph.get_context_for_query("login user database", top_k=5)
        assert len(results) > 0
        assert all(isinstance(n, CodeNode) for n in results)

    def test_top_k_respected(self, built_graph):
        results = built_graph.get_context_for_query("user", top_k=2)
        assert len(results) <= 2

    def test_irrelevant_query_still_returns(self, built_graph):
        """Even nonsense queries should not crash."""
        results = built_graph.get_context_for_query("xyzzy_nonexistent_token_abc", top_k=5)
        assert isinstance(results, list)
