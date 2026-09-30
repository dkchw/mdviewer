"""
High-performance Rust accelerator wrapper for mdviewer.
Communicates with `mdviewer_core` native binary for SIMD/Rayon multi-threaded
indexing, parsing, full-text searching, markdown rendering, and folder imports.
Falls back seamlessly to pure Python when the native binary is not available.
"""

import os
import sys
import json
import shutil
import subprocess
from typing import Dict, Any, Optional, List

RUST_BIN_NAME = "mdviewer_core"

def find_rust_binary() -> Optional[str]:
    """Find the compiled mdviewer_core native binary."""
    # 1. Bundled in package
    pkg_dir = os.path.dirname(__file__)
    cand1 = os.path.join(pkg_dir, "bin", RUST_BIN_NAME)
    if os.path.isfile(cand1) and os.access(cand1, os.X_OK):
        return cand1

    # 2. Cargo target directory in workspace
    repo_root = os.path.abspath(os.path.join(pkg_dir, "..", ".."))
    cand2 = os.path.join(repo_root, "crates", "mdviewer_core", "target", "release", RUST_BIN_NAME)
    if os.path.isfile(cand2) and os.access(cand2, os.X_OK):
        return cand2

    # 3. System PATH
    cand3 = shutil.which(RUST_BIN_NAME)
    if cand3 and os.access(cand3, os.X_OK):
        return cand3

    return None

def is_rust_available() -> bool:
    return find_rust_binary() is not None

def get_rust_info() -> Dict[str, Any]:
    bin_path = find_rust_binary()
    if not bin_path:
        return {"available": False, "engine": "Pure Python (Standard)"}
    try:
        proc = subprocess.run([bin_path, "version"], capture_output=True, text=True, timeout=2)
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            data["available"] = True
            data["binary_path"] = bin_path
            return data
    except Exception:
        pass
    return {"available": True, "engine": "Rust mdviewer_core", "binary_path": bin_path}

def rust_index_library(library_dir: str) -> Optional[Dict[str, Any]]:
    """Index an entire library in parallel with Rayon in Rust."""
    bin_path = find_rust_binary()
    if not bin_path:
        return None
    try:
        proc = subprocess.run([bin_path, "index", library_dir], capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception as e:
        sys.stderr.write(f"Rust index_library error: {e}\n")
    return None

def rust_parse_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Parse a markdown file into headings and flashcards in Rust."""
    bin_path = find_rust_binary()
    if not bin_path:
        return None
    try:
        proc = subprocess.run([bin_path, "parse", file_path], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception as e:
        sys.stderr.write(f"Rust parse_file error: {e}\n")
    return None

def rust_render_markdown(content_or_path: str) -> Optional[Dict[str, Any]]:
    """Render markdown using pulldown-cmark in Rust."""
    bin_path = find_rust_binary()
    if not bin_path:
        return None
    try:
        if len(content_or_path) < 4096 and os.path.exists(content_or_path) and os.path.isfile(content_or_path):
            proc = subprocess.run([bin_path, "render", content_or_path], capture_output=True, text=True, timeout=30)
        else:
            proc = subprocess.run([bin_path, "render"], input=content_or_path, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception as e:
        sys.stderr.write(f"Rust render_markdown error: {e}\n")
    return None

def rust_search_library(library_dir: str, query: str) -> Optional[Dict[str, Any]]:
    """Parallel full-text search across library using Rayon in Rust."""
    bin_path = find_rust_binary()
    if not bin_path:
        return None
    try:
        proc = subprocess.run([bin_path, "search", library_dir, query], capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception as e:
        sys.stderr.write(f"Rust search_library error: {e}\n")
    return None

def rust_import_folder(src_dir: str, dst_dir: str) -> Optional[Dict[str, Any]]:
    """Parallel folder import into library in Rust."""
    bin_path = find_rust_binary()
    if not bin_path:
        return None
    try:
        proc = subprocess.run([bin_path, "import-folder", src_dir, dst_dir], capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception as e:
        sys.stderr.write(f"Rust import_folder error: {e}\n")
    return None

def rust_tree(dir_path: str) -> Optional[Dict[str, Any]]:
    """Ultra-fast directory scanning in Rust."""
    bin_path = find_rust_binary()
    if not bin_path:
        return None
    try:
        proc = subprocess.run([bin_path, "tree", dir_path], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception as e:
        sys.stderr.write(f"Rust tree error: {e}\n")
    return None

def rust_file_meta(file_path: str) -> Optional[Dict[str, Any]]:
    """Fast line count and massive file detection in Rust."""
    bin_path = find_rust_binary()
    if not bin_path:
        return None
    try:
        proc = subprocess.run([bin_path, "meta", file_path], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception as e:
        sys.stderr.write(f"Rust file_meta error: {e}\n")
    return None

def rust_read_chunk(file_path: str, start_line: int = 1, count: int = 1000) -> Optional[Dict[str, Any]]:
    """Streamed chunk reader in Rust (reads range of lines without memory blowup)."""
    bin_path = find_rust_binary()
    if not bin_path:
        return None
    try:
        proc = subprocess.run([bin_path, "chunk", file_path, str(start_line), str(count)], capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception as e:
        sys.stderr.write(f"Rust read_chunk error: {e}\n")
    return None

def rust_count_directory(dir_path: str) -> Optional[Dict[str, Any]]:
    """Parallel counting of markdown files and assets in Rust."""
    bin_path = find_rust_binary()
    if not bin_path:
        return None
    try:
        proc = subprocess.run([bin_path, "count", dir_path], capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception as e:
        sys.stderr.write(f"Rust count error: {e}\n")
    return None
