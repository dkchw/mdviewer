import http.server
import socketserver
import json
import os
import urllib.parse
import webbrowser
import threading
import sys
import importlib.resources
import subprocess
import shutil
import shlex
import re

import difflib
import hashlib
import sqlite3
import time
import urllib.request
import urllib.error
import socket
import random
import concurrent.futures
import collections

def safe_rel_path(directory, rel_path):
    if not rel_path or rel_path == '.':
        return os.path.abspath(directory)
    rel_clean = rel_path.lstrip('/\\').replace('\\', '/')
    target = os.path.abspath(os.path.join(directory, rel_clean))
    dir_abs = os.path.abspath(directory)
    try:
        if os.path.commonpath([dir_abs, target]) != dir_abs:
            return None
    except ValueError:
        return None
    if os.path.exists(target):
        try:
            real_target = os.path.realpath(target)
            real_dir = os.path.realpath(directory)
            if os.path.commonpath([real_dir, real_target]) != real_dir:
                return None
        except Exception:
            return None
    return target

def get_buffer_base_dir(directory):
    ws_hash = hashlib.sha256(os.path.abspath(directory).encode('utf-8')).hexdigest()[:16]
    base_dir = os.path.abspath(os.path.join(os.path.expanduser("~/.mdviewer_buffers"), ws_hash))
    os.makedirs(base_dir, exist_ok=True)
    return base_dir

def get_buffer_file_path(directory, rel_path):
    target = safe_rel_path(directory, rel_path)
    if not target:
        return None
    base_dir = get_buffer_base_dir(directory)
    rel_clean = os.path.relpath(target, os.path.abspath(directory))
    buf_target = os.path.abspath(os.path.join(base_dir, rel_clean))
    if not buf_target.startswith(base_dir):
        return None
    return buf_target

def get_buffer_info(directory, rel_path):
    orig_target = safe_rel_path(directory, rel_path)
    if not orig_target or os.path.isdir(orig_target):
        return None
    buf_path = get_buffer_file_path(directory, rel_path)
    if not buf_path:
        return None

    orig_content = ""
    if os.path.exists(orig_target):
        try:
            with open(orig_target, 'r', encoding='utf-8', errors='replace') as f:
                orig_content = f.read()
        except Exception:
            pass

    has_buffer = os.path.exists(buf_path)
    buf_content = orig_content
    if has_buffer:
        try:
            with open(buf_path, 'r', encoding='utf-8', errors='replace') as f:
                buf_content = f.read()
        except Exception:
            pass

    diff_lines = list(difflib.unified_diff(
        orig_content.splitlines(keepends=True),
        buf_content.splitlines(keepends=True),
        fromfile=f"original/{rel_path}",
        tofile=f"buffer/{rel_path}"
    ))
    diff_text = "".join(diff_lines)
    is_dirty = (orig_content != buf_content)

    return {
        "path": rel_path,
        "has_buffer": has_buffer,
        "is_dirty": is_dirty,
        "content": buf_content,
        "original_content": orig_content,
        "diff": diff_text
    }

def save_buffer_content(directory, rel_path, content):
    orig_target = safe_rel_path(directory, rel_path)
    if not orig_target:
        raise ValueError("Security violation: path escapes workspace")
    buf_path = get_buffer_file_path(directory, rel_path)
    if not buf_path:
        raise ValueError("Invalid buffer destination")
    os.makedirs(os.path.dirname(buf_path), exist_ok=True)
    with open(buf_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return get_buffer_info(directory, rel_path)

def accept_buffer(directory, rel_path):
    orig_target = safe_rel_path(directory, rel_path)
    if not orig_target:
        raise ValueError("Security violation: path escapes workspace")
    buf_path = get_buffer_file_path(directory, rel_path)
    if not buf_path or not os.path.exists(buf_path):
        raise ValueError(f"No active staging buffer found for: {rel_path}")

    with open(buf_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    os.makedirs(os.path.dirname(orig_target), exist_ok=True)
    with open(orig_target, 'w', encoding='utf-8') as f:
        f.write(content)

    try:
        os.remove(buf_path)
    except Exception:
        pass
    return {"status": "ok", "path": rel_path, "message": f"Buffer changes accepted and written to original file: {rel_path}"}

def discard_buffer(directory, rel_path):
    buf_path = get_buffer_file_path(directory, rel_path)
    if buf_path and os.path.exists(buf_path):
        os.remove(buf_path)
    return {"status": "ok", "path": rel_path, "message": f"Staging buffer discarded for: {rel_path}"}

def list_all_buffers(directory):
    base_dir = get_buffer_base_dir(directory)
    active = []
    if not os.path.exists(base_dir):
        return active
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            buf_file = os.path.join(root, file)
            rel_path = os.path.relpath(buf_file, base_dir).replace('\\', '/')
            info = get_buffer_info(directory, rel_path)
            if info:
                active.append({
                    "path": rel_path,
                    "is_dirty": info["is_dirty"],
                    "has_diff": bool(info["diff"].strip()),
                    "diff": info["diff"]
                })
    return active

DEFAULT_PROMPTS = [
    {
        "id": "detailed",
        "name": "Detailed Explanation & Examples",
        "system_prompt": "You are an expert tutor. Provide a clear, detailed explanation of the flashcard concepts, with rich contextual real-world examples, nuanced explanations, and common pitfalls to avoid. Format your output with clean, readable Markdown (headings, bullet points, bold key terms).",
        "send_scope": "both",
        "rank": 0
    },
    {
        "id": "vocab",
        "name": "Vocabulary & Collocations",
        "system_prompt": "You are a linguistic expert. Analyze the vocabulary, expressions, idioms, and grammatical structures in this flashcard. Provide definitions, collocations, sample usage sentences, synonyms, and antonyms in clean Markdown.",
        "send_scope": "both",
        "rank": 1
    },
    {
        "id": "mnemonic",
        "name": "Mnemonic & Memory Hooks",
        "system_prompt": "You are a memory specialist. Create vivid, memorable mnemonics, imagery associations, etymology, and mental hooks to remember this flashcard term/concept easily.",
        "send_scope": "front",
        "rank": 2
    },
    {
        "id": "quiz",
        "name": "Active Recall & Quiz Questions",
        "system_prompt": "You are a learning coach. Generate 3 active recall questions ranging from basic understanding to deep application, followed by concise model answers in an expandable/spoiler format.",
        "send_scope": "both",
        "rank": 3
    }
]

def get_supplement_db_path(directory):
    ws_hash = hashlib.sha256(os.path.abspath(directory).encode('utf-8')).hexdigest()[:16]
    base_dir = os.path.abspath(os.path.join(os.path.expanduser("~/.mdviewer_supplements"), ws_hash))
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "flashcards.db")

def get_db_connection(directory):
    db_path = get_supplement_db_path(directory)
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_supplement_db(directory):
    db_path = get_supplement_db_path(directory)
    conn = get_db_connection(directory)
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='card_supplements'")
            tbl_exists = cur.fetchone() is not None
            if tbl_exists:
                cur.execute("PRAGMA table_info(card_supplements)")
                cols = [r[1] for r in cur.fetchall()]
                needs_migration = ("provider" not in cols) or ("version" not in cols)
                if needs_migration:
                    conn.execute("""
                    CREATE TABLE card_supplements_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path TEXT NOT NULL,
                        heading_slug TEXT NOT NULL,
                        heading_level INTEGER NOT NULL,
                        heading_text TEXT NOT NULL,
                        breadcrumb TEXT DEFAULT '',
                        prompt_id TEXT NOT NULL,
                        prompt_name TEXT DEFAULT '',
                        provider TEXT DEFAULT 'openrouter',
                        model TEXT NOT NULL,
                        content TEXT NOT NULL,
                        raw_front TEXT DEFAULT '',
                        raw_back TEXT DEFAULT '',
                        liked INTEGER DEFAULT 0,
                        version INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(file_path, heading_slug, prompt_id, provider, version)
                    );
                    """)
                    has_ver = "version" in cols
                    has_prov = "provider" in cols
                    prov_expr = "provider" if has_prov else "CASE WHEN model LIKE '%ollama%' OR model LIKE '%localhost%' THEN 'ollama' ELSE 'openrouter' END"
                    ver_expr = "version" if has_ver else "1"
                    conn.execute(f"""
                    INSERT OR REPLACE INTO card_supplements_new (
                        id, file_path, heading_slug, heading_level, heading_text, breadcrumb,
                        prompt_id, prompt_name, provider, model, content, raw_front, raw_back, liked, version, created_at, updated_at
                    )
                    SELECT
                        id, file_path, heading_slug, heading_level, heading_text, breadcrumb,
                        prompt_id, prompt_name, {prov_expr}, model, content, raw_front, raw_back, liked, {ver_expr}, created_at, updated_at
                    FROM card_supplements;
                    """)
                    conn.execute("DROP TABLE card_supplements;")
                    conn.execute("ALTER TABLE card_supplements_new RENAME TO card_supplements;")
            else:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS card_supplements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    heading_slug TEXT NOT NULL,
                    heading_level INTEGER NOT NULL,
                    heading_text TEXT NOT NULL,
                    breadcrumb TEXT DEFAULT '',
                    prompt_id TEXT NOT NULL,
                    prompt_name TEXT DEFAULT '',
                    provider TEXT DEFAULT 'openrouter',
                    model TEXT NOT NULL,
                    content TEXT NOT NULL,
                    raw_front TEXT DEFAULT '',
                    raw_back TEXT DEFAULT '',
                    liked INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(file_path, heading_slug, prompt_id, provider, version)
                );
                """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_supp_lookup ON card_supplements(file_path, heading_slug);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_supp_provider ON card_supplements(provider);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_supp_prov_lookup ON card_supplements(file_path, heading_slug, provider);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_supp_file ON card_supplements(file_path);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_supp_liked ON card_supplements(liked);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_supp_ver ON card_supplements(file_path, heading_slug, prompt_id, provider, version);")
            conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                send_scope TEXT NOT NULL DEFAULT 'both',
                rank INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """)
            
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM prompt_templates")
            if cur.fetchone()[0] == 0:
                for p in DEFAULT_PROMPTS:
                    cur.execute(
                        "INSERT INTO prompt_templates (id, name, system_prompt, send_scope, rank) VALUES (?, ?, ?, ?, ?)",
                        (p["id"], p["name"], p["system_prompt"], p["send_scope"], p["rank"])
                    )

            default_settings = {
                "provider": "openrouter",
                "model": "deepseek/deepseek-v4-flash-0731",
                "openrouter_model": "deepseek/deepseek-v4-flash-0731",
                "ollama_host": "http://localhost:11434",
                "ollama_model": "huggingface.co/LiquidAI/LFM2.5-8B-A1B-GGUF:latest",
                "batch_size": "10",
                "max_concurrency": "1000",
                "auto_next_batch": "false",
                "batch_auto_next": "false",
                "trigger_type": "threshold",
                "trigger_threshold": "5",
                "trigger_percentage": "80"
            }
            for k, v in default_settings.items():
                cur.execute("INSERT OR IGNORE INTO ai_settings (key, value) VALUES (?, ?)", (k, v))
            cur.execute("UPDATE ai_settings SET value = 'deepseek/deepseek-v4-flash-0731' WHERE key = 'model' AND value IN ('~deepseek/deepseek-flash-latest', 'deepseek/deepseek-flash-latest')")
            cur.execute("""
                UPDATE ai_settings 
                SET value = 'false' 
                WHERE key IN ('auto_next_batch', 'batch_auto_next') 
                  AND value IN ('true', 'True', '1')
                  AND NOT EXISTS (SELECT 1 FROM ai_settings WHERE key = 'auto_next_explicit' AND value = 'true')
            """)
    finally:
        conn.close()
    return db_path

