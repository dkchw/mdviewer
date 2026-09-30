"""
Anki .apkg to Markdown Converter for mdviewer.
Converts Anki package files (.apkg) into highly optimized, rich Markdown format
designed specifically for mdviewer's Outline Reader, Flashcards Mode,
Glowing Badge Pill System, Folder Decks, and AI Supplements.

Zero external dependencies - uses standard library only.
"""

import os
import re
import html
import json
import shutil
import sqlite3
import tempfile
import zipfile
import urllib.parse
from typing import Dict, List, Any, Optional, Tuple


def unicase_collate(s1: str, s2: str) -> int:
    """Python collation callback for SQLite 'unicase' collation used by Anki."""
    str1 = (s1 or "").lower()
    str2 = (s2 or "").lower()
    if str1 > str2:
        return 1
    elif str1 < str2:
        return -1
    return 0


def sanitize_filename(name: str) -> str:
    """Sanitize string for use as a file or folder name."""
    s = re.sub(r'[\\/*?:"<>|]', '_', name)
    s = re.sub(r'[\s_]+', '_', s).strip('._ ')
    return s or "deck"


def clean_html(raw: str, assets_prefix: str = "assets/") -> str:
    """
    Clean Anki HTML field content to clean Markdown.
    Preserves bold, italic, underline (as ==highlight==), images, and audio tags.
    """
    if not raw:
        return ""

    # Strip entire <style> and <script> blocks
    text = re.sub(r'<(?:style|script)[^>]*>.*?</(?:style|script)>', '', raw, flags=re.DOTALL | re.IGNORECASE)

    # Replace <br>, <p>, <div> tags with newlines
    text = re.sub(r'<(?:br|p|/p|div|/div)[^>]*>', '\n', text, flags=re.IGNORECASE)

    # <b>, <strong> -> **text**
    text = re.sub(r'<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>', r'**\1**', text, flags=re.DOTALL | re.IGNORECASE)

    # <i>, <em> -> *text*
    text = re.sub(r'<(?:i|em)[^>]*>(.*?)</(?:i|em)>', r'*\1*', text, flags=re.DOTALL | re.IGNORECASE)

    # <u> -> ==text== (Obsidian highlight)
    text = re.sub(r'<u[^>]*>(.*?)</u>', r'==\1==', text, flags=re.DOTALL | re.IGNORECASE)

    # <s>, <del>, <strike> -> ~~text~~
    text = re.sub(r'<(?:s|del|strike)[^>]*>(.*?)</(?:s|del|strike)>', r'~~\1~~', text, flags=re.DOTALL | re.IGNORECASE)

    # <code> -> `code`
    text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL | re.IGNORECASE)

    # <img src="..."> / <img src=...> -> ![image](assets_prefix/filename)
    def img_repl(m):
        src = (m.group(1) or m.group(2) or '').strip()
        clean_src = urllib.parse.unquote(src.split('?')[0].split('#')[0]).strip()
        fname = os.path.basename(clean_src)
        if not fname:
            return ""
        prefix = assets_prefix.rstrip('/') + '/' if assets_prefix else ''
        return f"![image]({prefix}{fname})"

    text = re.sub(r"""<img\b[^>]*?\bsrc=(?:["']([^"']*)["']|([^\s>]+))[^>]*>""", img_repl, text, flags=re.IGNORECASE)

    # [sound:filename] -> ![audio](assets_prefix/filename)
    def sound_repl(m):
        src = m.group(1).strip()
        clean_src = urllib.parse.unquote(src.split('?')[0].split('#')[0]).strip()
        fname = os.path.basename(clean_src)
        if not fname:
            return ""
        prefix = assets_prefix.rstrip('/') + '/' if assets_prefix else ''
        return f"![audio]({prefix}{fname})"

    text = re.sub(r'\[sound:([^\]]+)\]', sound_repl, text, flags=re.IGNORECASE)

    # Strip remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Unescape HTML entities (&nbsp;, &amp;, &lt;, etc.)
    text = html.unescape(text)

    # Normalize whitespace per line while preserving linebreaks
    lines = [re.sub(r'[ \t]+', ' ', l).strip() for l in text.split('\n')]
    cleaned = []
    for l in lines:
        if l or (cleaned and cleaned[-1]):
            cleaned.append(l)

    return '\n'.join(cleaned).strip()


