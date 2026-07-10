"""
RepoGraph - GitHub Fetcher
Clones or fetches a GitHub repo for analysis.
Supports public repos without auth, private repos with token.
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


class GitHubFetcher:
    """
    Fetches a GitHub repository to a local temp directory.
    
    Concepts implemented:
    - Shallow clone (--depth=1) to minimize bandwidth
    - Sparse checkout for large repos
    - Cleanup context manager
    """

    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self._temp_dirs: list[str] = []

    def fetch(self, repo_url: str, branch: str = "main") -> str:
        """
        Clone repo to temp dir. Returns path to cloned repo.
        Caller is responsible for cleanup (or use as context manager).
        """
        repo_url = self._normalize_url(repo_url)
        temp_dir = tempfile.mkdtemp(prefix="repograph_")
        self._temp_dirs.append(temp_dir)

        print(f"[Fetcher] Cloning {repo_url} (shallow)...")
        
        cmd = ["git", "clone", "--depth=1", "--single-branch"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [repo_url, temp_dir]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode != 0:
                # Try without branch specification (maybe branch doesn't exist)
                cmd_fallback = ["git", "clone", "--depth=1", repo_url, temp_dir]
                result = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    raise RuntimeError(f"Clone failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Repo clone timed out (>2 min). Try a smaller repo.")

        print(f"[Fetcher] Cloned to {temp_dir}")
        return temp_dir

    def _normalize_url(self, url: str) -> str:
        """Convert various GitHub URL formats to clonable HTTPS URL."""
        url = url.strip().rstrip("/")
        
        # Already a git URL
        if url.endswith(".git"):
            return url
        
        # github.com/user/repo format
        if "github.com" in url and not url.startswith("http"):
            url = "https://" + url
        
        # Inject token for private repos
        if self.github_token and "github.com" in url:
            parsed = urlparse(url)
            url = f"https://{self.github_token}@github.com{parsed.path}"
        
        return url

    def cleanup(self):
        """Remove all cloned temp directories."""
        for d in self._temp_dirs:
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)
        self._temp_dirs.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()
