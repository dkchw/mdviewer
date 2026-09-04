# mdviewer

`mdviewer` is a fast, lightweight, and local Markdown Outline Reader that spins up a local server to let you view your markdown files right from your browser, securely and efficiently. It automatically loads a sidebar with the file structure of your current directory.

## Features

- **Fast Markdown Rendering**: Renders Markdown quickly and clearly.
- **Sidebar File Explorer**: Automatically browses and explores the markdown files in the directory you run the command in. No more manually selecting folders or authorizing permissions!
- **Zero Dependencies**: Relies solely on Python's built-in standard library (`http.server` and `urllib`).
- **Fully Local**: Works completely offline.

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

This will spin up a local server on port `2024` (or a random port if `2024` is in use) and automatically open it in your default web browser. 

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for more information.
