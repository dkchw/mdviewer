use std::collections::HashSet;
use std::env;
use std::fs;
use std::io::{self, Read};
use std::path::Path;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use pulldown_cmark::{html, Options, Parser};
use rayon::prelude::*;
use regex::Regex;
use serde::{Deserialize, Serialize};
use walkdir::WalkDir;

#[derive(Serialize, Deserialize, Debug)]
struct LibraryFileInfo {
    rel_path: String,
    name: String,
    title: String,
    size: u64,
    mtime: u64,
    line_count: usize,
    card_count: usize,
    has_audio: bool,
    has_image: bool,
}

#[derive(Serialize, Deserialize, Debug)]
struct LibraryIndexResult {
    status: String,
    library_path: String,
    total_files: usize,
    total_cards: usize,
    total_folders: usize,
    files: Vec<LibraryFileInfo>,
    folders: Vec<String>,
    scan_duration_ms: f64,
    engine: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct HeadingInfo {
    line: usize,
    level: usize,
    text: String,
    slug: String,
    end: usize,
}

#[derive(Serialize, Deserialize, Debug)]
struct CardInfo {
    line: usize,
    level: usize,
    text: String,
    slug: String,
    end: usize,
    card_content: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct ParseResult {
    status: String,
    file_path: String,
    total_lines: usize,
    headings: Vec<HeadingInfo>,
    cards: Vec<CardInfo>,
    parse_duration_ms: f64,
}

#[derive(Serialize, Deserialize, Debug)]
struct RenderResult {
    status: String,
    html: String,
    toc: Vec<HeadingInfo>,
    render_duration_ms: f64,
}

#[derive(Serialize, Deserialize, Debug)]
struct SearchMatch {
    rel_path: String,
    file_name: String,
    line: usize,
    line_text: String,
    is_heading: bool,
    level: usize,
}

#[derive(Serialize, Deserialize, Debug)]
struct SearchResult {
    status: String,
    query: String,
    total_matches: usize,
    matches: Vec<SearchMatch>,
    duration_ms: f64,
}

#[derive(Serialize, Deserialize, Debug)]
struct ImportFolderResult {
    status: String,
    src_dir: String,
    dst_dir: String,
    files_copied: usize,
    assets_copied: usize,
    total_cards: usize,
    imported_files: Vec<String>,
    duration_ms: f64,
}

fn is_ignored_dir(name: &str) -> bool {
    name.starts_with('.') || name == "node_modules" || name == ".venv" || name == "__pycache__" || name == "target" || name == "dist"
}

fn index_library(lib_path: &Path) -> LibraryIndexResult {
    let t0 = Instant::now();
    let abs_lib = fs::canonicalize(lib_path).unwrap_or_else(|_| lib_path.to_path_buf());

    let mut md_files = Vec::new();
    let mut folders_set = HashSet::new();

    for entry in WalkDir::new(&abs_lib)
        .into_iter()
        .filter_entry(|e| !is_ignored_dir(e.file_name().to_str().unwrap_or("")))
        .filter_map(|e| e.ok())
    {
        let path = entry.path();
        if path.is_dir() {
            if let Ok(rel) = path.strip_prefix(&abs_lib) {
                let rel_str = rel.to_string_lossy().replace('\\', "/");
                if !rel_str.is_empty() {
                    folders_set.insert(rel_str);
                }
            }
        } else if path.is_file() {
            let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("").to_lowercase();
            if ext == "md" || ext == "markdown" {
                md_files.push(path.to_path_buf());
            }
        }
    }

    let total_cards_counter = AtomicUsize::new(0);

    let mut file_infos: Vec<LibraryFileInfo> = md_files
        .par_iter()
        .filter_map(|path| {
            let meta = fs::metadata(path).ok()?;
            let size = meta.len();
            let mtime = meta
                .modified()
                .ok()?
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs())
                .unwrap_or(0);

            let content = fs::read_to_string(path).unwrap_or_default();
            let mut line_count = 0;
            let mut card_count = 0;
            let mut first_heading = String::new();
            let mut in_code_block = false;
            let mut has_audio = false;
            let mut has_image = false;

            for line in content.lines() {
                line_count += 1;
                let trimmed = line.trim();
                if trimmed.starts_with("```") {
                    in_code_block = !in_code_block;
                    continue;
                }
                if !in_code_block && trimmed.starts_with('#') {
                    let mut hashes = 0;
                    for ch in trimmed.chars() {
                        if ch == '#' {
                            hashes += 1;
                        } else {
                            break;
                        }
                    }
                    if hashes >= 1 && hashes <= 6 {
                        card_count += 1;
                        if first_heading.is_empty() {
                            first_heading = trimmed[hashes..].trim().to_string();
                        }
                    }
                }
                if !has_audio && (line.contains("![audio]") || line.contains("[sound:") || line.contains(".mp3") || line.contains(".wav")) {
                    has_audio = true;
                }
                if !has_image && (line.contains("![image]") || line.contains("<img") || line.contains("<IMG") || line.contains(".png") || line.contains(".jpg")) {
                    has_image = true;
                }
            }

            total_cards_counter.fetch_add(card_count, Ordering::Relaxed);

            let rel = path.strip_prefix(&abs_lib).unwrap_or(path);
            let rel_path = rel.to_string_lossy().replace('\\', "/");
            let name = path.file_name().and_then(|s| s.to_str()).unwrap_or("").to_string();
            let title = if !first_heading.is_empty() {
                first_heading
            } else {
                path.file_stem().and_then(|s| s.to_str()).unwrap_or(&name).to_string()
            };

            Some(LibraryFileInfo {
                rel_path,
                name,
                title,
                size,
                mtime,
                line_count,
                card_count,
                has_audio,
                has_image,
            })
        })
        .collect();