def cloze_to_front(text: str) -> str:
    """Convert Anki cloze deletions {{c1::answer::hint}} to [hint] or [...] for card front."""
    if not text:
        return ""
    return re.sub(r'\{\{c\d+::([^:}]+)(?:::([^}]+))?\}\}', lambda m: f"[{m.group(2)}]" if m.group(2) else "[...]", text)


def cloze_to_back(text: str) -> str:
    """Convert Anki cloze deletions {{c1::answer::hint}} to ==answer== for card back."""
    if not text:
        return ""
    return re.sub(r'\{\{c\d+::([^:}]+)(?:::([^}]+))?\}\}', r'==\1==', text)


def clean_heading_title(raw: str, max_len: int = 120, assets_prefix: str = "assets/") -> str:
    """Sanitize text for use as a single-line markdown heading."""
    if not raw:
        return "Card"
    cleaned = clean_html(cloze_to_front(raw), assets_prefix=assets_prefix)
    cleaned = re.sub(r'[\r\n]+', ' - ', cleaned).strip()
    cleaned = re.sub(r'^#+\s*', '', cleaned)  # Remove leading markdown hashes
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len - 3].rstrip() + "..."
    return cleaned or "Card"


def find_recent_apkgs(workspace_dir: str) -> List[Dict[str, Any]]:
    """Scan workspace and user downloads directory for .apkg files."""
    results = []
    seen = set()

    search_paths = [
        workspace_dir,
        os.path.expanduser("~/Downloads"),
        "/run/host/home/dkchw/Downloads"
    ]

    for base in search_paths:
        if not base or not os.path.isdir(base):
            continue
        try:
            if base == workspace_dir:
                # Walk workspace up to 3 levels deep
                for root, dirs, files in os.walk(base):
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '.venv', '__pycache__')]
                    for f in files:
                        if f.lower().endswith('.apkg'):
                            p = os.path.abspath(os.path.join(root, f))
                            if p not in seen and os.path.isfile(p):
                                seen.add(p)
                                stat = os.stat(p)
                                results.append({
                                    "path": p,
                                    "name": f,
                                    "size": stat.st_size,
                                    "mtime": stat.st_mtime,
                                    "in_workspace": True
                                })
            else:
                for f in os.listdir(base):
                    if f.lower().endswith('.apkg'):
                        p = os.path.abspath(os.path.join(base, f))
                        if p not in seen and os.path.isfile(p):
                            seen.add(p)
                            stat = os.stat(p)
                            results.append({
                                "path": p,
                                "name": f,
                                "size": stat.st_size,
                                "mtime": stat.st_mtime,
                                "in_workspace": False
                            })
        except Exception:
            pass

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