def get_card_supplements(directory, file_path=None, heading_slug=None, prompt_id=None, version=None, folder_path=None, heading_level=None, search=None, limit=None, offset=None, provider=None):
    init_supplement_db(directory)
    conn = get_db_connection(directory)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cols = "id, file_path, heading_slug, heading_level, heading_text, breadcrumb, prompt_id, prompt_name, provider, model, content, liked, version, created_at, updated_at"
        query = f"SELECT {cols} FROM card_supplements WHERE 1=1"
        params = []
        if provider and provider != 'all':
            query += " AND provider = ?"
            params.append(provider)
        if file_path:
            query += " AND file_path = ?"
            params.append(file_path)
        elif folder_path:
            clean_folder = folder_path.strip().strip('/')
            if clean_folder:
                query += " AND (file_path = ? OR file_path LIKE ?)"
                params.extend([clean_folder, clean_folder + '/%'])
        if heading_slug:
            m = re.match(r'^H\d+::(.*)', heading_slug)
            if m:
                clean_text = m.group(1).strip()
                query += " AND (heading_slug = ? OR TRIM(LOWER(heading_text)) = ?)"
                params.extend([heading_slug, clean_text.lower()])
            else:
                query += " AND heading_slug = ?"
                params.append(heading_slug)
        if heading_level is not None and str(heading_level).strip() not in ('all', '', 'none', 'None'):
            query += " AND heading_level = ?"
            params.append(int(heading_level))
        if prompt_id and prompt_id != 'all':
            query += " AND prompt_id = ?"
            params.append(prompt_id)
        if version is not None:
            query += " AND version = ?"
            params.append(int(version))
        if search:
            query += " AND (heading_text LIKE ? OR content LIKE ? OR breadcrumb LIKE ?)"
            s_param = f"%{search}%"
            params.extend([s_param, s_param, s_param])
        query += " ORDER BY updated_at DESC, version DESC"
        if limit is not None and int(limit) > 0:
            query += " LIMIT ?"
            params.append(int(limit))
            if offset is not None and int(offset) > 0:
                query += " OFFSET ?"
                params.append(int(offset))
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

db_write_lock = threading.Lock()

def save_card_supplement(directory, file_path, heading_slug, heading_level, heading_text, breadcrumb, prompt_id, prompt_name, model, content, raw_front='', raw_back='', liked=0, version=None, create_new_version=False, provider='openrouter'):
    with db_write_lock:
        init_supplement_db(directory)
        conn = get_db_connection(directory)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                cur = conn.cursor()
                prov = (provider or 'openrouter').strip().lower()
                cur.execute("SELECT MAX(version) FROM card_supplements WHERE file_path = ? AND heading_slug = ? AND prompt_id = ? AND provider = ?", (file_path, heading_slug, prompt_id, prov))
                row = cur.fetchone()
                max_v = row[0] if (row and row[0] is not None) else 0

                if create_new_version:
                    v = max_v + 1
                elif version is not None:
                    v = int(version)
                else:
                    v = max_v if max_v > 0 else 1

                cur.execute("""
                INSERT INTO card_supplements (
                    file_path, heading_slug, heading_level, heading_text, breadcrumb,
                    prompt_id, prompt_name, provider, model, content, raw_front, raw_back, liked, version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(file_path, heading_slug, prompt_id, provider, version) DO UPDATE SET
                    heading_level = excluded.heading_level,
                    heading_text = excluded.heading_text,
                    breadcrumb = excluded.breadcrumb,
                    prompt_name = excluded.prompt_name,
                    model = excluded.model,
                    content = excluded.content,
                    raw_front = excluded.raw_front,
                    raw_back = excluded.raw_back,
                    liked = CASE WHEN excluded.liked IS NOT NULL AND excluded.liked != 0 THEN excluded.liked ELSE card_supplements.liked END,
                    updated_at = CURRENT_TIMESTAMP;
                """, (file_path, heading_slug, heading_level, heading_text, breadcrumb, prompt_id, prompt_name, prov, model, content, raw_front, raw_back, liked, v))
                cur.execute("SELECT * FROM card_supplements WHERE file_path = ? AND heading_slug = ? AND prompt_id = ? AND provider = ? AND version = ?", (file_path, heading_slug, prompt_id, prov, v))
                row = cur.fetchone()
                return dict(row) if row else {}
        finally:
            conn.close()

def delete_card_supplement(directory, file_path=None, heading_slug=None, prompt_id=None, version=None, supplement_id=None, provider=None):
    init_supplement_db(directory)
    conn = get_db_connection(directory)
    try:
        with conn:
            cur = conn.cursor()
            if supplement_id is not None:
                cur.execute("DELETE FROM card_supplements WHERE id = ?", (int(supplement_id),))
                return True
            if not file_path or not heading_slug:
                return False
            query = "DELETE FROM card_supplements WHERE file_path = ? AND heading_slug = ?"
            params = [file_path, heading_slug]
            if provider and provider != 'all':
                query += " AND provider = ?"
                params.append(provider)
            if prompt_id:
                query += " AND prompt_id = ?"
                params.append(prompt_id)
            if version is not None:
                query += " AND version = ?"
                params.append(int(version))
            cur.execute(query, params)
            return True
    finally:
        conn.close()

def toggle_card_like(directory, file_path, heading_slug, prompt_id=None, version=None, provider=None):
    init_supplement_db(directory)
    conn = get_db_connection(directory)
    try:
        with conn:
            cur = conn.cursor()
            prov_clause = " AND provider = ?" if (provider and provider != 'all') else ""
            prov_params = [provider] if (provider and provider != 'all') else []
            if prompt_id and version is not None:
                cur.execute(f"UPDATE card_supplements SET liked = 1 - liked WHERE file_path = ? AND heading_slug = ? AND prompt_id = ? AND version = ?{prov_clause}", [file_path, heading_slug, prompt_id, int(version)] + prov_params)
                cur.execute(f"SELECT liked FROM card_supplements WHERE file_path = ? AND heading_slug = ? AND prompt_id = ? AND version = ?{prov_clause}", [file_path, heading_slug, prompt_id, int(version)] + prov_params)
            elif prompt_id:
                cur.execute(f"UPDATE card_supplements SET liked = 1 - liked WHERE file_path = ? AND heading_slug = ? AND prompt_id = ?{prov_clause}", [file_path, heading_slug, prompt_id] + prov_params)
                cur.execute(f"SELECT MAX(liked) FROM card_supplements WHERE file_path = ? AND heading_slug = ? AND prompt_id = ?{prov_clause}", [file_path, heading_slug, prompt_id] + prov_params)
            else:
                cur.execute(f"UPDATE card_supplements SET liked = 1 - liked WHERE file_path = ? AND heading_slug = ?{prov_clause}", [file_path, heading_slug] + prov_params)
                cur.execute(f"SELECT MAX(liked) FROM card_supplements WHERE file_path = ? AND heading_slug = ?{prov_clause}", [file_path, heading_slug] + prov_params)
            row = cur.fetchone()
            return bool(row[0]) if row and row[0] is not None else False
    finally:
        conn.close()

def get_workspace_supplements_summary(directory):
    db_path = get_supplement_db_path(directory)
    if not os.path.exists(db_path):
        return {}
    conn = get_db_connection(directory)
    try:
        cur = conn.cursor()
        cur.execute("""
        SELECT file_path, COUNT(DISTINCT heading_slug) as count, SUM(liked) as liked_count, MAX(updated_at) as last_updated,
               GROUP_CONCAT(DISTINCT provider) as providers
        FROM card_supplements
        GROUP BY file_path
        """)
        summary = {}
        for row in cur.fetchall():
            summary[row[0]] = {
                "count": row[1],
                "liked_count": row[2] or 0,
                "last_updated": row[3],
                "providers": (row[4] or "").split(',')
            }
        return summary
    finally:
        conn.close()