    file_infos.sort_by(|a, b| a.rel_path.cmp(&b.rel_path));
    let mut folders: Vec<String> = folders_set.into_iter().collect();
    folders.sort();

    let duration_ms = t0.elapsed().as_secs_f64() * 1000.0;
    let total_cards = total_cards_counter.load(Ordering::Relaxed);

    LibraryIndexResult {
        status: "ok".to_string(),
        library_path: abs_lib.to_string_lossy().to_string(),
        total_files: file_infos.len(),
        total_cards,
        total_folders: folders.len(),
        files: file_infos,
        folders,
        scan_duration_ms: duration_ms,
        engine: "Rust mdviewer_core (SIMD & Rayon)".to_string(),
    }
}

fn parse_file(path: &Path) -> Result<ParseResult, io::Error> {
    let t0 = Instant::now();
    let content = fs::read_to_string(path)?;
    let lines: Vec<&str> = content.lines().collect();
    let total_lines = lines.len();

    let mut in_code_block = false;
    let mut raw_headings = Vec::new();

    for (idx, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if trimmed.starts_with("```") {
            in_code_block = !in_code_block;
            continue;
        }
        if !in_code_block && trimmed.starts_with('#') {
            let mut hashes = 0;
            for ch in trimmed.chars() {
                if ch == '#' {
                    hashes += 1;
                } else {
                    break;
                }
            }
            if hashes >= 1 && hashes <= 6 && trimmed.chars().nth(hashes).map(|c| c.is_whitespace()).unwrap_or(false) {
                let text = trimmed[hashes..].trim().to_string();
                let slug = format!("H{}::{}", hashes, text);
                raw_headings.push((idx, hashes, text, slug));
            }
        }
    }

    let mut headings = Vec::new();
    let mut cards = Vec::new();

    for i in 0..raw_headings.len() {
        let (line_idx, level, ref text, ref slug) = raw_headings[i];
        let end_idx = if i + 1 < raw_headings.len() {
            raw_headings[i + 1].0.saturating_sub(1)
        } else {
            total_lines.saturating_sub(1)
        };

        headings.push(HeadingInfo {
            line: line_idx,
            level,
            text: text.clone(),
            slug: slug.clone(),
            end: end_idx,
        });

        let card_body = if line_idx + 1 <= end_idx && end_idx < total_lines {
            lines[line_idx + 1..=end_idx].join("\n")
        } else {
            String::new()
        };

        cards.push(CardInfo {
            line: line_idx,
            level,
            text: text.clone(),
            slug: slug.clone(),
            end: end_idx,
            card_content: card_body,
        });
    }

    let duration_ms = t0.elapsed().as_secs_f64() * 1000.0;

    Ok(ParseResult {
        status: "ok".to_string(),
        file_path: path.to_string_lossy().to_string(),
        total_lines,
        headings,
        cards,
        parse_duration_ms: duration_ms,
    })
}

fn render_markdown_to_html(markdown_str: &str) -> RenderResult {
    let t0 = Instant::now();

    // Collect TOC headings
    let mut toc = Vec::new();
    let mut in_code_block = false;
    for (line_idx, line) in markdown_str.lines().enumerate() {
        let trimmed = line.trim();
        if trimmed.starts_with("```") {
            in_code_block = !in_code_block;
            continue;
        }
        if !in_code_block && trimmed.starts_with('#') {
            let mut hashes = 0;
            for ch in trimmed.chars() {
                if ch == '#' {
                    hashes += 1;
                } else {
                    break;
                }
            }
            if hashes >= 1 && hashes <= 6 && trimmed.chars().nth(hashes).map(|c| c.is_whitespace()).unwrap_or(false) {
                let text = trimmed[hashes..].trim().to_string();
                let slug = format!("H{}::{}", hashes, text);
                toc.push(HeadingInfo {
                    line: line_idx,
                    level: hashes,
                    text,
                    slug,
                    end: line_idx,
                });
            }
        }
    }

    // Set up pulldown-cmark parser options
    let mut options = Options::empty();
    options.insert(Options::ENABLE_TABLES);
    options.insert(Options::ENABLE_FOOTNOTES);
    options.insert(Options::ENABLE_STRIKETHROUGH);
    options.insert(Options::ENABLE_TASKLISTS);
    options.insert(Options::ENABLE_HEADING_ATTRIBUTES);

    // Pre-process Obsidian embeds ![[...]] and wikilinks [[...]] before markdown parser
    let re_embed = Regex::new(r#"!\[\[(.*?)\]\]"#).unwrap();
    let preprocessed_embeds = re_embed.replace_all(markdown_str, |caps: &regex::Captures| {
        let inner = caps.get(1).map(|m| m.as_str().trim()).unwrap_or("");
        let lower = inner.to_lowercase();
        if lower.ends_with(".png") || lower.ends_with(".jpg") || lower.ends_with(".jpeg") || lower.ends_with(".gif") || lower.ends_with(".webp") || lower.ends_with(".svg") {
            format!("![{}]({})", inner, inner)
        } else if lower.ends_with(".mp3") || lower.ends_with(".wav") || lower.ends_with(".ogg") || lower.ends_with(".m4a") {
            format!("<audio controls class=\"markdown-audio\" src=\"{}\"></audio>", inner)
        } else {
            format!("[{}]({})", inner, inner)
        }
    });

    let line_starts: Vec<usize> = std::iter::once(0)
        .chain(markdown_str.match_indices('\n').map(|(i, _)| i + 1))
        .collect();

    let get_line_num = |offset: usize| -> usize {
        match line_starts.binary_search(&offset) {
            Ok(idx) => idx + 1,
            Err(idx) => idx,
        }
    };

    let parser = Parser::new_ext(&preprocessed_embeds, options);
    let mut transformed_events = Vec::new();

    for (event, range) in parser.into_offset_iter() {
        let line_num = get_line_num(range.start);
        match event {
            pulldown_cmark::Event::Start(pulldown_cmark::Tag::Paragraph) => {
                transformed_events.push(pulldown_cmark::Event::Html(format!("<p data-line=\"{}\">", line_num).into()));
            }
            pulldown_cmark::Event::End(pulldown_cmark::TagEnd::Paragraph) => {
                transformed_events.push(pulldown_cmark::Event::Html("</p>\n".into()));
            }
            pulldown_cmark::Event::Start(pulldown_cmark::Tag::Heading { level, id, .. }) => {
                let id_attr = id.map(|s| format!(" id=\"{}\"", s)).unwrap_or_default();
                transformed_events.push(pulldown_cmark::Event::Html(format!("<h{} data-line=\"{}\"{}>", level as usize, line_num, id_attr).into()));
            }
            pulldown_cmark::Event::End(pulldown_cmark::TagEnd::Heading(level)) => {
                transformed_events.push(pulldown_cmark::Event::Html(format!("</h{}>\n", level as usize).into()));
            }
            pulldown_cmark::Event::Start(pulldown_cmark::Tag::BlockQuote(..)) => {
                transformed_events.push(pulldown_cmark::Event::Html(format!("<blockquote data-line=\"{}\">", line_num).into()));
            }
            pulldown_cmark::Event::End(pulldown_cmark::TagEnd::BlockQuote(..)) => {
                transformed_events.push(pulldown_cmark::Event::Html("</blockquote>\n".into()));
            }
            pulldown_cmark::Event::Start(pulldown_cmark::Tag::Item) => {
                transformed_events.push(pulldown_cmark::Event::Html(format!("<li data-line=\"{}\">", line_num).into()));
            }
            pulldown_cmark::Event::End(pulldown_cmark::TagEnd::Item) => {
                transformed_events.push(pulldown_cmark::Event::Html("</li>\n".into()));
            }
            pulldown_cmark::Event::Start(pulldown_cmark::Tag::Table(..)) => {
                transformed_events.push(pulldown_cmark::Event::Html(format!("<table data-line=\"{}\">", line_num).into()));
            }
            pulldown_cmark::Event::End(pulldown_cmark::TagEnd::Table) => {
                transformed_events.push(pulldown_cmark::Event::Html("</table>\n".into()));
            }
            pulldown_cmark::Event::Start(pulldown_cmark::Tag::CodeBlock(ref kind)) => {
                let class_attr = match kind {
                    pulldown_cmark::CodeBlockKind::Fenced(lang) if !lang.is_empty() => format!(" class=\"language-{}\"", lang),
                    _ => String::new(),
                };
                transformed_events.push(pulldown_cmark::Event::Html(format!("<pre data-line=\"{}\"><code{}>", line_num, class_attr).into()));
            }
            pulldown_cmark::Event::End(pulldown_cmark::TagEnd::CodeBlock) => {
                transformed_events.push(pulldown_cmark::Event::Html("</code></pre>\n".into()));
            }
            other => transformed_events.push(other),
        }
    }

    let mut html_output = String::with_capacity(markdown_str.len() * 3 / 2);
    html::push_html(&mut html_output, transformed_events.into_iter());

    // Post-process Obsidian highlights ==text== -> <mark>text</mark>
    let re_mark = Regex::new(r"==([^=]+)==").unwrap();
    let processed_mark = re_mark.replace_all(&html_output, "<mark>$1</mark>");

    // Make task list checkboxes interactive with sequential data-idx
    let re_cb = Regex::new(r#"<input\s+[^>]*?type="checkbox"[^>]*?/?>"#).unwrap();
    let mut cb_counter = 0;
    let processed_cb = re_cb.replace_all(&processed_mark, |caps: &regex::Captures| {
        let whole = caps.get(0).map(|m| m.as_str()).unwrap_or("");
        let is_checked = whole.contains("checked");
        let checked_str = if is_checked { " checked" } else { "" };
        let out = format!(r#"<input type="checkbox" class="task-checkbox" data-idx="{}"{}>"#, cb_counter, checked_str);
        cb_counter += 1;
        out
    });

    // Post-process wikilinks [[Page]] or [[Page|Display]]
    let re_wiki = Regex::new(r#"\[\[([^\]\|]+)(?:\|([^\]]+))?\]\]"#).unwrap();
    let processed_wiki = re_wiki.replace_all(&processed_cb, |caps: &regex::Captures| {
        let target = caps.get(1).map(|m| m.as_str().trim()).unwrap_or("");
        let display = caps.get(2).map(|m| m.as_str().trim()).unwrap_or(target);
        format!(r#"<a href="javascript:void(0)" class="internal-link" onclick="openFileByTarget('{}')">{}</a>"#, target, display)
    });

    // Post-process callouts > [!NOTE], > [!TIP], > [!WARNING], > [!IMPORTANT], > [!CAUTION]
    let re_callout = Regex::new(r#"(?s)<blockquote(?:\s+data-line="(\d+)")?>\s*<p(?:\s+data-line="\d+")?>\[!([A-Za-z_-]+)\][ \t]*(.*?)(?:</p>|\n)(.*?)</blockquote>"#).unwrap();
    let final_html = re_callout.replace_all(&processed_wiki, |caps: &regex::Captures| {
        let line_attr = caps.get(1).map(|m| format!(" data-line=\"{}\"", m.as_str())).unwrap_or_default();
        let kind = caps.get(2).map(|m| m.as_str().to_lowercase()).unwrap_or_else(|| "note".to_string());
        let raw_title = caps.get(3).map(|m| m.as_str().trim()).unwrap_or("");
        let body = caps.get(4).map(|m| m.as_str().trim()).unwrap_or("");
        let title = if !raw_title.is_empty() {
            raw_title.to_string()
        } else {
            let mut c = kind.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
            }
        };
        let icon = match kind.as_str() {
            "tip" | "hint" => "💡",
            "warning" | "caution" | "attention" => "⚠️",
            "danger" | "error" | "bug" => "⚡",
            "important" | "fire" => "🔥",
            "question" | "help" | "faq" => "❓",
            "success" | "check" | "done" => "✔️",
            "example" => "📝",
            "quote" | "cite" => "💬",
            _ => "ℹ️",
        };
        let content_html = if body.is_empty() {
            String::new()
        } else if body.starts_with("<p>") {
            body.to_string()
        } else {
            format!("<p>{}</p>", body.replace("</p>", ""))
        };
        format!(
            r#"<div class="callout callout-{}"{}><div class="callout-title"><span class="callout-icon">{}</span> <span class="callout-title-inner">{}</span></div><div class="callout-content">{}</div></div>"#,
            kind, line_attr, icon, title, content_html
        )
    });

    let duration_ms = t0.elapsed().as_secs_f64() * 1000.0;

    RenderResult {
        status: "ok".to_string(),
        html: final_html.into_owned(),
        toc,
        render_duration_ms: duration_ms,
    }
}

fn search_library(lib_path: &Path, query: &str) -> SearchResult {
    let t0 = Instant::now();
    let abs_lib = fs::canonicalize(lib_path).unwrap_or_else(|_| lib_path.to_path_buf());
    let query_lower = query.to_lowercase();

    let mut md_files = Vec::new();
    for entry in WalkDir::new(&abs_lib)
        .into_iter()
        .filter_entry(|e| !is_ignored_dir(e.file_name().to_str().unwrap_or("")))
        .filter_map(|e| e.ok())
    {
        let path = entry.path();
        if path.is_file() {
            let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("").to_lowercase();
            if ext == "md" || ext == "markdown" {
                md_files.push(path.to_path_buf());
            }
        }
    }

    let matches: Vec<SearchMatch> = md_files
        .par_iter()
        .flat_map(|path| {
            let mut file_matches = Vec::new();
            if let Ok(content) = fs::read_to_string(path) {
                let rel = path.strip_prefix(&abs_lib).unwrap_or(path);
                let rel_path = rel.to_string_lossy().replace('\\', "/");
                let file_name = path.file_name().and_then(|s| s.to_str()).unwrap_or("").to_string();

                for (idx, line) in content.lines().enumerate() {
                    if line.to_lowercase().contains(&query_lower) {
                        let trimmed = line.trim();
                        let is_heading = trimmed.starts_with('#');
                        let mut level = 0;
                        if is_heading {
                            for ch in trimmed.chars() {
                                if ch == '#' {
                                    level += 1;
                                } else {
                                    break;
                                }
                            }
                        }
                        file_matches.push(SearchMatch {
                            rel_path: rel_path.clone(),
                            file_name: file_name.clone(),
                            line: idx + 1,
                            line_text: trimmed.chars().take(180).collect(),
                            is_heading,
                            level,
                        });
                    }
                }
            }
            file_matches
        })
        .collect();

    let duration_ms = t0.elapsed().as_secs_f64() * 1000.0;
    let total_matches = matches.len();

    SearchResult {
        status: "ok".to_string(),
        query: query.to_string(),
        total_matches,
        matches,
        duration_ms,
    }
}

fn import_folder(src_dir: &Path, dst_dir: &Path) -> Result<ImportFolderResult, io::Error> {
    let t0 = Instant::now();
    let abs_src = fs::canonicalize(src_dir)?;
    fs::create_dir_all(dst_dir)?;
    let abs_dst = fs::canonicalize(dst_dir)?;

    let mut files_to_copy = Vec::new();
    for entry in WalkDir::new(&abs_src)
        .into_iter()
        .filter_entry(|e| !is_ignored_dir(e.file_name().to_str().unwrap_or("")))
        .filter_map(|e| e.ok())
    {
        let path = entry.path();
        if path.is_file() {
            files_to_copy.push(path.to_path_buf());
        }
    }

    let files_copied = AtomicUsize::new(0);
    let assets_copied = AtomicUsize::new(0);
    let total_cards = AtomicUsize::new(0);

    let imported_files: Vec<String> = files_to_copy
        .par_iter()
        .filter_map(|src_path| {
            let rel = src_path.strip_prefix(&abs_src).ok()?;
            let target_path = abs_dst.join(rel);

            if let Some(parent) = target_path.parent() {
                let _ = fs::create_dir_all(parent);
            }

            if fs::copy(src_path, &target_path).is_ok() {
                let ext = target_path
                    .extension()
                    .and_then(|s| s.to_str())
                    .unwrap_or("")
                    .to_lowercase();
                if ext == "md" || ext == "markdown" {
                    files_copied.fetch_add(1, Ordering::Relaxed);
                    // Fast count headings in imported markdown
                    if let Ok(content) = fs::read_to_string(&target_path) {
                        let cards = content
                            .lines()
                            .filter(|l| {
                                let t = l.trim();
                                t.starts_with("# ")
                                    || t.starts_with("## ")
                                    || t.starts_with("### ")
                                    || t.starts_with("#### ")
                                    || t.starts_with("##### ")
                                    || t.starts_with("###### ")
                            })
                            .count();
                        total_cards.fetch_add(cards, Ordering::Relaxed);
                    }
                    Some(rel.to_string_lossy().replace('\\', "/"))
                } else {
                    assets_copied.fetch_add(1, Ordering::Relaxed);
                    None
                }
            } else {
                None
            }
        })
        .collect();

    let duration_ms = t0.elapsed().as_secs_f64() * 1000.0;

    Ok(ImportFolderResult {
        status: "ok".to_string(),
        src_dir: abs_src.to_string_lossy().to_string(),
        dst_dir: abs_dst.to_string_lossy().to_string(),
        files_copied: files_copied.load(Ordering::Relaxed),
        assets_copied: assets_copied.load(Ordering::Relaxed),
        total_cards: total_cards.load(Ordering::Relaxed),
        imported_files,
        duration_ms,
    })
}

#[derive(Serialize, Deserialize, Debug)]
struct TreeEntry {
    name: String,
    kind: String,
    size: u64,
    mtime: u64,
}

#[derive(Serialize, Deserialize, Debug)]
struct TreeResult {
    status: String,
    path: String,
    entries: Vec<TreeEntry>,
    duration_ms: f64,
}

fn scan_tree(dir_path: &Path) -> TreeResult {
    let t0 = Instant::now();
    let mut entries = Vec::new();
    if let Ok(read_dir) = fs::read_dir(dir_path) {
        for entry in read_dir.flatten() {
            let file_name = entry.file_name().to_string_lossy().to_string();
            if file_name.starts_with('.') {
                continue;
            }
            if let Ok(ft) = entry.file_type() {
                if ft.is_dir() {
                    let low = file_name.to_lowercase();
                    if low == "node_modules" || low == ".obsidian" || low == ".vscode" || low == ".idea" || low == "target" || low == ".git" {
                        continue;
                    }
                    let mtime = entry.metadata().ok().and_then(|m| m.modified().ok())
                        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                        .map(|d| d.as_secs()).unwrap_or(0);
                    entries.push(TreeEntry {
                        name: file_name,
                        kind: "directory".to_string(),
                        size: 0,
                        mtime,
                    });
                } else if ft.is_file() {
                    let low = file_name.to_lowercase();
                    if low.ends_with(".md") || low.ends_with(".markdown") || low.ends_with(".txt") {
                        let meta = entry.metadata().ok();
                        let size = meta.as_ref().map(|m| m.len()).unwrap_or(0);
                        let mtime = meta.and_then(|m| m.modified().ok())
                            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                            .map(|d| d.as_secs()).unwrap_or(0);
                        entries.push(TreeEntry {
                            name: file_name,
                            kind: "file".to_string(),
                            size,
                            mtime,
                        });
                    }
                }
            }
        }
    }
    entries.sort_by(|a, b| {
        if a.kind != b.kind {
            if a.kind == "directory" { std::cmp::Ordering::Less } else { std::cmp::Ordering::Greater }
        } else {
            a.name.to_lowercase().cmp(&b.name.to_lowercase())
        }
    });
    TreeResult {
        status: "ok".to_string(),
        path: dir_path.to_string_lossy().to_string(),
        entries,
        duration_ms: t0.elapsed().as_secs_f64() * 1000.0,
    }
}

#[derive(Serialize, Deserialize, Debug)]
struct FileMetaResult {
    status: String,
    file_path: String,
    size_bytes: u64,
    total_lines: usize,
    is_massive: bool,
    recommended_chunk_size: usize,
    duration_ms: f64,
}

fn file_meta(file_path: &Path) -> Result<FileMetaResult, String> {
    let t0 = Instant::now();
    let metadata = fs::metadata(file_path).map_err(|e| e.to_string())?;
    let size_bytes = metadata.len();
    let file = fs::File::open(file_path).map_err(|e| e.to_string())?;
    let reader = io::BufReader::with_capacity(64 * 1024, file);
    use std::io::BufRead;
    let mut total_lines = 0;
    for _ in reader.lines() {
        total_lines += 1;
    }
    let is_massive = total_lines > 20_000 || size_bytes > 2 * 1024 * 1024;
    Ok(FileMetaResult {
        status: "ok".to_string(),
        file_path: file_path.to_string_lossy().to_string(),
        size_bytes,
        total_lines,
        is_massive,
        recommended_chunk_size: if is_massive { 1000 } else { total_lines },
        duration_ms: t0.elapsed().as_secs_f64() * 1000.0,
    })
}

#[derive(Serialize, Deserialize, Debug)]
struct ChunkResult {
    status: String,
    file_path: String,
    start_line: usize,
    count: usize,
    total_lines: usize,
    has_more: bool,
    lines: Vec<String>,
    content: String,
    duration_ms: f64,
}

fn read_file_chunk(file_path: &Path, start_line: usize, count: usize) -> Result<ChunkResult, String> {
    let t0 = Instant::now();
    let file = fs::File::open(file_path).map_err(|e| e.to_string())?;
    let reader = io::BufReader::with_capacity(64 * 1024, file);
    use std::io::BufRead;
    let mut chunk_lines = Vec::with_capacity(count);
    let mut total_lines = 0;
    for (idx, line_res) in reader.lines().enumerate() {
        let line_num = idx + 1; // 1-indexed
        total_lines += 1;
        if line_num >= start_line && line_num < start_line + count {
            if let Ok(l) = line_res {
                chunk_lines.push(l);
            }
        }
    }
    let actual_count = chunk_lines.len();
    let has_more = start_line + actual_count <= total_lines;
    let content = chunk_lines.join("\n");
    Ok(ChunkResult {
        status: "ok".to_string(),
        file_path: file_path.to_string_lossy().to_string(),
        start_line,
        count: actual_count,
        total_lines,
        has_more,
        lines: chunk_lines,
        content,
        duration_ms: t0.elapsed().as_secs_f64() * 1000.0,
    })
}

#[derive(Serialize, Deserialize, Debug)]
struct CountResult {
    status: String,
    path: String,
    md_count: usize,
    asset_count: usize,
    total_files: usize,
    duration_ms: f64,
}

fn fast_count_directory(dir_path: &Path) -> CountResult {
    let t0 = Instant::now();
    let md_count = AtomicUsize::new(0);
    let asset_count = AtomicUsize::new(0);
    let total_files = AtomicUsize::new(0);

    WalkDir::new(dir_path)
        .into_iter()
        .filter_entry(|e| {
            let name = e.file_name().to_string_lossy();
            if name.starts_with('.') && name != "." {
                return false;
            }
            let low = name.to_lowercase();
            if low == "node_modules" || low == ".obsidian" || low == ".vscode" || low == ".idea" || low == "target" || low == ".git" {
                return false;
            }
            true
        })
        .par_bridge()
        .for_each(|entry_res| {
            if let Ok(entry) = entry_res {
                if entry.file_type().is_file() {
                    total_files.fetch_add(1, Ordering::Relaxed);
                    let name = entry.file_name().to_string_lossy().to_lowercase();
                    if name.ends_with(".md") || name.ends_with(".markdown") || name.ends_with(".txt") {
                        md_count.fetch_add(1, Ordering::Relaxed);
                    } else if name.ends_with(".png") || name.ends_with(".jpg") || name.ends_with(".jpeg")
                        || name.ends_with(".gif") || name.ends_with(".svg") || name.ends_with(".webp")
                        || name.ends_with(".mp3") || name.ends_with(".m4a") || name.ends_with(".wav") || name.ends_with(".ogg") {
                        asset_count.fetch_add(1, Ordering::Relaxed);
                    }
                }
            }
        });

    CountResult {
        status: "ok".to_string(),
        path: dir_path.to_string_lossy().to_string(),
        md_count: md_count.load(Ordering::Relaxed),
        asset_count: asset_count.load(Ordering::Relaxed),
        total_files: total_files.load(Ordering::Relaxed),
        duration_ms: t0.elapsed().as_secs_f64() * 1000.0,
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        println!(
            "{{\"status\":\"error\",\"message\":\"Usage: mdviewer_core <index|parse|render|search|import-folder|tree|meta|chunk|count|version> [args]\"}}"
        );
        return;
    }

    match args[1].as_str() {
        "version" => {
            println!(
                "{{\"status\":\"ok\",\"version\":\"1.1.0\",\"engine\":\"mdviewer_core\",\"features\":[\"rayon_indexing\",\"simd_search\",\"pulldown_cmark\",\"parallel_importer\",\"fast_tree\",\"stream_chunker\",\"massive_shield\"]}}"
            );
        }
        "index" => {
            if args.len() < 3 {
                eprintln!("Error: missing library path for index command");
                std::process::exit(1);
            }
            let res = index_library(Path::new(&args[2]));
            println!("{}", serde_json::to_string(&res).unwrap());
        }
        "tree" => {
            if args.len() < 3 {
                eprintln!("Error: missing directory path for tree command");
                std::process::exit(1);
            }
            let res = scan_tree(Path::new(&args[2]));
            println!("{}", serde_json::to_string(&res).unwrap());
        }
        "meta" => {
            if args.len() < 3 {
                eprintln!("Error: missing file path for meta command");
                std::process::exit(1);
            }
            match file_meta(Path::new(&args[2])) {
                Ok(res) => println!("{}", serde_json::to_string(&res).unwrap()),
                Err(e) => {
                    println!("{{\"status\":\"error\",\"message\":\"{}\"}}", e);
                    std::process::exit(1);
                }
            }
        }
        "chunk" => {
            if args.len() < 3 {
                eprintln!("Error: missing file path for chunk command");
                std::process::exit(1);
            }
            let start = if args.len() >= 4 { args[3].parse::<usize>().unwrap_or(1) } else { 1 };
            let count = if args.len() >= 5 { args[4].parse::<usize>().unwrap_or(1000) } else { 1000 };
            match read_file_chunk(Path::new(&args[2]), start, count) {
                Ok(res) => println!("{}", serde_json::to_string(&res).unwrap()),
                Err(e) => {
                    println!("{{\"status\":\"error\",\"message\":\"{}\"}}", e);
                    std::process::exit(1);
                }
            }
        }
        "count" => {
            if args.len() < 3 {
                eprintln!("Error: missing directory path for count command");
                std::process::exit(1);
            }
            let res = fast_count_directory(Path::new(&args[2]));
            println!("{}", serde_json::to_string(&res).unwrap());
        }
        "parse" => {
            if args.len() < 3 {
                eprintln!("Error: missing file path for parse command");
                std::process::exit(1);
            }
            match parse_file(Path::new(&args[2])) {
                Ok(res) => println!("{}", serde_json::to_string(&res).unwrap()),
                Err(e) => {
                    println!("{{\"status\":\"error\",\"message\":\"{}\"}}", e);
                    std::process::exit(1);
                }
            }
        }
        "render" => {
            let content = if args.len() >= 3 && Path::new(&args[2]).exists() {
                fs::read_to_string(&args[2]).unwrap_or_default()
            } else if args.len() >= 3 {
                args[2].clone()
            } else {
                let mut buf = String::new();
                let _ = io::stdin().read_to_string(&mut buf);
                buf
            };
            let res = render_markdown_to_html(&content);
            println!("{}", serde_json::to_string(&res).unwrap());
        }
        "search" => {
            if args.len() < 4 {
                eprintln!("Error: usage: mdviewer_core search <lib_path> <query>");
                std::process::exit(1);
            }
            let res = search_library(Path::new(&args[2]), &args[3]);
            println!("{}", serde_json::to_string(&res).unwrap());
        }
        "import-folder" => {
            if args.len() < 4 {
                eprintln!("Error: usage: mdviewer_core import-folder <src_dir> <dst_dir>");
                std::process::exit(1);
            }
            match import_folder(Path::new(&args[2]), Path::new(&args[3])) {
                Ok(res) => println!("{}", serde_json::to_string(&res).unwrap()),
                Err(e) => {
                    println!("{{\"status\":\"error\",\"message\":\"{}\"}}", e);
                    std::process::exit(1);
                }
            }
        }
        other => {
            println!(
                "{{\"status\":\"error\",\"message\":\"Unknown command '{}'\"}}",
                other
            );
            std::process::exit(1);
        }
    }
}
