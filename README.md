# mdviewer

**Ultra-fast Markdown Workstation** — a standalone, offline-first markdown reader, editor, and flashcard study tool powered by a native Rust rendering core.

## Features

### Three Unified Modes

| Mode | Shortcut | Description |
| :--- | :---: | :--- |
| **📋 Outline** | `1` | Fast collapsible outline reader with heading-level expansion |
| **📖 Document** | `2` | Full rendered document view with Obsidian-grade editing |
| **🎴 Flashcards** | `3` | Heading-based flashcard study mode with AI supplements |

### Document Mode — Obsidian-Style Editing
- **📖 Reading View**: Rendered GitHub-style prose, double-page book layout, TOC sidebar, interactive checkboxes synced to disk
- **⚡ Live Preview**: Side-by-side split editor with real-time rendered preview (Rust engine, sub-3ms), synchronized scrolling, KaTeX math, Mermaid diagrams, Obsidian callouts
- **📝 Source Editor**: Full-width focused markdown authoring with line numbers
- **`Ctrl+E`** toggles between Reading and Edit views (Obsidian muscle-memory)
- **Smart Editing**: Auto-indent, list continuation (`- [ ]`, `-`, `1.`, `>`), Tab/Shift+Tab indent, bracket auto-close, full formatting toolbar
- **Auto-Save**: Debounced auto-save to disk with `Ctrl+S` instant save

### Flashcard Mode — AI-Powered Study
- Study any heading level as flashcard decks (file or entire folder)
- AI supplement generation via OpenRouter or local Ollama with streaming
- Multi-version prompt management, batch generation (up to 1000 concurrent)
- Anki `.apkg` import with audio/image media support
- Audio playback with speed control and auto-play

### Core Architecture
- **Rust Rendering Core** (`mdviewer_core`): Native binary for sub-10ms library indexing, outline parsing, and markdown-to-HTML rendering with callout, task list, and code fence support
- **Python Backend** (`__main__.py`): HTTP server with file management, document rendering API, AI generation orchestration, and Anki import
- **Single-File Frontend** (`index.html`): Zero-framework SPA with Tokyo Night theme

### Additional Features
- **In-Place Workspace (0 Duplication)**: Open and work directly in your existing notes directory. All edits, saves, and checklists write to your disk files in-place without duplicating anything.
- **Distrobox & Container Path Mapping**: Built-in support for running inside Distrobox/Docker/Podman with auto-detected `/run/host` path prefix, configurable via UI modal, CLI `--prefix`, or `MDVIEWER_PATH_PREFIX`.
- **Sidebar File Explorer**: Browse, create, rename, delete files and folders with right-click context menus
- **In-Browser Terminal**: Sandboxed CLI with `ls`, `cd`, `cat`, `edit`, `diff`, `accept`, `discard` commands
- **Workspace Search**: `Ctrl+Shift+F` full-text search across all files
- **Zero External Dependencies**: Python standard library only (no pip packages required)
- **Fully Local & Offline**: No network access needed, no telemetry

## Installation

```bash
# Install with uv
uv tool install .

# Or with pip
pip install .
```

### Building the Rust Core (optional, for maximum performance)

```bash
cd crates/mdviewer_core
cargo build --release
cp target/release/mdviewer_core ../../src/mdviewer/bin/
```

## Usage

```bash
# Standalone mode (opens last active workspace or default vault)
mdviewer

# Open a specific folder directly in-place
mdviewer /path/to/your/notes

# Running in Distrobox with host path prefix
mdviewer --prefix /run/host /home/user/Documents/Notes

# Custom port
mdviewer --port 8080 /path/to/notes

# Import an Anki deck (.apkg)
mdviewer import-anki deck.apkg -o ./output
```

The server starts on port `2112` (or auto-selects a free port) and opens in your default browser.

## Keyboard Shortcuts

| Key | Action |
| :--- | :--- |
| `1` / `2` / `3` | Switch mode: Outline / Document / Flashcards |
| `Ctrl+E` | Toggle between Reading View and Edit View |
| `Ctrl+S` | Save current document to disk |
| `Ctrl+F` | Search in current file |
| `Ctrl+Shift+F` | Search across all files |
| `` ` `` | Toggle in-browser terminal |
| `Space` / `Enter` | Flip flashcard |
| `←` `→` | Previous / next flashcard |
| `F` | Toggle fullscreen |
| `Tab` | Indent (in editor) |
| `Shift+Tab` | Outdent (in editor) |

## License

Apache License 2.0 — see [LICENSE](LICENSE).