def get_file_saved_cards(directory, file_path, provider=None):
    db_path = get_supplement_db_path(directory)
    if not os.path.exists(db_path):
        return []
    conn = get_db_connection(directory)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        prov_clause = " AND provider = ?" if (provider and provider != 'all') else ""
        prov_params = [provider] if (provider and provider != 'all') else []
        cur.execute(f"""
        SELECT heading_slug, heading_level, heading_text, breadcrumb, MAX(liked) as liked,
               COUNT(DISTINCT prompt_id) as prompts_count, COUNT(id) as total_versions, MAX(updated_at) as last_updated,
               GROUP_CONCAT(DISTINCT provider) as providers
        FROM card_supplements
        WHERE file_path = ? {prov_clause}
        GROUP BY heading_slug
        ORDER BY heading_level, heading_text
        """, [file_path] + prov_params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def get_folder_saved_cards(directory, folder_path="", provider=None):
    db_path = get_supplement_db_path(directory)
    if not os.path.exists(db_path):
        return []
    conn = get_db_connection(directory)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        clean_folder = folder_path.strip().strip('/')
        prov_clause = " AND provider = ?" if (provider and provider != 'all') else ""
        prov_params = [provider] if (provider and provider != 'all') else []
        if clean_folder:
            pattern = clean_folder + '/%'
            cur.execute(f"""
            SELECT file_path, heading_slug, heading_level, heading_text, breadcrumb, MAX(liked) as liked,
                   COUNT(DISTINCT prompt_id) as prompts_count, COUNT(id) as total_versions, MAX(updated_at) as last_updated,
                   GROUP_CONCAT(DISTINCT provider) as providers
            FROM card_supplements
            WHERE (file_path = ? OR file_path LIKE ?) {prov_clause}
            GROUP BY file_path, heading_slug
            ORDER BY file_path, heading_level
            """, [clean_folder, pattern] + prov_params)
        else:
            cur.execute(f"""
            SELECT file_path, heading_slug, heading_level, heading_text, breadcrumb, MAX(liked) as liked,
                   COUNT(DISTINCT prompt_id) as prompts_count, COUNT(id) as total_versions, MAX(updated_at) as last_updated,
                   GROUP_CONCAT(DISTINCT provider) as providers
            FROM card_supplements
            WHERE 1=1 {prov_clause}
            GROUP BY file_path, heading_slug
            ORDER BY file_path, heading_level
            """, prov_params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def get_prompts(directory):
    init_supplement_db(directory)
    conn = get_db_connection(directory)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, system_prompt, send_scope, rank FROM prompt_templates ORDER BY rank ASC, updated_at ASC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def save_prompts(directory, prompts):
    init_supplement_db(directory)
    conn = get_db_connection(directory)
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM prompt_templates")
            for idx, p in enumerate(prompts):
                pid = p.get("id") or f"prompt_{idx}_{int(os.times().system*1000)}"
                cur.execute(
                    "INSERT INTO prompt_templates (id, name, system_prompt, send_scope, rank) VALUES (?, ?, ?, ?, ?)",
                    (pid, p.get("name", "Untitled Prompt"), p.get("system_prompt", ""), p.get("send_scope", "both"), idx)
                )
        return get_prompts(directory)
    finally:
        conn.close()

def get_ai_settings(directory):
    init_supplement_db(directory)
    conn = get_db_connection(directory)
    try:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM ai_settings")
        res = {k: v for k, v in cur.fetchall()}
        if "model" not in res or not res["model"]:
            res["model"] = "deepseek/deepseek-v4-flash-0731"
        elif res["model"] in ("~deepseek/deepseek-flash-latest", "deepseek/deepseek-flash-latest"):
            res["model"] = "deepseek/deepseek-v4-flash-0731"
        
        # Ensure auto-generation defaults to 'false'
        auto_val = res.get("batch_auto_next") or res.get("auto_next_batch") or "false"
        res["auto_next_batch"] = auto_val
        res["batch_auto_next"] = auto_val
        return res
    finally:
        conn.close()

def save_ai_settings(directory, settings):
    init_supplement_db(directory)
    conn = get_db_connection(directory)
    try:
        with conn:
            cur = conn.cursor()
            for k, v in settings.items():
                cur.execute("INSERT INTO ai_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
                if k in ('auto_next_batch', 'batch_auto_next'):
                    cur.execute("INSERT INTO ai_settings (key, value) VALUES ('auto_next_explicit', 'true') ON CONFLICT(key) DO UPDATE SET value='true'")
        return get_ai_settings(directory)
    finally:
        conn.close()

def cleanup_supplements(directory, scope='all', file_path=None, heading_slug=None, ids=None, valid_slugs=None, valid_texts=None, provider=None):
    db_path = get_supplement_db_path(directory)
    if not os.path.exists(db_path):
        return {"status": "ok", "deleted": 0}
    conn = get_db_connection(directory)
    try:
        with conn:
            cur = conn.cursor()
            prov_clause = " AND provider = ?" if (provider and provider != 'all') else ""
            prov_params = [provider] if (provider and provider != 'all') else []

            if scope == 'card' and file_path and heading_slug:
                cur.execute(f"DELETE FROM card_supplements WHERE file_path = ? AND heading_slug = ?{prov_clause}", [file_path, heading_slug] + prov_params)
            elif scope == 'file' and file_path:
                cur.execute(f"DELETE FROM card_supplements WHERE file_path = ?{prov_clause}", [file_path] + prov_params)
            elif scope in ('duplicates', 'prune_versions'):
                if file_path:
                    cur.execute(f"""
                        DELETE FROM card_supplements
                        WHERE file_path = ? {prov_clause} AND id NOT IN (
                            SELECT MAX(id)
                            FROM card_supplements
                            WHERE file_path = ? {prov_clause}
                            GROUP BY provider, prompt_id, COALESCE(NULLIF(TRIM(LOWER(heading_text)), ''), heading_slug)
                        )
                    """, [file_path] + prov_params + [file_path] + prov_params)
                else:
                    cur.execute(f"""
                        DELETE FROM card_supplements
                        WHERE 1=1 {prov_clause} AND id NOT IN (
                            SELECT MAX(id)
                            FROM card_supplements
                            WHERE 1=1 {prov_clause}
                            GROUP BY file_path, provider, prompt_id, COALESCE(NULLIF(TRIM(LOWER(heading_text)), ''), heading_slug)
                        )
                    """, prov_params + prov_params)
            elif scope == 'orphans' and file_path:
                s_list = list(valid_slugs) if valid_slugs else []
                t_list = [t.strip().lower() for t in valid_texts if t.strip()] if valid_texts else []
                if s_list or t_list:
                    conds = []
                    params = [file_path] + prov_params
                    if s_list:
                        placeholders = ','.join(['?'] * len(s_list))
                        conds.append(f"heading_slug NOT IN ({placeholders})")
                        params.extend(s_list)
                    if t_list:
                        placeholders = ','.join(['?'] * len(t_list))
                        conds.append(f"TRIM(LOWER(heading_text)) NOT IN ({placeholders})")
                        params.extend(t_list)
                    cur.execute(f"DELETE FROM card_supplements WHERE file_path = ? {prov_clause} AND ({' AND '.join(conds)})", params)
                else:
                    cur.execute(f"DELETE FROM card_supplements WHERE file_path = ?{prov_clause}", [file_path] + prov_params)
            elif scope in ('ids', 'selected') and ids:
                clean_ids = [int(x) for x in ids if str(x).isdigit()]
                if clean_ids:
                    placeholders = ','.join(['?'] * len(clean_ids))
                    cur.execute(f"DELETE FROM card_supplements WHERE id IN ({placeholders})", clean_ids)
            else:
                cur.execute(f"DELETE FROM card_supplements WHERE 1=1 {prov_clause}", prov_params)
            deleted = cur.rowcount
        conn.isolation_level = None
        conn.execute("VACUUM")
        return {"status": "ok", "deleted": deleted, "scope": scope}
    finally:
        conn.close()

def export_supplements_markdown(directory, file_path):
    rows = get_card_supplements(directory, file_path)
    if not rows:
        return f"# AI Supplements for {file_path}\n\n*No supplements found.*"
    
    lines = [f"# AI Flashcard Supplements: {file_path}", f"> Exported from MDViewer on {rows[0]['updated_at']}", ""]
    headings_map = {}
    for r in rows:
        slug = r["heading_slug"]
        if slug not in headings_map:
            headings_map[slug] = []
        headings_map[slug].append(r)
    
    for slug, cards in headings_map.items():
        first = cards[0]
        prefix = "#" * max(1, min(6, first["heading_level"]))
        lines.append(f"{prefix} {first['heading_text']}")
        if first["breadcrumb"]:
            lines.append(f"*Breadcrumb: {first['breadcrumb']}*")
        lines.append("")
        for c in cards:
            lines.append(f"### ✨ {c['prompt_name']} (`{c['model']}`)")
            lines.append(c["content"])
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)

def collect_folder_flashcards(directory, folder_rel_path="", target_level="all", recursive=True):
    folder_abs = safe_rel_path(directory, folder_rel_path)
    if not folder_abs or not os.path.isdir(folder_abs):
        return {"status": "error", "message": "Folder not found", "cards": []}

    md_files = []
    if recursive:
        for root, dirs, files in os.walk(folder_abs):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in ('node_modules', '.obsidian', '.vscode', '.git', '.idea')]
            for f in sorted(files):
                if f.lower().endswith(('.md', '.markdown')):
                    abs_p = os.path.join(root, f)
                    rel_p = os.path.relpath(abs_p, directory).replace('\\', '/')
                    md_files.append((abs_p, rel_p))
    else:
        for entry in sorted(os.scandir(folder_abs), key=lambda e: e.name):
            if entry.is_file() and entry.name.lower().endswith(('.md', '.markdown')):
                rel_p = os.path.relpath(entry.path, directory).replace('\\', '/')
                md_files.append((entry.path, rel_p))

    all_cards = []
    target_int = int(target_level) if str(target_level).isdigit() and int(target_level) > 0 else 0

    for file_abs, file_rel in md_files:
        try:
            with open(file_abs, 'r', encoding='utf-8', errors='replace') as fp:
                file_lines = fp.read().splitlines()
        except Exception:
            continue

        file_headings = []
        for idx, l in enumerate(file_lines):
            m = re.match(r'^(#{1,6})\s+(.*)$', l)
            if m:
                lvl = len(m.group(1))
                htext = m.group(2).strip()
                file_headings.append({
                    "level": lvl,
                    "text": htext,
                    "line": idx,
                    "end": len(file_lines) - 1
                })

        for i in range(len(file_headings)):
            curr = file_headings[i]
            for j in range(i + 1, len(file_headings)):
                nxt = file_headings[j]
                if nxt["level"] <= curr["level"]:
                    curr["end"] = max(curr["line"], nxt["line"] - 1)
                    break

        file_base = os.path.basename(file_rel)
        for h in file_headings:
            if target_int > 0 and h["level"] != target_int:
                continue

            start_l = h["line"] + 1
            end_l = h["end"]
            card_body = "\n".join(file_lines[start_l:end_l + 1]) if start_l <= end_l else ""

            slug = re.sub(r'[^\w\s-]', '', h["text"].lower())
            slug = re.sub(r'[-\s]+', '-', slug).strip('-') or f"h{h['level']}-{h['line']}"

            all_cards.append({
                "file_path": file_rel,
                "file_name": file_base,
                "level": h["level"],
                "text": h["text"],
                "slug": slug,
                "breadcrumb": f"{file_base} > H{h['level']}",
                "card_content": card_body,
                "line": h["line"],
                "end": h["end"]
            })

    folder_name = os.path.basename(folder_rel_path.rstrip('/\\')) if folder_rel_path else os.path.basename(os.path.abspath(directory))
    return {
        "status": "ok",
        "folder": folder_rel_path,
        "folder_name": folder_name or "Root",
        "target_level": target_level,
        "total_files": len(md_files),
        "total_cards": len(all_cards),
        "cards": all_cards
    }

def extract_ai_content(choices, target_model=""):
    if not choices:
        raise RuntimeError("No choices returned from OpenRouter")
    msg_obj = choices[0].get("message", {})
    raw_content = (msg_obj.get("content") or "").strip()

    # Priority 1: Model output in message.content
    if raw_content:
        # Check if the content contains <think>...</think> tags and strip them
        clean = re.sub(r'<think>[\s\S]*?</think>', '', raw_content).strip()
        if clean:
            return clean
        # If unclosed think tag or only think tags, return raw_content
        return raw_content

    # Priority 2: Alternative text field in choice
    alt_text = (choices[0].get("text") or "").strip()
    if alt_text:
        clean = re.sub(r'<think>[\s\S]*?</think>', '', alt_text).strip()
        if clean:
            return clean
        return alt_text

    # Priority 3: Reasoning fallback if and only if no content was produced
    reasoning = (msg_obj.get("reasoning") or msg_obj.get("reasoning_content") or "").strip()
    if reasoning:
        return reasoning

    raise RuntimeError("OpenRouter returned an empty response. Please check model status or retry.")

def get_ollama_models(host="http://localhost:11434"):
    clean_host = (host or "http://localhost:11434").strip().rstrip('/')
    if not clean_host.startswith(('http://', 'https://')):
        clean_host = 'http://' + clean_host
    req = urllib.request.Request(
        f"{clean_host}/api/tags",
        headers={"User-Agent": "MDViewer/1.2"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        raw_models = data.get("models", [])
        models = []
        for m in raw_models:
            models.append({
                "name": m.get("name"),
                "model": m.get("model") or m.get("name"),
                "size": m.get("size", 0),
                "modified_at": m.get("modified_at", "")
            })
        return models

def proxy_ollama_generate(model, system_prompt, user_message, host="http://localhost:11434", max_tokens=None):
    clean_host = (host or "http://localhost:11434").strip().rstrip('/')
    if not clean_host.startswith(('http://', 'https://')):
        clean_host = 'http://' + clean_host
    target_model = (model or "").strip()
    if not target_model:
        raise ValueError("No Ollama model specified. Please configure your model in AI Settings (⚙️).")

    req_body = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "stream": False
    }
    options = {"num_ctx": 32768}
    if max_tokens is not None and int(max_tokens) > 0:
        options["num_predict"] = int(max_tokens)
        req_body["max_tokens"] = int(max_tokens)
    req_body["options"] = options

    data = json.dumps(req_body).encode('utf-8')
    req = urllib.request.Request(
        f"{clean_host}/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "MDViewer/1.2"
        },
        method="POST"
    )
    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                res_json = json.loads(resp.read().decode('utf-8'))
                choices = res_json.get("choices", [])
                text = extract_ai_content(choices, target_model)
                return {
                    "status": "ok",
                    "content": text,
                    "model": res_json.get("model", target_model),
                    "usage": res_json.get("usage", {})
                }
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode('utf-8', errors='replace')
            try:
                err_json = json.loads(err_msg)
                msg = err_json.get("error", {}).get("message", err_msg)
            except Exception:
                msg = err_msg
            raise RuntimeError(f"Ollama Error ({e.code}): {msg}")
        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            if attempt < max_retries:
                time.sleep(1.5 + attempt)
                continue
            raise RuntimeError(f"Ollama connection error to {clean_host}: {e}")

def proxy_openrouter_generate(model, system_prompt, user_message, api_key=None, max_tokens=None):
    if not api_key:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("Missing OpenRouter API key. Please configure your key in AI Settings (⚙️) or set OPENROUTER_API_KEY.")
    
    clean_key = api_key.strip()
    target_model = (model or "").strip() or "deepseek/deepseek-v4-flash-0731"
    req_body = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    }
    # Completely remove default context limit! Only add max_tokens if explicitly requested as positive int
    if max_tokens is not None and int(max_tokens) > 0:
        req_body["max_tokens"] = int(max_tokens)

    data = json.dumps(req_body).encode('utf-8')
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {clean_key}",
            "HTTP-Referer": "http://127.0.0.1:2026",
            "X-Title": "MDViewer Flashcard Assistant",
            "User-Agent": "MDViewer/1.2"
        },
        method="POST"
    )
    max_retries = 5
    for attempt in range(max_retries + 1):
        try:
            # 300s timeout so reasoning models never get cut off mid-thought
            with urllib.request.urlopen(req, timeout=300) as resp:
                res_json = json.loads(resp.read().decode('utf-8'))
                choices = res_json.get("choices", [])
                text = extract_ai_content(choices, target_model)

                return {
                    "status": "ok",
                    "content": text,
                    "model": res_json.get("model", target_model),
                    "usage": res_json.get("usage", {})
                }
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                retry_after = e.headers.get("Retry-After")
                base_delay = (1.8 ** attempt) * 2.5 + random.uniform(0.5, 2.0)
                try:
                    sleep_s = max(float(retry_after), base_delay) if retry_after else base_delay
                except (ValueError, TypeError):
                    sleep_s = base_delay
                time.sleep(min(sleep_s, 30.0))
                continue
            err_msg = e.read().decode('utf-8', errors='replace')
            try:
                err_json = json.loads(err_msg)
                msg = err_json.get("error", {}).get("message", err_msg)
            except Exception:
                msg = err_msg
            raise RuntimeError(f"OpenRouter Error ({e.code}): {msg}")
        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            if attempt < max_retries:
                time.sleep((1.8 ** attempt) * 2.0 + random.uniform(0.5, 1.5))
                continue
            raise RuntimeError(f"OpenRouter network timeout / connection error: {e}")