def inspect_apkg(apkg_path: str) -> Dict[str, Any]:
    """
    Inspect an .apkg file without extracting everything.
    Returns deck metadata, card count, note types, and media summary.
    """
    if not os.path.isfile(apkg_path):
        raise FileNotFoundError(f"APKG file not found: {apkg_path}")

    with zipfile.ZipFile(apkg_path, 'r') as z, tempfile.TemporaryDirectory() as td:
        names = set(z.namelist())
        col_file = 'collection.anki21' if 'collection.anki21' in names else 'collection.anki2'
        if col_file not in names:
            raise ValueError(f"Invalid APKG package: neither collection.anki21 nor collection.anki2 found in archive")

        z.extract(col_file, td)
        db_path = os.path.join(td, col_file)

        conn = sqlite3.connect(db_path)
        conn.create_collation('unicase', unicase_collate)
        cur = conn.cursor()

        # Check existing tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}

        decks_map: Dict[int, str] = {}
        # Try Schema B (decks table)
        if 'decks' in tables:
            cur.execute("SELECT id, name FROM decks")
            for did, dname in cur.fetchall():
                decks_map[int(did)] = dname
        # Fallback to Schema A (col.decks JSON)
        if not decks_map and 'col' in tables:
            cur.execute("SELECT decks FROM col")
            row = cur.fetchone()
            if row and row[0] and row[0] != "{}":
                try:
                    raw_decks = json.loads(row[0])
                    for k, v in raw_decks.items():
                        decks_map[int(k)] = v.get("name", f"Deck {k}")
                except Exception:
                    pass

        # Models / Notetypes
        models_map: Dict[int, Dict[str, Any]] = {}
        if 'notetypes' in tables:
            cur.execute("SELECT id, name FROM notetypes")
            for mid, mname in cur.fetchall():
                fields = []
                if 'fields' in tables:
                    cur.execute("SELECT ord, name FROM fields WHERE ntid = ? ORDER BY ord", (mid,))
                    fields = [f[1] for f in cur.fetchall()]
                models_map[int(mid)] = {"name": mname, "fields": fields}
        elif 'col' in tables:
            cur.execute("SELECT models FROM col")
            row = cur.fetchone()
            if row and row[0] and row[0] != "{}":
                try:
                    raw_models = json.loads(row[0])
                    for k, v in raw_models.items():
                        fields = [f.get("name", "") for f in v.get("flds", [])]
                        models_map[int(k)] = {"name": v.get("name", f"Model {k}"), "fields": fields}
                except Exception:
                    pass

        # Card & Note counts per deck
        deck_stats: Dict[int, Dict[str, Any]] = {}
        cur.execute("SELECT did, count(DISTINCT nid), count(*) FROM cards GROUP BY did")
        for did, note_cnt, card_cnt in cur.fetchall():
            dname = decks_map.get(did, f"Deck {did}")
            deck_stats[did] = {
                "id": did,
                "name": dname,
                "note_count": note_cnt,
                "card_count": card_cnt
            }

        total_notes = sum(d["note_count"] for d in deck_stats.values())
        total_cards = sum(d["card_count"] for d in deck_stats.values())

        # Inspect media manifest
        media_count = 0
        audio_count = 0
        image_count = 0
        sample_media = []
        if 'media' in names:
            try:
                media_json = z.read('media').decode('utf-8')
                media_map = json.loads(media_json)
                media_count = len(media_map)
                for num, fname in media_map.items():
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in ('.mp3', '.wav', '.ogg', '.m4a', '.opus', '.aac', '.flac'):
                        audio_count += 1
                    elif ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp'):
                        image_count += 1
                    if len(sample_media) < 5:
                        sample_media.append(fname)
            except Exception:
                pass

        conn.close()

        decks_list = sorted(list(deck_stats.values()), key=lambda d: d["note_count"], reverse=True)
        if not decks_list and decks_map:
            decks_list = [{"id": k, "name": v, "note_count": 0, "card_count": 0} for k, v in decks_map.items()]

        return {
            "status": "ok",
            "apkg_path": apkg_path,
            "filename": os.path.basename(apkg_path),
            "file_size": os.path.getsize(apkg_path),
            "col_version": col_file,
            "total_notes": total_notes,
            "total_cards": total_cards,
            "decks": decks_list,
            "notetypes": [{"id": k, "name": v["name"], "fields": v["fields"]} for k, v in models_map.items()],
            "media": {
                "total": media_count,
                "audio": audio_count,
                "images": image_count,
                "samples": sample_media
            }
        }


