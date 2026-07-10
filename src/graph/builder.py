"""
RepoGraph - Graph Builder
Parses a GitHub repo into a dependency graph: files as nodes, imports/calls as edges.
This is the core "Caveman" insight: represent code as a graph, not flat text.
"""

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json


@dataclass
class CodeNode:
    """
    Represents a single file in the repo as a graph node.
    Stores metadata + a compressed summary instead of raw code.
    """
    node_id: str           # Unique ID: relative file path
    file_path: str
    language: str
    size_bytes: int
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    summary: str = ""       # LLM-generated or heuristic summary
    chunk_hash: str = ""    # For cache invalidation
    raw_snippet: str = ""   # First 30 lines only — not full file

    def to_dict(self):
        return self.__dict__


@dataclass
class CodeEdge:
    """
    Directed edge: source file imports/calls target file.
    Edge weight = how many times it's referenced (higher = more important).
    """
    source: str
    target: str
    edge_type: str   # "import", "function_call", "inheritance"
    weight: int = 1

    def to_dict(self):
        return self.__dict__


class RepoGraphBuilder:
    """
    Builds a dependency graph from a local repo clone.
    
    Key Concepts Implemented:
    - AST-based parsing (Python) for accurate import extraction
    - Regex fallback for JS/TS/other languages  
    - Node compression: stores signatures, not full source
    - PageRank-style importance scoring
    """

    SUPPORTED_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rb": "ruby",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".cs": "csharp",
    }

    IGNORE_DIRS = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".next", "coverage", ".pytest_cache",
        "vendor", "target", ".gradle"
    }

    def __init__(self, repo_path: str, max_file_size_kb: int = 500):
        self.repo_path = Path(repo_path)
        self.max_file_size_kb = max_file_size_kb
        self.nodes: dict[str, CodeNode] = {}
        self.edges: list[CodeEdge] = []
        self._file_to_module: dict[str, str] = {}  # path -> module name

    def build(self) -> "RepoGraph":
        """Main entry point: scan repo, build nodes, resolve edges."""
        print(f"[RepoGraph] Scanning {self.repo_path}...")
        self._scan_files()
        self._resolve_edges()
        self._compute_importance()
        graph = RepoGraph(
            nodes=self.nodes,
            edges=self.edges,
            repo_path=str(self.repo_path)
        )
        print(f"[RepoGraph] Built graph: {len(self.nodes)} nodes, {len(self.edges)} edges")
        return graph

    def _scan_files(self):
        for root, dirs, files in os.walk(self.repo_path):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
            for fname in files:
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()
                if ext not in self.SUPPORTED_EXTENSIONS:
                    continue
                size = fpath.stat().st_size
                if size > self.max_file_size_kb * 1024:
                    continue  # Skip huge files
                rel_path = fpath.relative_to(self.repo_path).as_posix()
                lang = self.SUPPORTED_EXTENSIONS[ext]
                node = self._parse_file(fpath, rel_path, lang, size)
                if node:
                    self.nodes[rel_path] = node

    def _parse_file(self, fpath: Path, rel_path: str, lang: str, size: int) -> Optional[CodeNode]:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

        node = CodeNode(
            node_id=rel_path,
            file_path=rel_path,
            language=lang,
            size_bytes=size,
            raw_snippet="\n".join(content.splitlines()[:30])  # Only top 30 lines stored
        )

        if lang == "python":
            self._parse_python(content, node)
        else:
            self._parse_generic(content, node, lang)

        # Build module map for edge resolution
        module_name = rel_path.replace("/", ".").replace("\\", ".").removesuffix(f".{fpath.suffix.lstrip('.')}")
        self._file_to_module[module_name] = rel_path

        return node

    def _parse_python(self, content: str, node: CodeNode):
        """Use Python AST for precise extraction — not regex guessing."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            self._parse_generic(content, node, "python")
            return

        for stmt in ast.walk(tree):
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                node.functions.append(stmt.name)
            elif isinstance(stmt, ast.ClassDef):
                node.classes.append(stmt.name)
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    node.imports.append(alias.name)
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.module:
                    node.imports.append(stmt.module)

    def _parse_generic(self, content: str, node: CodeNode, lang: str):
        """Regex-based extraction for non-Python files."""
        patterns = {
            "javascript": [
                r'import\s+.*?\s+from\s+[\'"](.+?)[\'"]',
                r'require\([\'"](.+?)[\'"]\)',
                r'(?:function|const|let|var)\s+(\w+)\s*(?:=\s*(?:async\s+)?(?:function|\()|\()',
                r'class\s+(\w+)',
            ],
            "java": [
                r'import\s+([\w.]+);',
                r'(?:public|private|protected).*?(?:class|interface)\s+(\w+)',
                r'(?:public|private|protected).*?\s+(\w+)\s*\(',
            ],
            "go": [
                r'"([\w./]+)"',  # imports
                r'func\s+(\w+)\s*\(',
                r'type\s+(\w+)\s+struct',
            ],
        }
        lang_patterns = patterns.get(lang, patterns["javascript"])
        
        import_pat = lang_patterns[0]
        for match in re.finditer(import_pat, content):
            node.imports.append(match.group(1))
        
        if len(lang_patterns) > 2:
            for match in re.finditer(lang_patterns[2], content):
                node.functions.append(match.group(1))
        if len(lang_patterns) > 3:
            for match in re.finditer(lang_patterns[3], content):
                node.classes.append(match.group(1))

    def _resolve_edges(self):
        """Match imports to actual nodes in the graph — create edges."""
        path_index = set(self.nodes.keys())
        
        for src_path, node in self.nodes.items():
            src_dir = Path(src_path).parent.as_posix()
            
            for imp in node.imports:
                target = self._resolve_import(imp, src_dir, path_index)
                if target and target != src_path:
                    # Check if edge already exists; if so, increment weight
                    existing = next(
                        (e for e in self.edges if e.source == src_path and e.target == target),
                        None
                    )
                    if existing:
                        existing.weight += 1
                    else:
                        self.edges.append(CodeEdge(
                            source=src_path,
                            target=target,
                            edge_type="import",
                            weight=1
                        ))

    def _resolve_import(self, imp: str, src_dir: str, path_index: set) -> Optional[str]:
        """Try to find which file an import string maps to."""
        # Try relative path variations
        candidates = [
            imp.replace(".", "/") + ".py",
            imp.replace(".", "/") + ".js",
            imp.replace(".", "/") + ".ts",
            imp.replace(".", "/") + "/index.js",
            imp.replace(".", "/") + "/index.ts",
            f"{src_dir}/{imp.replace('.', '/')}.py",
            f"{src_dir}/{imp.replace('.', '/')}.js",
        ]
        for candidate in candidates:
            # Normalize path separators
            normalized = candidate.lstrip("/").replace("\\", "/")
            if normalized in path_index:
                return normalized
        return None

    def _compute_importance(self):
        """
        Simple in-degree centrality as importance score.
        Files imported by many others = high importance.
        This drives smart context selection: prioritize high-importance nodes.
        """
        in_degree: dict[str, int] = {k: 0 for k in self.nodes}
        for edge in self.edges:
            if edge.target in in_degree:
                in_degree[edge.target] += edge.weight

        max_degree = max(in_degree.values(), default=1) or 1
        for path, node in self.nodes.items():
            score = in_degree.get(path, 0) / max_degree
            node.summary = f"[importance={score:.2f}] " + node.summary


class RepoGraph:
    """
    The final graph object. Supports serialization and smart context queries.
    """

    def __init__(self, nodes: dict, edges: list, repo_path: str):
        self.nodes = nodes
        self.edges = edges
        self.repo_path = repo_path

    def get_context_for_query(self, query: str, top_k: int = 10) -> list[CodeNode]:
        """
        Given a natural language query, return the most relevant nodes.
        Uses keyword matching + graph traversal (BFS from matched nodes).
        This is the core cost-saving mechanism.
        """
        query_terms = set(query.lower().split())
        scored = []

        for path, node in self.nodes.items():
            score = 0
            searchable = (
                path.lower() + " " +
                " ".join(node.functions).lower() + " " +
                " ".join(node.classes).lower() + " " +
                node.raw_snippet.lower()
            )
            for term in query_terms:
                score += searchable.count(term)
            if score > 0:
                scored.append((score, node))

        scored.sort(key=lambda x: -x[0])
        seed_nodes = [n for _, n in scored[:5]]

        # BFS: expand to neighbors of top matches
        visited = set(n.node_id for n in seed_nodes)
        queue = list(seed_nodes)
        result = list(seed_nodes)

        adj: dict[str, list[str]] = {}
        for edge in self.edges:
            adj.setdefault(edge.source, []).append(edge.target)
            adj.setdefault(edge.target, []).append(edge.source)

        while queue and len(result) < top_k:
            current = queue.pop(0)
            for neighbor_id in adj.get(current.node_id, []):
                if neighbor_id not in visited and neighbor_id in self.nodes:
                    visited.add(neighbor_id)
                    neighbor = self.nodes[neighbor_id]
                    result.append(neighbor)
                    queue.append(neighbor)
                    if len(result) >= top_k:
                        break

        return result[:top_k]

    def to_dict(self) -> dict:
        return {
            "repo_path": self.repo_path,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
        }

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        print(f"[RepoGraph] Saved graph to {path}")

    @classmethod
    def load(cls, path: str) -> "RepoGraph":
        with open(path) as f:
            data = json.load(f)
        nodes = {k: CodeNode(**v) for k, v in data["nodes"].items()}
        edges = [CodeEdge(**e) for e in data["edges"]]
        return cls(nodes=nodes, edges=edges, repo_path=data["repo_path"])