class BatchJob:
    def __init__(self, batch_id, directory, file_path, cards, model, api_key, concurrency=1000, mode="missing", skip_existing=True, create_new_version=False, provider="openrouter", ollama_host="http://localhost:11434"):
        self.lock = threading.Lock()
        self.batch_id = batch_id
        self.directory = directory
        self.file_path = file_path
        self.cards = cards
        self.model = model
        self.api_key = api_key
        self.concurrency = concurrency
        self.mode = mode
        self.skip_existing = skip_existing
        self.create_new_version = create_new_version
        self.provider = (provider or "openrouter").strip().lower()
        self.ollama_host = ollama_host or "http://localhost:11434"
        self.status = "running" # running, paused, stopped, completed
        self.total = len(cards)
        self.completed = 0
        self.success_count = 0
        self.skipped_count = 0
        self.error_count = 0
        self.start_time = time.time()
        self.active_workers = {}
        self.events = []
        self.event_counter = 0
        self.failed_cards = []
        self.stop_requested = False
        self.is_paused = False
        self.pause_cond = threading.Condition(self.lock)
        self.executor = None
        self.runner_thread = None

    def start(self):
        existing_set = set()
        if self.skip_existing:
            try:
                conn = get_db_connection(self.directory)
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT file_path, heading_slug, heading_text FROM card_supplements WHERE provider = ?", (self.provider,))
                    for r in cur.fetchall():
                        existing_set.add(f"{r[0]}::{r[1]}")
                        if r[2]:
                            existing_set.add(f"{r[0]}::text::{r[2].strip().lower()}")
                finally:
                    conn.close()
            except Exception as e:
                print(f"[BatchJob {self.batch_id}] Warning reading existing cards: {e}")

        pending_cards = []
        with self.lock:
            for c in self.cards:
                c_file = c.get('file_path') or self.file_path
                card_key = f"{c_file}::{c.get('slug', '')}"
                text_key = f"{c_file}::text::{c.get('text', '').strip().lower()}"
                if self.skip_existing and (card_key in existing_set or text_key in existing_set):
                    self.skipped_count += 1
                    self.completed += 1
                    self.event_counter += 1
                    self.events.append({
                        "id": self.event_counter,
                        "type": "card_skipped",
                        "batch_id": self.batch_id,
                        "card_idx": c.get('cardIdx', 0),
                        "file_path": c_file,
                        "slug": c.get('slug', ''),
                        "text": c.get('text', ''),
                        "completed": self.completed,
                        "total": self.total
                    })
                else:
                    pending_cards.append(c)

        if not pending_cards:
            with self.lock:
                self.status = "completed"
                self.event_counter += 1
                self.events.append({
                    "id": self.event_counter,
                    "type": "batch_done",
                    "batch_id": self.batch_id,
                    "file_path": self.file_path,
                    "status": self.status,
                    "total": self.total,
                    "completed": self.completed,
                    "success": self.success_count,
                    "skipped": self.skipped_count,
                    "errors": self.error_count
                })
            return {
                "status": "ok",
                "batch_id": self.batch_id,
                "file_path": self.file_path,
                "total": self.total,
                "scheduled": 0,
                "skipped": self.skipped_count
            }

        self.runner_thread = threading.Thread(
            target=self._run_batch,
            args=(pending_cards,),
            daemon=True
        )
        self.runner_thread.start()
        return {
            "status": "ok",
            "batch_id": self.batch_id,
            "file_path": self.file_path,
            "total": self.total,
            "scheduled": len(pending_cards),
            "skipped": self.skipped_count
        }

    def _run_batch(self, pending_cards):
        if self.provider == 'ollama':
            pool_concurrency = max(1, min(self.concurrency or 2, 4, len(pending_cards)))
        else:
            pool_concurrency = max(1, min(self.concurrency or 1000, 2000, len(pending_cards)))
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=pool_concurrency)

        def worker(card):
            c_idx = card.get('cardIdx', 0)
            target_file = card.get('file_path') or self.file_path
            max_attempts = 5
            card_success = False
            last_err = None

            for attempt in range(1, max_attempts + 1):
                if self.stop_requested:
                    break

                with self.lock:
                    while self.is_paused and not self.stop_requested:
                        self.pause_cond.wait(timeout=0.2)
                if self.stop_requested:
                    break

                with self.lock:
                    self.active_workers[c_idx] = {
                        "card_idx": c_idx,
                        "title": card.get('text', 'Card'),
                        "start_time": time.time(),
                        "attempt": attempt
                    }

                try:
                    if self.provider == 'ollama':
                        gen_res = proxy_ollama_generate(
                            model=self.model,
                            system_prompt=card.get('system_prompt', ''),
                            user_message=card.get('user_message', ''),
                            host=self.ollama_host
                        )
                    else:
                        gen_res = proxy_openrouter_generate(
                            model=self.model,
                            system_prompt=card.get('system_prompt', ''),
                            user_message=card.get('user_message', ''),
                            api_key=self.api_key
                        )
                    content = (gen_res.get('content') or '').strip()
                    if not content:
                        raise RuntimeError("Empty response received from model")

                    saved = save_card_supplement(
                        directory=self.directory,
                        file_path=target_file,
                        heading_slug=card.get('slug', ''),
                        heading_level=int(card.get('level', 1)),
                        heading_text=card.get('text', ''),
                        breadcrumb=card.get('breadcrumb', ''),
                        prompt_id=card.get('prompt_id', 'detailed'),
                        prompt_name=card.get('prompt_name', ''),
                        provider=self.provider,
                        model=gen_res.get('model', self.model),
                        content=content,
                        raw_front=card.get('raw_front', ''),
                        raw_back=card.get('raw_back', ''),
                        liked=0,
                        create_new_version=self.create_new_version
                    )

                    with self.lock:
                        self.active_workers.pop(c_idx, None)
                        self.success_count += 1
                        self.completed += 1
                        self.event_counter += 1
                        self.events.append({
                            "id": self.event_counter,
                            "type": "card_saved",
                            "batch_id": self.batch_id,
                            "file_path": target_file,
                            "card_idx": c_idx,
                            "slug": card.get('slug', ''),
                            "level": card.get('level', 1),
                            "text": card.get('text', ''),
                            "card": saved,
                            "completed": self.completed,
                            "total": self.total,
                            "success": self.success_count
                        })
                    card_success = True
                    break
                except Exception as e:
                    last_err = e
                    if attempt < max_attempts and not self.stop_requested:
                        retry_delay = min(15.0, (1.8 ** attempt) * 1.5 + random.uniform(0.3, 1.2))
                        time.sleep(retry_delay)
                        continue
                    break

            if not card_success and not self.stop_requested:
                with self.lock:
                    self.active_workers.pop(c_idx, None)
                    self.error_count += 1
                    self.completed += 1
                    err_str = str(last_err) if last_err else "Failed generation"
                    self.failed_cards.append({
                        "card_idx": c_idx,
                        "file_path": target_file,
                        "slug": card.get('slug', ''),
                        "text": card.get('text', ''),
                        "error": err_str,
                        "card_data": card
                    })
                    self.event_counter += 1
                    self.events.append({
                        "id": self.event_counter,
                        "type": "card_error",
                        "batch_id": self.batch_id,
                        "card_idx": c_idx,
                        "file_path": target_file,
                        "slug": card.get('slug', ''),
                        "text": card.get('text', ''),
                        "error": err_str,
                        "completed": self.completed,
                        "total": self.total,
                        "errors": self.error_count
                    })

        futures = [self.executor.submit(worker, card) for card in pending_cards]
        concurrent.futures.wait(futures)
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass

        with self.lock:
            if self.stop_requested:
                self.status = "stopped"
            else:
                self.status = "completed"
            self.active_workers.clear()
            self.event_counter += 1
            self.events.append({
                "id": self.event_counter,
                "type": "batch_done",
                "batch_id": self.batch_id,
                "file_path": self.file_path,
                "status": self.status,
                "total": self.total,
                "completed": self.completed,
                "success": self.success_count,
                "skipped": self.skipped_count,
                "errors": self.error_count
            })

    def pause(self):
        with self.lock:
            if self.status == "running":
                self.is_paused = True
                self.status = "paused"
                self.event_counter += 1
                self.events.append({"id": self.event_counter, "type": "batch_paused", "batch_id": self.batch_id})
                return True
            return False

    def resume(self):
        with self.lock:
            if self.status == "paused":
                self.is_paused = False
                self.status = "running"
                self.pause_cond.notify_all()
                self.event_counter += 1
                self.events.append({"id": self.event_counter, "type": "batch_resumed", "batch_id": self.batch_id})
                return True
            return False

    def stop(self):
        with self.lock:
            self.stop_requested = True
            self.is_paused = False
            self.pause_cond.notify_all()
            if self.status in ("running", "paused"):
                self.status = "stopped"
                self.event_counter += 1
                self.events.append({"id": self.event_counter, "type": "batch_stopped", "batch_id": self.batch_id})
                return True
            return False

    def get_status(self, since_id=0):
        with self.lock:
            now = time.time()
            elapsed = (now - self.start_time) if self.start_time > 0 else 0
            active_list = []
            for cidx, info in list(self.active_workers.items())[:12]:
                active_list.append({
                    "card_idx": cidx,
                    "title": info["title"],
                    "elapsed": round(now - info["start_time"], 1),
                    "attempt": info["attempt"]
                })
            new_events = [e for e in self.events if e["id"] > since_id]
            return {
                "status": self.status,
                "batch_id": self.batch_id,
                "file_path": self.file_path,
                "total": self.total,
                "completed": self.completed,
                "success": self.success_count,
                "skipped": self.skipped_count,
                "errors": self.error_count,
                "in_flight": len(self.active_workers),
                "elapsed_sec": round(elapsed, 1),
                "active_workers": active_list,
                "active_worker_count": len(self.active_workers),
                "failed_cards": [{"card_idx": f["card_idx"], "slug": f["slug"], "text": f["text"], "error": f["error"]} for f in self.failed_cards],
                "new_events": new_events,
                "last_event_id": self.events[-1]["id"] if self.events else 0
            }

class BatchManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.batches = {}
        self.batch_order = []

    def start_batch(self, directory, cards, model, api_key, concurrency=1000, mode="missing", skip_existing=True, create_new_version=False, file_path=None, provider="openrouter", ollama_host="http://localhost:11434"):
        with self.lock:
            if not file_path and cards:
                file_path = cards[0].get('file_path', '')

            # If an active batch already exists for this EXACT same file, stop it to replace with a fresh one.
            # Crucial: NEVER stop batches for other files!
            if file_path:
                for bid in list(self.batches.keys()):
                    b = self.batches[bid]
                    if b.file_path == file_path and b.status in ("running", "paused"):
                        b.stop()

            batch_id = f"batch_{int(time.time() * 1000)}_{random.randint(100, 999)}"
            job = BatchJob(
                batch_id=batch_id,
                directory=directory,
                file_path=file_path or '',
                cards=cards,
                model=model,
                api_key=api_key,
                concurrency=concurrency,
                mode=mode,
                skip_existing=skip_existing,
                create_new_version=create_new_version,
                provider=provider,
                ollama_host=ollama_host
            )
            self.batches[batch_id] = job
            self.batch_order.append(batch_id)
            if len(self.batch_order) > 50:
                old_bid = self.batch_order.pop(0)
                self.batches.pop(old_bid, None)

        return job.start()

    def get_job(self, batch_id=None, file_path=None):
        with self.lock:
            if batch_id and batch_id in self.batches:
                return self.batches[batch_id]
            if file_path:
                matching = [b for b in self.batches.values() if b.file_path == file_path]
                active_m = [b for b in matching if b.status in ("running", "paused")]
                if active_m:
                    return active_m[-1]
                elif matching:
                    return matching[-1]
            # fallback to latest running/paused job or latest job
            active_jobs = [self.batches[bid] for bid in reversed(self.batch_order) if bid in self.batches and self.batches[bid].status in ("running", "paused")]
            if active_jobs:
                return active_jobs[0]
            elif self.batch_order:
                return self.batches.get(self.batch_order[-1])
            return None

    def get_status(self, batch_id=None, file_path=None, since_id=0):
        with self.lock:
            active_batches_summary = []
            for bid in reversed(self.batch_order):
                b = self.batches.get(bid)
                if not b:
                    continue
                active_batches_summary.append({
                    "batch_id": b.batch_id,
                    "file_path": b.file_path,
                    "status": b.status,
                    "total": b.total,
                    "completed": b.completed,
                    "success": b.success_count,
                    "skipped": b.skipped_count,
                    "errors": b.error_count,
                    "in_flight": len(b.active_workers),
                    "elapsed_sec": round((time.time() - b.start_time), 1) if b.start_time > 0 else 0
                })

        job = self.get_job(batch_id, file_path)
        if job:
            res = job.get_status(since_id=since_id)
            res["active_batches"] = active_batches_summary
            return res
        else:
            return {
                "status": "idle",
                "batch_id": None,
                "file_path": file_path or "",
                "total": 0,
                "completed": 0,
                "success": 0,
                "skipped": 0,
                "errors": 0,
                "in_flight": 0,
                "elapsed_sec": 0,
                "active_workers": [],
                "active_worker_count": 0,
                "failed_cards": [],
                "new_events": [],
                "last_event_id": 0,
                "active_batches": active_batches_summary
            }

    def pause(self, batch_id=None, file_path=None):
        if batch_id == 'all':
            with self.lock:
                for b in self.batches.values():
                    b.pause()
            return True
        job = self.get_job(batch_id, file_path)
        return job.pause() if job else False

    def resume(self, batch_id=None, file_path=None):
        if batch_id == 'all':
            with self.lock:
                for b in self.batches.values():
                    b.resume()
            return True
        job = self.get_job(batch_id, file_path)
        return job.resume() if job else False

    def stop(self, batch_id=None, file_path=None):
        if batch_id == 'all':
            with self.lock:
                for b in self.batches.values():
                    b.stop()
            return True
        job = self.get_job(batch_id, file_path)
        return job.stop() if job else False

    def retry_failed(self, directory, model, api_key, concurrency=1000, batch_id=None, file_path=None):
        job = self.get_job(batch_id, file_path)
        if not job or not job.failed_cards:
            return {"status": "ok", "message": "No failed cards to retry", "scheduled": 0}
        with job.lock:
            cards_to_retry = [f["card_data"] for f in job.failed_cards if "card_data" in f]
        if not cards_to_retry:
            return {"status": "ok", "message": "No cards to retry", "scheduled": 0}
        return self.start_batch(
            directory=directory,
            cards=cards_to_retry,
            model=model,
            api_key=api_key,
            concurrency=concurrency,
            mode="overwrite",
            skip_existing=False,
            create_new_version=False,
            file_path=job.file_path,
            provider=getattr(job, 'provider', 'openrouter'),
            ollama_host=getattr(job, 'ollama_host', 'http://localhost:11434')
        )

global_batch_manager = BatchManager()