def pick_front_field(field_pairs: List[Tuple[str, str]]) -> Tuple[Optional[str], str]:
    """
    Select the optimal field to serve as the card's Front heading.
    Follows priority heuristics:
    1. Standard front/question/word/expression terms
    2. Target language indicators
    3. First non-id/sort field
    """
    if not field_pairs:
        return None, ""

    # Priority 1: Direct matches
    for name, val in field_pairs:
        cname = name.lower()
        if any(k in cname for k in ["front", "mặt trước", "word", "sentence", "question", "term", "expression", "prompt", "text", "vocable", "titel", "title", "heading", "topic", "concept", "diagnose"]):
            if val.strip():
                return name, val

    # Priority 2: Target language name
    for name, val in field_pairs:
        cname = name.lower()
        if any(k in cname for k in ["german", "deutsch", "hanzi", "chinese", "kanji", "japanese", "korean", "spanish", "french", "target"]):
            if val.strip():
                return name, val

    # Priority 3: First non-metadata field
    for name, val in field_pairs:
        cname = name.lower()
        if not any(k in cname for k in ["id", "sort", "rank", "guid", "audio", "sound", "picture", "image", "pos", "type", "verdeckung", "occlusion", "date", "stamp", "source", "note id"]):
            if val.strip():
                return name, val

    # Fallback: First field with content
    for name, val in field_pairs:
        if val.strip():
            return name, val

    return field_pairs[0]


