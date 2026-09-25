# mdviewer

`mdviewer` is a fast, lightweight, and local Markdown Outline Reader that spins up a local server to let you view your markdown files right from your browser, securely and efficiently. It automatically loads a sidebar with the file structure of your current directory.

## Features

- **Fast Markdown Rendering**: Renders Markdown quickly and clearly with full outline views and interactive flashcard review mode.
- **Sidebar File Explorer**: Automatically browses and explores markdown files with right-click context actions.
- **In-Browser Sandboxed Terminal**: An isolated, browser-embedded CLI (press `` ` `` or click `🖥️ Terminal`) with zero dependencies on host OS terminals. Supports `ls`, `cd`, `pwd`, `cat`, `hx`/`edit`, `diff`, `accept`, `discard`, `status`, `touch`, `mkdir`, and `help`.
- **Staging Buffer Editing**: Opening or editing files creates an isolated staging buffer (`~/.mdviewer_buffers/`). Original vault files on disk are **never touched or overwritten** until you review the diff and explicitly choose to **Accept & Replace**.
- **Strict Security Isolation**: Strict directory boundary checking (`safe_rel_path`) blocks all path-traversal attempts outside the served workspace.
- **Zero External Dependencies**: Relies solely on Python's built-in standard library (`http.server`, `urllib`, `difflib`).
- **Fully Local & Offline**: Operates completely local without network access.

## Installation

You can install `mdviewer` using `uv` (or `pip`):

```bash
uv tool install .
# or
pip install .
```

## Usage

Navigate to any directory with Markdown files and run:

```bash
mdviewer
```

This will spin up a local server on port `2026` (or a random port if `2026` is in use) and automatically open it in your default web browser.

### In-Browser Terminal & Staging Buffer Commands

| Command | Action |
| --- | --- |
| `` ` `` *(backtick)* | Toggle in-browser sandboxed terminal drawer |
| `hx <file>` or `edit <file>` | Open file in the built-in staging buffer modal |
| `diff [file]` | Review unified diff between staged buffer and original disk file |
| `accept <file>` | Explicitly apply buffer changes to original disk file |
| `discard <file>` | Discard staged changes without modifying original file |
| `status` | List all active staging buffers awaiting acceptance |
### Flashcard AI Assistant, Multi-Version & Learning Mode

| Key / Control | Action |
| --- | --- |
| `Space` / `W` / `Enter` | Flip flashcard between front and back |
| `T` | **Swap AI Supplement to Card Back** (toggle between original markdown and AI supplement for learning) |
| `I` | Toggle AI Assistant side panel |
| `O` | Toggle Cards Overview and Search panel |
| `C` | Toggle 2-Column page view vs 1-Column scroll |
| `F` | Toggle Fullscreen mode |
| `🎴 Folder Deck` | **Study Entire Folder as a Deck**: Right-click any folder or click `🎴 Folder Deck` to open all files at a chosen heading level (H1, H2, H3, or All) as a massive deck (e.g. 4,337 cards in milliseconds) |
| `📁 Folder All` | **Generate All Files in Folder**: Right-click any folder $\rightarrow$ `⚡ Generate All in Folder...` or click `📁 Folder All` in the AI panel to generate AI supplements across all files in the current folder at once (concurrency up to 1000) |
| `⚡ Generate` | **Real-Time Streaming & Live Thinking**: Zero artificial timeout; streams SSE tokens live with collapsible thinking process box displaying duration and model reasoning |
| `⏹ Stop` | Cancel in-flight generation cleanly at any time |
| `🚀 All` | Generate AI supplements for **all** cards in outline or folder concurrently (up to 1000 workers) |
| `➕ New Ver` | Generate and store a new version for the current prompt without overwriting prior outputs |
| Prompt Chips | Switch between different prompts generated on the card (e.g. Detailed, Vocabulary, Mnemonics, Quiz) |
| Back View Tabs | Toggle between `📄 Original` section markdown and `✨ AI Supplement` directly on the card back |
| Back Sub-Bar | Switch prompts and versions right on the card back while studying |

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for more information.