def exec_terminal_command(directory, cwd, cmd_line):
    cmd_line = (cmd_line or "").strip()
    if not cmd_line:
        return {"status": "ok", "cwd": cwd, "output": ""}

    cur_dir_abs = safe_rel_path(directory, cwd)
    if not cur_dir_abs or not os.path.isdir(cur_dir_abs):
        cwd = ""
        cur_dir_abs = os.path.abspath(directory)

    try:
        tokens = shlex.split(cmd_line)
    except Exception as e:
        return {"status": "error", "cwd": cwd, "output": f"Syntax error: {e}"}

    if not tokens:
        return {"status": "ok", "cwd": cwd, "output": ""}

    cmd = tokens[0].lower()
    args = tokens[1:]

    if cmd == "help":
        help_text = (
            "MDViewer In-Browser Terminal (Sandboxed CLI)\n"
            "===========================================\n"
            "Buffer & File Commands:\n"
            "  hx <file>        Open file in staging buffer editor (alias: edit)\n"
            "  diff [file]      Show unified diff between buffer and original file\n"
            "  accept <file>    Accept buffer changes and replace original file\n"
            "  discard <file>   Discard staging buffer (revert to original)\n"
            "  status           List all active staging buffers\n\n"
            "AI Supplements:\n"
            "  ai status        Show AI supplement statistics and database info\n"
            "  ai cleanup [f]   Clean up stored AI supplements (file or all)\n"
            "  ai export <file> Export AI supplements to <file>.supplement.md\n\n"
            "Navigation & Exploration:\n"
            "  ls [dir]         List files & folders in current directory\n"
            "  cd <dir>         Change working directory (cd ~ or cd ..)\n"
            "  pwd              Print current working directory\n"
            "  cat <file>       Display file content\n"
            "  touch <file>     Create an empty markdown file\n"
            "  mkdir <dir>      Create a new directory\n"
            "  clear            Clear terminal screen\n"
            "  help             Show this help guide\n"
        )
        return {"status": "ok", "cwd": cwd, "output": help_text}

    elif cmd == "pwd":
        display_cwd = "/" + cwd.replace('\\', '/') if cwd else "/"
        return {"status": "ok", "cwd": cwd, "output": display_cwd}

    elif cmd == "cd":
        target = args[0] if args else "~"
        if target in ("~", "/", ""):
            return {"status": "ok", "cwd": "", "output": ""}
        if target == "..":
            if not cwd:
                return {"status": "ok", "cwd": "", "output": ""}
            parent_cwd = os.path.dirname(cwd.rstrip('/\\'))
            return {"status": "ok", "cwd": parent_cwd.replace('\\', '/'), "output": ""}

        candidate_rel = os.path.normpath(os.path.join(cwd, target)).replace('\\', '/')
        if candidate_rel.startswith('..'):
            candidate_rel = ""
        candidate_abs = safe_rel_path(directory, candidate_rel)
        if candidate_abs and os.path.isdir(candidate_abs):
            new_rel = os.path.relpath(candidate_abs, os.path.abspath(directory)).replace('\\', '/')
            if new_rel == '.':
                new_rel = ""
            return {"status": "ok", "cwd": new_rel, "output": ""}
        else:
            return {"status": "error", "cwd": cwd, "output": f"cd: no such directory: {target}"}

    elif cmd in ("ls", "dir"):
        target_dir = cur_dir_abs
        if args:
            target_rel = os.path.normpath(os.path.join(cwd, args[0])).replace('\\', '/')
            target_dir = safe_rel_path(directory, target_rel)
            if not target_dir or not os.path.isdir(target_dir):
                return {"status": "error", "cwd": cwd, "output": f"ls: cannot access '{args[0]}': No such directory"}

        try:
            entries = sorted(os.listdir(target_dir))
            active_bufs = {b["path"] for b in list_all_buffers(directory)}
            lines = []
            dir_count = 0
            file_count = 0
            for name in entries:
                if name.startswith('.') and not name.endswith('.md'):
                    continue
                full_p = os.path.join(target_dir, name)
                rel_p = os.path.relpath(full_p, os.path.abspath(directory)).replace('\\', '/')
                is_dir = os.path.isdir(full_p)
                has_buf = rel_p in active_bufs

                buf_tag = "  [BUFFER PENDING]" if has_buf else ""
                if is_dir:
                    dir_count += 1
                    lines.append(f"📁 {name}/")
                else:
                    file_count += 1
                    try:
                        sz = os.path.getsize(full_p)
                        sz_str = f"{sz:,} B" if sz < 1024 else f"{sz/1024:.1f} KB"
                    except Exception:
                        sz_str = ""
                    icon = "📄" if name.endswith('.md') else "📃"
                    lines.append(f"{icon} {name:<35} {sz_str:>8}{buf_tag}")

            summary = f"\nTotal: {dir_count} directories, {file_count} files"
            return {"status": "ok", "cwd": cwd, "output": "\n".join(lines) + summary}
        except Exception as e:
            return {"status": "error", "cwd": cwd, "output": f"ls: error reading directory: {e}"}

    elif cmd == "cat":
        if not args:
            return {"status": "error", "cwd": cwd, "output": "cat: missing file operand"}
        target_rel = os.path.normpath(os.path.join(cwd, args[0])).replace('\\', '/')
        target_abs = safe_rel_path(directory, target_rel)
        if not target_abs or not os.path.isfile(target_abs):
            return {"status": "error", "cwd": cwd, "output": f"cat: {args[0]}: No such file"}
        try:
            with open(target_abs, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return {"status": "ok", "cwd": cwd, "output": content}
        except Exception as e:
            return {"status": "error", "cwd": cwd, "output": f"cat: {args[0]}: {e}"}

    elif cmd in ("hx", "edit", "buffer"):
        if not args:
            return {"status": "error", "cwd": cwd, "output": f"{cmd}: missing file operand. Usage: {cmd} <filename>"}
        target_rel = os.path.normpath(os.path.join(cwd, args[0])).replace('\\', '/')
        target_abs = safe_rel_path(directory, target_rel)
        if not target_abs:
            return {"status": "error", "cwd": cwd, "output": f"{cmd}: security violation - path restricted to workspace"}

        if not os.path.exists(target_abs):
            os.makedirs(os.path.dirname(target_abs), exist_ok=True)
            with open(target_abs, 'w', encoding='utf-8') as f:
                f.write("")

        info = get_buffer_info(directory, target_rel)
        return {
            "status": "ok",
            "cwd": cwd,
            "output": f"Opening staging buffer for: {target_rel}\n(Changes will NOT affect original file until accepted)",
            "action": {
                "type": "open_buffer",
                "path": target_rel,
                "info": info
            }
        }

    elif cmd == "diff":
        if args:
            target_rel = os.path.normpath(os.path.join(cwd, args[0])).replace('\\', '/')
            info = get_buffer_info(directory, target_rel)
            if not info or not info["has_buffer"]:
                return {"status": "ok", "cwd": cwd, "output": f"No active staging buffer for {target_rel}. File is clean."}
            if not info["diff"].strip():
                return {"status": "ok", "cwd": cwd, "output": f"Buffer matches original file {target_rel}. No changes."}
            return {"status": "ok", "cwd": cwd, "output": info["diff"]}
        else:
            active = list_all_buffers(directory)
            if not active:
                return {"status": "ok", "cwd": cwd, "output": "No active staging buffers in workspace."}
            out_parts = []
            for b in active:
                out_parts.append(f"--- Diff for {b['path']} ---")
                out_parts.append(b["diff"] if b["diff"] else "No changes.")
            return {"status": "ok", "cwd": cwd, "output": "\n\n".join(out_parts)}

    elif cmd == "accept":
        if not args:
            return {"status": "error", "cwd": cwd, "output": "accept: missing file operand. Usage: accept <filename>"}
        target_rel = os.path.normpath(os.path.join(cwd, args[0])).replace('\\', '/')
        try:
            res = accept_buffer(directory, target_rel)
            return {
                "status": "ok",
                "cwd": cwd,
                "output": f"✓ {res['message']}",
                "action": { "type": "buffer_accepted", "path": target_rel }
            }
        except Exception as e:
            return {"status": "error", "cwd": cwd, "output": f"accept: {e}"}

    elif cmd in ("discard", "revert"):
        if not args:
            return {"status": "error", "cwd": cwd, "output": f"{cmd}: missing file operand. Usage: {cmd} <filename>"}
        target_rel = os.path.normpath(os.path.join(cwd, args[0])).replace('\\', '/')
        try:
            res = discard_buffer(directory, target_rel)
            return {
                "status": "ok",
                "cwd": cwd,
                "output": f"✓ {res['message']}",
                "action": { "type": "buffer_discarded", "path": target_rel }
            }
        except Exception as e:
            return {"status": "error", "cwd": cwd, "output": f"{cmd}: {e}"}

    elif cmd == "status":
        active = list_all_buffers(directory)
        if not active:
            return {"status": "ok", "cwd": cwd, "output": "No active staging buffers. Workspace clean."}
        lines = ["Active Staging Buffers (Pending Acceptance):", "------------------------------------------"]
        for b in active:
            st = "MODIFIED" if b["is_dirty"] else "STAGED (Identical to original)"
            lines.append(f"  * {b['path']:<35} [{st}]")
        lines.append("\nType 'diff <file>' to preview changes, or 'accept <file>' to apply.")
        return {"status": "ok", "cwd": cwd, "output": "\n".join(lines)}

    elif cmd == "touch":
        if not args:
            return {"status": "error", "cwd": cwd, "output": "touch: missing file operand"}
        target_rel = os.path.normpath(os.path.join(cwd, args[0])).replace('\\', '/')
        target_abs = safe_rel_path(directory, target_rel)
        if not target_abs:
            return {"status": "error", "cwd": cwd, "output": "touch: security violation - path restricted to workspace"}
        try:
            os.makedirs(os.path.dirname(target_abs), exist_ok=True)
            with open(target_abs, 'a', encoding='utf-8'):
                os.utime(target_abs, None)
            return {"status": "ok", "cwd": cwd, "output": f"Created/touched {target_rel}"}
        except Exception as e:
            return {"status": "error", "cwd": cwd, "output": f"touch: {e}"}

    elif cmd == "mkdir":
        if not args:
            return {"status": "error", "cwd": cwd, "output": "mkdir: missing operand"}
        target_rel = os.path.normpath(os.path.join(cwd, args[0])).replace('\\', '/')
        target_abs = safe_rel_path(directory, target_rel)
        if not target_abs:
            return {"status": "error", "cwd": cwd, "output": "mkdir: security violation - path restricted to workspace"}
        try:
            os.makedirs(target_abs, exist_ok=True)
            return {"status": "ok", "cwd": cwd, "output": f"Created directory {target_rel}"}
        except Exception as e:
            return {"status": "error", "cwd": cwd, "output": f"mkdir: {e}"}

    elif cmd == "ai":
        subcmd = args[0].lower() if args else "status"
        if subcmd == "status":
            summary = get_workspace_supplements_summary(directory)
            total_files = len(summary)
            total_cards = sum(s["count"] for s in summary.values())
            total_liked = sum(s["liked_count"] for s in summary.values())
            db_path = get_supplement_db_path(directory)
            lines = [
                "✨ AI Flashcard Supplements:",
                "----------------------------------------",
                f"Database: {db_path}",
                f"Files with supplements: {total_files}",
                f"Total cards with AI notes: {total_cards}",
                f"Liked cards: {total_liked}"
            ]
            if summary:
                lines.append("\nBreakdown by file:")
                for fp, info in summary.items():
                    lines.append(f"  * {fp:<35} {info['count']} cards ({info['liked_count']} liked)")
            return {"status": "ok", "cwd": cwd, "output": "\n".join(lines)}
        elif subcmd == "cleanup":
            target = args[1] if len(args) > 1 else None
            if not target or target in ("all", "*"):
                res = cleanup_supplements(directory, scope='all')
                return {"status": "ok", "cwd": cwd, "output": f"✓ Cleaned up all AI supplements ({res['deleted']} entries removed)."}
            else:
                target_rel = os.path.normpath(os.path.join(cwd, target)).replace('\\', '/')
                res = cleanup_supplements(directory, scope='file', file_path=target_rel)
                return {"status": "ok", "cwd": cwd, "output": f"✓ Cleaned up AI supplements for {target_rel} ({res['deleted']} entries removed)."}
        elif subcmd == "export":
            if len(args) < 2:
                return {"status": "error", "cwd": cwd, "output": "ai export: missing file operand. Usage: ai export <filename>"}
            target_rel = os.path.normpath(os.path.join(cwd, args[1])).replace('\\', '/')
            content = export_supplements_markdown(directory, target_rel)
            out_file = safe_rel_path(directory, target_rel + ".supplement.md")
            if out_file:
                with open(out_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                return {"status": "ok", "cwd": cwd, "output": f"✓ Exported supplements to: {target_rel}.supplement.md"}
            return {"status": "error", "cwd": cwd, "output": "Security error exporting supplement file"}
        else:
            return {"status": "error", "cwd": cwd, "output": f"ai: unknown subcommand '{subcmd}'. Usage: ai [status | cleanup [file] | export <file>]"}

    elif cmd == "echo":
        return {"status": "ok", "cwd": cwd, "output": " ".join(args)}

    elif cmd == "clear":
        return {"status": "ok", "cwd": cwd, "output": "", "action": { "type": "clear" }}

    else:
        return {
            "status": "error",
            "cwd": cwd,
            "output": f"{cmd}: command not found. Type 'help' for available commands."
        }

def main():
    directory = sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else os.getcwd()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def send_json(self, status_code, obj):
            data = json.dumps(obj).encode('utf-8')
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            try:
                self.wfile.flush()
            except Exception:
                pass

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            
            if parsed.path == '/':
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                
                try:
                    # For Python 3.9+
                    html_content = importlib.resources.files('mdviewer').joinpath('index.html').read_bytes()
                except AttributeError:
                    # For Python 3.8
                    html_content = importlib.resources.read_binary('mdviewer', 'index.html')
                    
                self.wfile.write(html_content)
                
            elif parsed.path in ('/favicon.ico', '/icon.png'):
                self.send_response(200)
                self.send_header('Content-type', 'image/png')
                self.end_headers()
                try:
                    # For Python 3.9+
                    icon_content = importlib.resources.files('mdviewer').joinpath('icon.png').read_bytes()
                except AttributeError:
                    # For Python 3.8
                    icon_content = importlib.resources.read_binary('mdviewer', 'icon.png')
                self.wfile.write(icon_content)
                
            elif parsed.path == '/api/tree':
                query = urllib.parse.parse_qs(parsed.query)
                rel_path = query.get('path', [''])[0]
                
                # Make sure rel_path doesn't escape directory
                target_dir = os.path.abspath(os.path.join(directory, rel_path))
                if not target_dir.startswith(os.path.abspath(directory)):
                    self.send_response(403)
                    self.end_headers()
                    return

                entries = []
                if os.path.isdir(target_dir):
                    try:
                        for entry in os.scandir(target_dir):
                            if entry.name.startswith('.'):
                                continue
                            if entry.is_dir():
                                if entry.name.lower() in ('node_modules', '.obsidian', '.vscode', '.idea'):
                                    continue
                                entries.append({"name": entry.name, "kind": "directory"})
                            elif entry.is_file():
                                if entry.name.lower().endswith(('.md', '.markdown', '.txt')):
                                    entries.append({"name": entry.name, "kind": "file"})
                    except Exception as e:
                        pass
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(entries).encode('utf-8'))
                
            elif parsed.path == '/api/file':
                query = urllib.parse.parse_qs(parsed.query)
                rel_path = query.get('path', [''])[0]
                target_file = os.path.abspath(os.path.join(directory, rel_path))
                
                if not target_file.startswith(os.path.abspath(directory)):
                    self.send_response(403)
                    self.end_headers()
                    return
                    
                try:
                    with open(target_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(content.encode('utf-8'))
                except Exception as e:
                    self.send_response(404)
                    self.end_headers()
                    
            elif parsed.path == '/api/search':
                query_args = urllib.parse.parse_qs(parsed.query)
                q = query_args.get('q', [''])[0].lower()
                if not q:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'[]')
                    return
                    
                results = []
                # Walk the directory
                for root, dirs, files in os.walk(directory):
                    # Skip hidden dirs and node_modules
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in ('node_modules', '.obsidian', '.vscode', '.idea')]
                    for file in files:
                        if file.lower().endswith(('.md', '.markdown', '.txt')) and not file.startswith('.'):
                            filepath = os.path.join(root, file)
                            rel_path = os.path.relpath(filepath, directory)
                            try:
                                with open(filepath, 'r', encoding='utf-8') as f:
                                    lines = f.readlines()
                                    for i, line in enumerate(lines):
                                        if q in line.lower():
                                            results.append({
                                                "file": rel_path,
                                                "line": i,
                                                "text": line.strip()[:200]  # snippet
                                            })
                                            if len(results) > 100:  # cap results for performance
                                                break
                            except Exception:
                                pass
                            if len(results) > 100:
                                break
                    if len(results) > 100:
                        break

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(results).encode('utf-8'))
            elif parsed.path == '/api/config':
                config_file = os.path.expanduser("~/.mdviewer_config.json")
                config_data = {}
                if os.path.exists(config_file):
                    try:
                        with open(config_file, 'r') as f:
                            config_data = json.load(f)
                    except:
                        pass
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(config_data).encode('utf-8'))
            elif parsed.path == '/api/buffers':
                buffers = list_all_buffers(directory)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(buffers).encode('utf-8'))
            elif parsed.path == '/api/ai/ollama/models':
                query = urllib.parse.parse_qs(parsed.query)
                host = query.get('host', ['http://localhost:11434'])[0]
                try:
                    models = get_ollama_models(host)
                    self.send_json(200, {"status": "ok", "models": models})
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e), "models": []})
            elif parsed.path == '/api/ai/card':
                query = urllib.parse.parse_qs(parsed.query)
                file_path = query.get('file', [None])[0]
                folder_path = query.get('folder', [None])[0]
                heading_slug = query.get('heading', [None])[0]
                heading_level = query.get('level', [None])[0]
                prompt_id = query.get('prompt_id', [None])[0]
                version = query.get('version', [None])[0]
                provider = query.get('provider', [None])[0]
                search = query.get('search', [None])[0]
                limit_val = query.get('limit', [None])[0]
                limit = int(limit_val) if limit_val else (None if (file_path or heading_slug) else 300)
                offset_val = query.get('offset', [None])[0]
                offset = int(offset_val) if offset_val else None
                cards = get_card_supplements(
                    directory,
                    file_path=file_path,
                    heading_slug=heading_slug,
                    prompt_id=prompt_id,
                    version=version,
                    folder_path=folder_path,
                    heading_level=heading_level,
                    search=search,
                    limit=limit,
                    offset=offset,
                    provider=provider
                )
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(cards).encode('utf-8'))
            elif parsed.path == '/api/ai/summary':
                summary = get_workspace_supplements_summary(directory)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(summary).encode('utf-8'))
            elif parsed.path == '/api/ai/file-cards':
                query = urllib.parse.parse_qs(parsed.query)
                file_path = query.get('file', [''])[0]
                provider = query.get('provider', [None])[0]
                saved_cards = get_file_saved_cards(directory, file_path, provider=provider)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(saved_cards).encode('utf-8'))
            elif parsed.path == '/api/ai/folder-cards':
                query = urllib.parse.parse_qs(parsed.query)
                folder_path = query.get('folder', [''])[0]
                provider = query.get('provider', [None])[0]
                saved_cards = get_folder_saved_cards(directory, folder_path, provider=provider)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(saved_cards).encode('utf-8'))
            elif parsed.path == '/api/ai/prompts':
                prompts = get_prompts(directory)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(prompts).encode('utf-8'))
            elif parsed.path == '/api/ai/settings':
                settings = get_ai_settings(directory)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(settings).encode('utf-8'))
            elif parsed.path == '/api/ai/export':
                query = urllib.parse.parse_qs(parsed.query)
                file_path = query.get('file', [''])[0]
                md_content = export_supplements_markdown(directory, file_path)
                self.send_response(200)
                self.send_header('Content-type', 'text/markdown; charset=utf-8')
                self.end_headers()
                self.wfile.write(md_content.encode('utf-8'))
            elif parsed.path == '/api/folder/cards':
                query = urllib.parse.parse_qs(parsed.query)
                folder_path = query.get('path', [''])[0]
                target_level = query.get('level', ['all'])[0]
                recursive = query.get('recursive', ['1'])[0] in ('1', 'true', 'True')
                res = collect_folder_flashcards(directory, folder_path, target_level, recursive)
                self.send_json(200, res)
            elif parsed.path == '/api/ai/batch/status':
                query = urllib.parse.parse_qs(parsed.query)
                since_id = 0
                try:
                    since_id = int(query.get('since', ['0'])[0])
                except Exception:
                    since_id = 0
                batch_id = query.get('batch_id', [None])[0]
                file_path = query.get('file_path', [None])[0]
                res = global_batch_manager.get_status(batch_id=batch_id, file_path=file_path, since_id=since_id)
                self.send_json(200, res)
            elif parsed.path == '/api/ai/batch/list':
                res = global_batch_manager.get_status()
                self.send_json(200, {
                    "status": "ok",
                    "active_batches": res.get("active_batches", [])
                })
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == '/api/config':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    new_patch = json.loads(post_data)
                    config_file = os.path.expanduser("~/.mdviewer_config.json")
                    config_data = {}
                    if os.path.exists(config_file):
                        try:
                            with open(config_file, 'r') as f:
                                config_data = json.load(f)
                        except:
                            pass
                    
                    config_data.update(new_patch)
                    
                    with open(config_file, 'w') as f:
                        json.dump(config_data, f)
                    
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
            elif parsed.path in ('/api/file', '/api/save'):
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    rel_path = payload.get('path', '')
                    content = payload.get('content', '')
                    target_file = safe_rel_path(directory, rel_path)
                    if not target_file:
                        self.send_response(403)
                        self.end_headers()
                        return
                    with open(target_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
            elif parsed.path == '/api/terminal/exec':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    cmd_line = payload.get('cmd', '')
                    cwd = payload.get('cwd', '')
                    res = exec_terminal_command(directory, cwd, cmd_line)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(res).encode('utf-8'))
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "output": f"Server error: {e}"}).encode('utf-8'))
            elif parsed.path == '/api/buffer/get':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    rel_path = payload.get('path', '')
                    info = get_buffer_info(directory, rel_path)
                    if not info:
                        self.send_response(404)
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", **info}).encode('utf-8'))
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            elif parsed.path == '/api/buffer/save':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    rel_path = payload.get('path', '')
                    content = payload.get('content', '')
                    info = save_buffer_content(directory, rel_path, content)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", **info}).encode('utf-8'))
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            elif parsed.path == '/api/buffer/diff':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    rel_path = payload.get('path', '')
                    info = get_buffer_info(directory, rel_path)
                    if not info:
                        self.send_response(404)
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "path": rel_path, "diff": info["diff"], "is_dirty": info["is_dirty"]}).encode('utf-8'))
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            elif parsed.path == '/api/buffer/accept':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    rel_path = payload.get('path', '')
                    res = accept_buffer(directory, rel_path)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(res).encode('utf-8'))
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            elif parsed.path == '/api/buffer/discard':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    rel_path = payload.get('path', '')
                    res = discard_buffer(directory, rel_path)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(res).encode('utf-8'))
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            elif parsed.path == '/api/open-terminal':
                # Safe redirect to in-browser terminal action
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    rel_path = payload.get('path', '')
                    target = safe_rel_path(directory, rel_path)
                    is_dir = os.path.isdir(target) if target else True
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "ok",
                        "action": "open_in_browser_terminal",
                        "path": rel_path,
                        "is_dir": is_dir
                    }).encode('utf-8'))
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            elif parsed.path == '/api/ai/generate':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    model = payload.get('model', 'deepseek/deepseek-v4-flash-0731')
                    system_prompt = payload.get('system_prompt', '')
                    user_message = payload.get('user_message', '')
                    max_tokens = payload.get('max_tokens')
                    provider = payload.get('provider', 'openrouter')
                    ollama_host = payload.get('ollama_host', 'http://localhost:11434')
                    if provider == 'ollama':
                        res = proxy_ollama_generate(model, system_prompt, user_message, host=ollama_host, max_tokens=max_tokens)
                    else:
                        api_key = payload.get('api_key') or self.headers.get('X-OpenRouter-Key')
                        res = proxy_openrouter_generate(model, system_prompt, user_message, api_key, max_tokens=max_tokens)
                    self.send_json(200, res)
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e)})
            elif parsed.path == '/api/ai/generate/stream':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    model = payload.get('model', 'deepseek/deepseek-v4-flash-0731')
                    system_prompt = payload.get('system_prompt', '')
                    user_message = payload.get('user_message', '')
                    max_tokens = payload.get('max_tokens')
                    provider = payload.get('provider', 'openrouter')
                    ollama_host = payload.get('ollama_host', 'http://localhost:11434')

                    if provider == 'ollama':
                        clean_host = (ollama_host or "http://localhost:11434").strip().rstrip('/')
                        if not clean_host.startswith(('http://', 'https://')):
                            clean_host = 'http://' + clean_host
                        target_model = (model or "").strip()
                        if not target_model:
                            self.send_json(400, {"status": "error", "message": "No Ollama model specified."})
                            return
                        req_body = {
                            "model": target_model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_message}
                            ],
                            "stream": True,
                            "options": {
                                "num_ctx": 32768
                            }
                        }
                        if max_tokens and int(max_tokens) > 0:
                            req_body["options"]["num_predict"] = int(max_tokens)
                            req_body["max_tokens"] = int(max_tokens)
                        data = json.dumps(req_body).encode('utf-8')
                        req = urllib.request.Request(
                            f"{clean_host}/v1/chat/completions",
                            data=data,
                            headers={
                                "Content-Type": "application/json",
                                "User-Agent": "MDViewer/1.2"
                            },
                            method="POST"
                        )
                        try:
                            resp = urllib.request.urlopen(req, timeout=300)
                        except urllib.error.HTTPError as e:
                            err_msg = e.read().decode('utf-8', errors='replace')
                            self.send_json(e.code, {"status": "error", "message": f"Ollama Error ({e.code}): {err_msg}"})
                            return
                        except Exception as e:
                            self.send_json(500, {"status": "error", "message": f"Ollama connection error: {e}"})
                            return

                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                        self.send_header('Cache-Control', 'no-cache, no-transform')
                        self.send_header('X-Accel-Buffering', 'no')
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        self.wfile.flush()

                        with resp:
                            for chunk in resp:
                                try:
                                    self.wfile.write(chunk)
                                    self.wfile.flush()
                                except (BrokenPipeError, ConnectionResetError):
                                    break
                        return

                    api_key = payload.get('api_key') or self.headers.get('X-OpenRouter-Key')
                    if not api_key:
                        api_key = os.environ.get("OPENROUTER_API_KEY", "")
                    if not api_key:
                        self.send_json(400, {"status": "error", "message": "Missing OpenRouter API key. Please configure your key in AI Settings (⚙️)."})
                        return

                    target_model = (model or "").strip() or "deepseek/deepseek-v4-flash-0731"
                    req_body = {
                        "model": target_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message}
                        ],
                        "stream": True
                    }
                    if max_tokens and int(max_tokens) > 0:
                        req_body["max_tokens"] = int(max_tokens)
                    data = json.dumps(req_body).encode('utf-8')
                    req = urllib.request.Request(
                        "https://openrouter.ai/api/v1/chat/completions",
                        data=data,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key.strip()}",
                            "HTTP-Referer": "http://127.0.0.1:2026",
                            "X-Title": "MDViewer Flashcard Assistant",
                            "User-Agent": "MDViewer/1.2"
                        },
                        method="POST"
                    )

                    try:
                        # 300s socket timeout prevents premature timeout during deep reasoning
                        resp = urllib.request.urlopen(req, timeout=300)
                    except urllib.error.HTTPError as e:
                        err_msg = e.read().decode('utf-8', errors='replace')
                        try:
                            err_json = json.loads(err_msg)
                            msg = err_json.get("error", {}).get("message", err_msg)
                        except Exception:
                            msg = err_msg
                        self.send_json(e.code, {"status": "error", "message": f"OpenRouter Error ({e.code}): {msg}"})
                        return
                    except Exception as e:
                        self.send_json(500, {"status": "error", "message": f"Connection error: {e}"})
                        return

                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                    self.send_header('Cache-Control', 'no-cache, no-transform')
                    self.send_header('X-Accel-Buffering', 'no')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.flush()

                    with resp:
                        for chunk in resp:
                            try:
                                self.wfile.write(chunk)
                                self.wfile.flush()
                            except (BrokenPipeError, ConnectionResetError):
                                break
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e)})
            elif parsed.path == '/api/ai/card/save':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    card = save_card_supplement(
                        directory=directory,
                        file_path=payload.get('file_path', ''),
                        heading_slug=payload.get('heading_slug', ''),
                        heading_level=int(payload.get('heading_level', 1)),
                        heading_text=payload.get('heading_text', ''),
                        breadcrumb=payload.get('breadcrumb', ''),
                        prompt_id=payload.get('prompt_id', 'detailed'),
                        prompt_name=payload.get('prompt_name', ''),
                        model=payload.get('model', 'deepseek/deepseek-v4-flash-0731'),
                        content=payload.get('content', ''),
                        raw_front=payload.get('raw_front', ''),
                        raw_back=payload.get('raw_back', ''),
                        liked=int(payload.get('liked', 0)),
                        version=payload.get('version'),
                        create_new_version=bool(payload.get('create_new_version', False)),
                        provider=payload.get('provider', 'openrouter')
                    )
                    self.send_json(200, {"status": "ok", "card": card})
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e)})
            elif parsed.path == '/api/ai/card/delete':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    supp_id = payload.get('id') or payload.get('supplement_id')
                    delete_card_supplement(
                        directory=directory,
                        file_path=payload.get('file_path'),
                        heading_slug=payload.get('heading_slug'),
                        prompt_id=payload.get('prompt_id'),
                        version=payload.get('version'),
                        supplement_id=supp_id,
                        provider=payload.get('provider')
                    )
                    self.send_json(200, {"status": "ok"})
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e)})
            elif parsed.path == '/api/ai/card/like':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    liked = toggle_card_like(
                        directory=directory,
                        file_path=payload.get('file_path', ''),
                        heading_slug=payload.get('heading_slug', ''),
                        prompt_id=payload.get('prompt_id'),
                        version=payload.get('version'),
                        provider=payload.get('provider')
                    )
                    self.send_json(200, {"status": "ok", "liked": liked})
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e)})
            elif parsed.path == '/api/ai/prompts/save':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    prompts = payload.get('prompts', [])
                    updated = save_prompts(directory, prompts)
                    self.send_json(200, {"status": "ok", "prompts": updated})
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e)})
            elif parsed.path == '/api/ai/settings/save':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    settings = payload.get('settings') if (isinstance(payload, dict) and 'settings' in payload) else payload
                    updated = save_ai_settings(directory, settings if isinstance(settings, dict) else {})
                    self.send_json(200, {"status": "ok", "settings": updated})
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e)})
            elif parsed.path == '/api/ai/cleanup':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    scope = payload.get('scope', 'all')
                    file_path = payload.get('file_path')
                    heading_slug = payload.get('heading_slug')
                    ids = payload.get('ids')
                    valid_slugs = payload.get('valid_slugs')
                    valid_texts = payload.get('valid_texts')
                    provider = payload.get('provider')
                    res = cleanup_supplements(directory, scope=scope, file_path=file_path, heading_slug=heading_slug, ids=ids, valid_slugs=valid_slugs, valid_texts=valid_texts, provider=provider)
                    self.send_json(200, res)
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e)})
            elif parsed.path == '/api/ai/batch/start':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    cards = payload.get('cards', [])
                    model = payload.get('model', 'deepseek/deepseek-v4-flash-0731')
                    api_key = payload.get('api_key') or self.headers.get('X-OpenRouter-Key')
                    if not api_key:
                        api_key = os.environ.get("OPENROUTER_API_KEY", "")
                    concurrency = int(payload.get('concurrency', 1000))
                    mode = payload.get('mode', 'missing')
                    skip_existing = bool(payload.get('skip_existing', True))
                    create_new_version = bool(payload.get('create_new_version', False))
                    file_path = payload.get('file_path', '')
                    provider = payload.get('provider', 'openrouter')
                    ollama_host = payload.get('ollama_host', 'http://localhost:11434')
                    res = global_batch_manager.start_batch(
                        directory=directory,
                        cards=cards,
                        model=model,
                        api_key=api_key,
                        concurrency=concurrency,
                        mode=mode,
                        skip_existing=skip_existing,
                        create_new_version=create_new_version,
                        file_path=file_path,
                        provider=provider,
                        ollama_host=ollama_host
                    )
                    self.send_json(200, res)
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e)})
            elif parsed.path == '/api/ai/batch/pause':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
                payload = json.loads(post_data.decode('utf-8')) if post_data.strip() else {}
                batch_id = payload.get('batch_id')
                file_path = payload.get('file_path')
                paused = global_batch_manager.pause(batch_id=batch_id, file_path=file_path)
                self.send_json(200, {"status": "ok", "paused": paused, "batch_id": batch_id})
            elif parsed.path == '/api/ai/batch/resume':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
                payload = json.loads(post_data.decode('utf-8')) if post_data.strip() else {}
                batch_id = payload.get('batch_id')
                file_path = payload.get('file_path')
                resumed = global_batch_manager.resume(batch_id=batch_id, file_path=file_path)
                self.send_json(200, {"status": "ok", "resumed": resumed, "batch_id": batch_id})
            elif parsed.path == '/api/ai/batch/stop':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
                payload = json.loads(post_data.decode('utf-8')) if post_data.strip() else {}
                batch_id = payload.get('batch_id')
                file_path = payload.get('file_path')
                stopped = global_batch_manager.stop(batch_id=batch_id, file_path=file_path)
                self.send_json(200, {"status": "ok", "stopped": stopped, "batch_id": batch_id})
            elif parsed.path == '/api/ai/batch/retry-failed':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
                try:
                    payload = json.loads(post_data.decode('utf-8'))
                    model = payload.get('model', 'deepseek/deepseek-v4-flash-0731')
                    api_key = payload.get('api_key') or self.headers.get('X-OpenRouter-Key')
                    if not api_key:
                        api_key = os.environ.get("OPENROUTER_API_KEY", "")
                    concurrency = int(payload.get('concurrency', 1000))
                    batch_id = payload.get('batch_id')
                    file_path = payload.get('file_path')
                    res = global_batch_manager.retry_failed(
                        directory=directory,
                        model=model,
                        api_key=api_key,
                        concurrency=concurrency,
                        batch_id=batch_id,
                        file_path=file_path
                    )
                    self.send_json(200, res)
                except Exception as e:
                    self.send_json(500, {"status": "error", "message": str(e)})
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass # Suppress logging

    class ReusableTCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
        request_queue_size = 2048

        def handle_error(self, request, client_address):
            exc = sys.exception()
            if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                return
            super().handle_error(request, client_address)

    port = 2026
    try:
        httpd = ReusableTCPServer(("127.0.0.1", port), Handler)
    except OSError:
        httpd = ReusableTCPServer(("127.0.0.1", 0), Handler)

    init_supplement_db(directory)

    with httpd:
        port = httpd.server_address[1]
        url = f"http://127.0.0.1:{port}"
        print(f"Serving {directory} at {url}")
        
        # Start browser after a tiny delay to ensure server is fully up
        threading.Timer(0.1, lambda: webbrowser.open(url)).start()
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down mdviewer.")
            sys.exit(0)

if __name__ == '__main__':
    main()