def import_apkg(
    apkg_path: str,
    output_dir: str,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Import and convert an .apkg file to Markdown format for mdviewer.
    Extracts referenced media files into an assets/ directory.
    Creates structured markdown files with # Deck and ## Card headings.
    """
    options = options or {}
    heading_level = int(options.get("heading_level", 2))
    number_cards = bool(options.get("number_cards", True))
    extract_media = bool(options.get("extract_media", True))
    include_tags = bool(options.get("include_tags", True))
    deck_filter = options.get("deck_filter", None)  # list of int did or str name

    os.makedirs(output_dir, exist_ok=True)
    assets_dir = os.path.join(output_dir, "assets")

    if not os.path.isfile(apkg_path):
        raise FileNotFoundError(f"APKG file not found: {apkg_path}")

    with zipfile.ZipFile(apkg_path, 'r') as z, tempfile.TemporaryDirectory() as td:
        names = set(z.namelist())
        col_file = 'collection.anki21' if 'collection.anki21' in names else 'collection.anki2'
        if col_file not in names:
            raise ValueError(f"Invalid APKG: collection file not found in {apkg_path}")

        z.extract(col_file, td)
        db_path = os.path.join(td, col_file)

        conn = sqlite3.connect(db_path)
        conn.create_collation('unicase', unicase_collate)
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}

        # Read Decks
        decks_map: Dict[int, str] = {}
        if 'decks' in tables:
            cur.execute("SELECT id, name FROM decks")
            for did, dname in cur.fetchall():
                decks_map[int(did)] = dname
        if not decks_map and 'col' in tables:
            cur.execute("SELECT decks FROM col")
            row = cur.fetchone()
            if row and row[0] and row[0] != "{}":
                try:
                    raw_decks = json.loads(row[0])
                    for k, v in raw_decks.items():
                        decks_map[int(k)] = v.get("name", f"Deck {k}")
                except Exception:
                    pass

        # Read Notetypes / Fields
        models_map: Dict[int, List[str]] = {}
        if 'notetypes' in tables:
            cur.execute("SELECT id, name FROM notetypes")
            for mid, mname in cur.fetchall():
                fields = []
                if 'fields' in tables:
                    cur.execute("SELECT ord, name FROM fields WHERE ntid = ? ORDER BY ord", (mid,))
                    fields = [f[1] for f in cur.fetchall()]
                models_map[int(mid)] = fields
        elif 'col' in tables:
            cur.execute("SELECT models FROM col")
            row = cur.fetchone()
            if row and row[0] and row[0] != "{}":
                try:
                    raw_models = json.loads(row[0])
                    for k, v in raw_models.items():
                        fields = [f.get("name", "") for f in v.get("flds", [])]
                        models_map[int(k)] = fields
                except Exception:
                    pass

        # Read Media map
        media_map: Dict[str, str] = {}
        extracted_media_count = 0
        if 'media' in names:
            try:
                media_json = z.read('media').decode('utf-8')
                media_map = json.loads(media_json)
            except Exception:
                pass

        if extract_media and media_map:
            os.makedirs(assets_dir, exist_ok=True)
            for zip_key, real_filename in media_map.items():
                if zip_key in names:
                    clean_name = os.path.basename(real_filename)
                    out_path = os.path.join(assets_dir, clean_name)
                    try:
                        with z.open(zip_key) as src_f, open(out_path, 'wb') as dst_f:
                            shutil.copyfileobj(src_f, dst_f)
                        extracted_media_count += 1
                    except Exception:
                        pass

        # Extract Notes and Cards
        cur.execute("""
            SELECT c.did, n.id, n.mid, n.flds, n.tags, c.ord
            FROM cards c JOIN notes n ON n.id = c.nid
            ORDER BY c.did, n.id, c.ord
        """)
        rows = cur.fetchall()
        conn.close()

        # Group notes by Deck ID
        seen_notes_per_deck = set()
        deck_notes: Dict[int, List[Dict[str, Any]]] = {}

        for did, nid, mid, flds_raw, tags, cord in rows:
            # Check deck filter if specified
            if deck_filter is not None:
                dname = decks_map.get(did, "")
                if did not in deck_filter and dname not in deck_filter:
                    continue

            # In note-based mode, each note is imported once per deck
            note_key = (did, nid)
            if note_key in seen_notes_per_deck:
                continue
            seen_notes_per_deck.add(note_key)

            if did not in deck_notes:
                deck_notes[did] = []

            fld_names = models_map.get(mid, [])
            fld_vals = flds_raw.split('\x1f')

            pairs = []
            for i, val in enumerate(fld_vals):
                name = fld_names[i] if i < len(fld_names) else f"Field {i+1}"
                pairs.append((name, val))

            deck_notes[did].append({
                "nid": nid,
                "pairs": pairs,
                "tags": tags or ""
            })

        # Generate Markdown files
        imported_files = []
        total_notes_count = 0
        hashes = '#' * max(1, min(6, heading_level))

        # If there's only 1 deck with notes, use deck name or fallback
        for did, notes in deck_notes.items():
            if not notes:
                continue

            deck_raw_name = decks_map.get(did, f"Deck_{did}")
            # Handle hierarchical subdecks e.g. "German::Vocabulary::A1"
            parts = [sanitize_filename(p) for p in deck_raw_name.split('::') if p.strip()]
            if not parts:
                parts = ["Deck"]

            if len(parts) > 1:
                rel_dir = os.path.join(*parts[:-1])
                target_folder = os.path.join(output_dir, rel_dir)
                os.makedirs(target_folder, exist_ok=True)
                md_filename = f"{parts[-1]}.md"
                md_file_path = os.path.join(target_folder, md_filename)
                # Compute relative assets prefix
                rel_depth = len(parts) - 1
                assets_prefix = ("../" * rel_depth) + "assets/"
            else:
                md_filename = f"{parts[0]}.md"
                md_file_path = os.path.join(output_dir, md_filename)
                assets_prefix = "assets/"

            # Build Markdown document
            lines = [
                f"# {deck_raw_name}",
                "",
                f"> Imported from Anki deck **{deck_raw_name}** ({len(notes)} cards).",
                ""
            ]

            card_idx = 1
            for note in notes:
                pairs = note["pairs"]
                tags = note["tags"]

                front_field, front_val = pick_front_field(pairs)
                clean_front = clean_heading_title(front_val, assets_prefix=assets_prefix)

                if number_cards:
                    heading_line = f"{hashes} {card_idx}. {clean_front}"
                else:
                    heading_line = f"{hashes} {clean_front}"

                lines.append(heading_line)
                lines.append("")

                # If the front field contained multi-line text, images, or details, include it if different from heading
                raw_front_clean = clean_html(cloze_to_back(front_val), assets_prefix=assets_prefix)
                if '\n' in raw_front_clean or len(raw_front_clean) > len(clean_front) + 5 or '![image]' in raw_front_clean:
                    lines.append(f"**{front_field or 'Question'}:** {raw_front_clean}")
                    lines.append("")

                # Add all remaining fields as **Key:** Value
                for name, val in pairs:
                    if name == front_field:
                        continue
                    if not val.strip():
                        continue

                    cleaned_val = clean_html(cloze_to_back(val), assets_prefix=assets_prefix)
                    if not cleaned_val:
                        continue

                    # If multi-line, format cleanly
                    if '\n' in cleaned_val:
                        lines.append(f"**{name}:**\n{cleaned_val}")
                    else:
                        lines.append(f"**{name}:** {cleaned_val}")
                    lines.append("")

                # Tags pill
                clean_tags = " ".join(t.strip() for t in tags.split() if t.strip())
                if include_tags and clean_tags:
                    lines.append(f"**Tags:** {clean_tags}")
                    lines.append("")

                lines.append("---")
                lines.append("")
                card_idx += 1

            # Write file
            with open(md_file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

            imported_files.append(os.path.relpath(md_file_path, output_dir))
            total_notes_count += len(notes)

        return {
            "status": "ok",
            "imported_files": imported_files,
            "total_notes": total_notes_count,
            "total_cards": total_notes_count,
            "extracted_media_count": extracted_media_count,
            "output_dir": output_dir
        }


def split_markdown_deck(
    md_file_path: str,
    chunk_size: int = 500,
    output_dir: Optional[str] = None,
    by_level: bool = False,
    keep_original: bool = True
) -> Dict[str, Any]:
    """
    Split a large monolithic markdown deck file into modular chapter files (e.g. 500 cards each).
    Each chapter file is fully self-contained, keeps asset references intact, and avoids triggering
    the Massive File Shield so it can be browsed, read in double-page mode, and studied in full.
    """
    if not os.path.isfile(md_file_path):
        raise FileNotFoundError(f"Deck file not found: {md_file_path}")

    with open(md_file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split into header and cards
    card_pattern = r'\n(?=#{1,6}\s+(?:\d+\.\s+|[^\n]+))'
    parts = re.split(card_pattern, content)
    if len(parts) <= 1:
        parts = content.split('\n---\n')

    first_part = parts[0]
    if re.search(r'^\s*#{1,6}\s+\d+\.\s+', first_part, re.MULTILINE):
        header_text = ""
        card_blocks = parts
    else:
        header_text = first_part.strip()
        card_blocks = parts[1:]

    total_cards = len(card_blocks)
    if total_cards <= chunk_size and not by_level:
        return {
            "status": "ok",
            "message": f"File has only {total_cards} cards, which is already under chunk size ({chunk_size}).",
            "total_cards": total_cards,
            "files_created": []
        }

    target_dir = os.path.abspath(output_dir or os.path.dirname(md_file_path))
    os.makedirs(target_dir, exist_ok=True)

    deck_title = "Deck"
    m_title = re.search(r'^\s*#\s+([^\n\r]+)', header_text)
    if m_title:
        deck_title = m_title.group(1).strip()
    else:
        deck_title = os.path.splitext(os.path.basename(md_file_path))[0]

    files_created = []

    if by_level:
        levels: Dict[str, List[str]] = {}
        for c in card_blocks:
            m_lvl = re.search(r'\*\*Level:\*\*\s*([^\n\r]+)', c)
            lvl = m_lvl.group(1).strip() if m_lvl else "Uncategorized"
            levels.setdefault(lvl, []).append(c)

        part_idx = 1
        for lvl_name, lvl_cards in levels.items():
            safe_lvl = sanitize_filename(lvl_name)
            sub_chunks = []
            curr = 0
            while curr < len(lvl_cards):
                end = min(len(lvl_cards), curr + chunk_size)
                if 0 < (len(lvl_cards) - end) < max(20, chunk_size // 6):
                    end = len(lvl_cards)
                sub_chunks.append((curr, end))
                curr = end

            for s_idx, (s_start, s_end) in enumerate(sub_chunks):
                chunk_c = lvl_cards[s_start:s_end]
                sub_suffix = f"_Part_{s_idx + 1}" if len(sub_chunks) > 1 else ""
                fname = f"{part_idx:02d}_{safe_lvl}{sub_suffix}_({len(chunk_c)}_cards).md"
                out_path = os.path.join(target_dir, fname)

                chunk_lines = [
                    f"# {deck_title} - Level {lvl_name}{sub_suffix} ({len(chunk_c)} cards)",
                    "",
                    f"> Level **{lvl_name}** ({len(chunk_c)} cards) from **{deck_title}**.",
                    "",
                    '\n'.join(c.strip() for c in chunk_c if c.strip()),
                    ""
                ]
                with open(out_path, 'w', encoding='utf-8') as out_f:
                    out_f.write('\n'.join(chunk_lines))

                files_created.append({
                    "filename": fname,
                    "path": out_path,
                    "cards_count": len(chunk_c),
                    "level": lvl_name
                })
                part_idx += 1
    else:
        chunk_ranges = []
        curr = 0
        while curr < total_cards:
            end = min(total_cards, curr + chunk_size)
            if 0 < (total_cards - end) < max(20, chunk_size // 6):
                end = total_cards
            chunk_ranges.append((curr, end))
            curr = end

        digits = 4 if total_cards >= 1000 else 3

        for idx, (start_idx, end_idx) in enumerate(chunk_ranges):
            cards_in_chunk = card_blocks[start_idx:end_idx]
            card_start_num = start_idx + 1
            card_end_num = end_idx
            part_num = idx + 1

            fname = f"{part_num:02d}_Rank_{card_start_num:0{digits}d}-{card_end_num:0{digits}d}.md"
            out_path = os.path.join(target_dir, fname)

            chunk_lines = [
                f"# {deck_title} - Part {part_num} (Cards {card_start_num}–{card_end_num})",
                "",
                f"> Cards **{card_start_num}** to **{card_end_num}** of **{deck_title}** ({len(cards_in_chunk)} cards).",
                "",
                '\n'.join(c.strip() for c in cards_in_chunk if c.strip()),
                ""
            ]

            with open(out_path, 'w', encoding='utf-8') as out_f:
                out_f.write('\n'.join(chunk_lines))

            files_created.append({
                "filename": fname,
                "path": out_path,
                "cards_count": len(cards_in_chunk),
                "start_card": card_start_num,
                "end_card": card_end_num
            })

    orig_dir = os.path.dirname(os.path.abspath(md_file_path))
    if os.path.abspath(target_dir) == orig_dir and keep_original:
        full_backup_dir = os.path.join(target_dir, "_full_deck")
        os.makedirs(full_backup_dir, exist_ok=True)
        backup_path = os.path.join(full_backup_dir, os.path.basename(md_file_path))
        if os.path.abspath(md_file_path) != os.path.abspath(backup_path) and os.path.isfile(md_file_path):
            try:
                shutil.move(md_file_path, backup_path)
            except Exception:
                pass

    return {
        "status": "ok",
        "total_cards": total_cards,
        "chunk_size": chunk_size,
        "parts_count": len(files_created),
        "files_created": files_created,
        "target_dir": target_dir
    }
