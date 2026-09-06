import datetime
import difflib
import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path

MAX_READ_LINES = 500
MAX_SEARCH_MATCHES = 100
MAX_TREE_ENTRIES = 500
MAX_LIST_ENTRIES = 300
MAX_FIND_RESULTS = 200
MAX_RUN_OUTPUT = 20000
MAX_TOOL_OUTPUT = 50000
MAX_CLOSE_MATCHES = 3

handlers = {}
tools = []


def tool(name, description, params, required):
    def register(fn):
        handlers[name] = fn
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": params,
                        "required": required,
                    },
                },
            }
        )
        return fn

    return register


def walk_tree(dir_path, prefix, current_depth, results, max_depth):
    entries = sorted(dir_path.iterdir())
    for i, entry in enumerate(entries):
        if len(results) >= MAX_TREE_ENTRIES:
            return
        is_last_entry = i == len(entries) - 1
        connector = "`-- " if is_last_entry else "|-- "
        is_dir = entry.is_dir()
        results.append(f"{prefix}{connector}{entry.name}" + ("/" if is_dir else ""))
        if is_dir and (max_depth < 0 or current_depth < max_depth):
            new_prefix = prefix + ("    " if is_last_entry else "|   ")
            walk_tree(entry, new_prefix, current_depth + 1, results, max_depth)


def tool_err(category, detail, tip=""):
    if tip:
        return f"error: {category}: {detail}. Tip: {tip}"
    return f"error: {category}: {detail}"


def similar_file_paths(p, limit=MAX_CLOSE_MATCHES):
    root = p.parent if p.parent.is_dir() else Path(".")
    names = []
    paths_by_name = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("__pycache__", "node_modules")]
        for fn in filenames:
            if len(names) >= MAX_LIST_ENTRIES:
                return []
            names.append(fn)
            paths_by_name.setdefault(fn, Path(dirpath) / fn)
    wanted = p.name
    close = difflib.get_close_matches(wanted, names, n=limit, cutoff=0.6)
    ci = [n for n in names if n.lower() == wanted.lower() and n != wanted]
    ordered = []
    for n in ci + close:
        if n not in ordered:
            ordered.append(n)
    return [str(paths_by_name[n]) for n in ordered[:limit]]


def read_or_err(p, similar_hint=False):
    try:
        return p.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        detail = f"file not found: {p}"
        if similar_hint:
            similar = similar_file_paths(p)
            if similar:
                detail += "; did you mean: " + ", ".join(similar)
        return None, tool_err("not found", detail, "use list_files to check the path")
    except PermissionError:
        return None, tool_err("io", f"permission denied reading {p}")


def write_or_err(p, text):
    try:
        p.write_text(text, encoding="utf-8")
    except PermissionError:
        return tool_err("io", f"permission denied writing {p}")
    return None


@tool(
    "read_file",
    "Read lines from a file. Returns numbered lines with header '[path: lines X-Y of Z]'. Use start/end to paginate, or tail to read the end of a file. Defaults to the first 500 lines. Line numbers are 1-based.",
    {
        "path": {
            "type": "string",
            "description": "File path relative to workspace root.",
        },
        "start": {
            "type": "integer",
            "description": "Start line number (1-based, default 1).",
        },
        "end": {
            "type": "integer",
            "description": "End line number (1-based, inclusive, default 500).",
        },
        "tail": {"type": "integer", "description": "Read the last N lines of the file."},
    },
    ["path"],
)
def read_file(agent, args):
    p = Path(args["path"])

    txt, err = read_or_err(p, similar_hint=True)
    if err:
        return err

    lines = txt.splitlines()

    total = len(lines)

    if not total:
        return "(empty file)"

    tail_arg = args.get("tail")
    if tail_arg is not None:
        tail = int(tail_arg)
        if tail < 1:
            return tool_err("validation", f"tail must be >= 1, got {tail}")
        start, end = max(1, total - tail + 1), total
    else:
        start = int(args.get("start", 1))
        end = int(args.get("end", min(total, start + MAX_READ_LINES - 1)))

    if start < 1:
        return tool_err("validation", f"start must be >= 1, got {start}")
    if end < 1:
        return tool_err("validation", f"end must be >= 1, got {end}")
    if start > end:
        return tool_err("validation", f"start must be <= {end}, got {start}")
    if start > total:
        return tool_err("validation", f"start must be <= {total}, got {start}")

    end = min(end, total)
    snippet = lines[start - 1 : end]

    out = [f"[{p}: lines {start}-{end} of {total}]"]
    out.extend(f"{i}:{ln}" for i, ln in enumerate(snippet, start))
    result = "\n".join(out)

    if end < total:
        result += f"\n\n[{total - end} more lines. Use start={end + 1} to continue.]"
    elif args.get("start") or args.get("end"):
        result += "\n\n[end of file]"

    return result


@tool(
    "write_file",
    "Write content to a file. Creates parent directories if needed. Set append=true to append the content to the end of an existing file.",
    {
        "path": {
            "type": "string",
            "description": "File path relative to workspace root.",
        },
        "content": {"type": "string", "description": "File content to write."},
        "append": {
            "type": "boolean",
            "description": "If true, append content to the end of the file.",
        },
    },
    ["path", "content"],
)
def write_file(agent, args):
    p = Path(args["path"])
    content = args["content"]

    try:
        if args.get("append") and p.is_file():
            existing = p.read_text(encoding="utf-8")
            if existing and not existing.endswith("\n") and not content.startswith("\n"):
                content = "\n" + content

            with p.open("a", encoding="utf-8") as f:
                f.write(content)
            return f"appended: {p} ({len(content.encode("utf-8"))} bytes)"

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"written: {p} ({len(content.encode("utf-8"))} bytes)"
    except PermissionError:
        return tool_err("io", f"permission denied writing {p}")


def closest_lines(text, pattern, limit=3, floor=0.3, max_display=80):
    search_norms = [" ".join(ln.split()) for ln in pattern.split("\n") if ln.strip()]
    if not search_norms:
        return []
    file_lines = text.split("\n")
    best = {}
    for lineno, line in enumerate(file_lines, 1):
        norm = " ".join(line.split())
        if not norm or norm in best:
            continue
        nlen = len(norm)
        scored = None
        for s in search_norms:
            slen = len(s)
            if 2.0 * min(nlen, slen) < floor * (nlen + slen):
                continue
            ratio = difflib.SequenceMatcher(None, norm, s).ratio()
            if scored is None or ratio > scored[0]:
                overlap = len(set(norm.lower().split()) & set(s.lower().split()))
                scored = (ratio, overlap)
        if scored is not None and scored[0] >= floor:
            best[norm] = (scored[0], scored[1], lineno)
    ranked = sorted(best.values(), key=lambda t: (-t[0], -t[1], t[2]))[:limit]
    out = []
    for _ratio, _overlap, lineno in ranked:
        line = file_lines[lineno - 1].strip()
        if len(line) > max_display:
            line = line[: max_display - 3] + "..."
        out.append((lineno, line))
    out.sort()
    return out


def token_regex(pattern, flags=0, optional_leading=False):
    lines = pattern.split("\n")
    if all(not line.strip() for line in lines):
        return None

    regex_parts = []
    for i, line in enumerate(lines):
        if i > 0:
            regex_parts.append("\n")
        match = re.match(r"^[ \t]*", line)
        leading = match.group(0)
        tokens = line[len(leading) :].split()
        if leading:
            if optional_leading:
                regex_parts.append(r"(?:" + re.escape(leading) + r")?")
            else:
                regex_parts.append(re.escape(leading))
        if tokens:
            regex_parts.append(r"[ \t]*".join(map(re.escape, tokens)))

    return re.compile("".join(regex_parts), flags)


def token_ranges(text, pattern):
    regex = token_regex(pattern)
    if regex is None:
        return []
    return [(m.start(), m.end()) for m in regex.finditer(text)]


def line_no(text, pos):
    return 1 + text.count("\n", 0, pos)


def per_line_lines(text, pattern, limit=5):
    out = []
    for line in pattern.split("\n"):
        if not line.strip():
            continue
        nums = []
        for s, _e in token_ranges(text, line):
            nums.append(line_no(text, s))
            if len(nums) >= limit:
                break
        out.append(nums)
    return out


def per_line_suffix(text, pattern, limit=5):
    if len(pattern.split("\n")) < 2:
        return ""
    lines = per_line_lines(text, pattern, limit)
    if not lines:
        return ""
    parts = []
    for i, nums in enumerate(lines, 1):
        if nums:
            parts.append(f"search line {i} -> file line(s) " + ", ".join(map(str, nums)))
        else:
            parts.append(f"search line {i} -> none")
    suffix = "; per-line: " + "; ".join(parts)
    if all(lines):
        suffix += "; all search lines exist individually but not as a consecutive sequence"
    return suffix


def variant_notes(text, pattern, limit=3):
    notes = []
    for note, flags, optional_leading in (
        ("; note: case-insensitive match at line(s) ", re.IGNORECASE, False),
        ("; note: match with different leading indentation at line(s) ", 0, True),
    ):
        rx = token_regex(pattern, flags=flags, optional_leading=optional_leading)
        if rx is None:
            continue
        lines = []
        for m in rx.finditer(text):
            lines.append(str(line_no(text, m.start())))
            if len(lines) >= limit:
                break
        if lines:
            notes.append(note + ", ".join(lines))
    return "".join(notes)


def compute_diff(old, new, path):
    if old == new:
        return ""
    old_lines, new_lines = old.splitlines(keepends=True), new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=path, tofile=path, n=3))[2:]
    return "".join(line if line.endswith("\n") else line + "\n" for line in diff)


def not_found_hint(text, search):
    hint = ""
    close = closest_lines(text, search)
    if close:
        hint += "; closest line(s): " + ", ".join(f"{ln}: {line}" for ln, line in close)
    hint += per_line_suffix(text, search)
    hint += variant_notes(text, search)
    return hint


def report_edit(p, old_txt, new_txt, summary):
    diff = compute_diff(old_txt, new_txt, str(p))
    print(f"\n{diff}\n")
    return f"edited: {p}" + (f" ({summary})" if summary else "") + f"\n{diff}"


@tool(
    "edit_file",
    "Edit a file. Replaces the first occurrence of the search text. Use mode='all' to replace all occurrences. Returns diff.",
    {
        "path": {
            "type": "string",
            "description": "File path relative to workspace root.",
        },
        "search": {
            "type": "string",
            "description": "Text to find and replace (first occurrence, whitespace-insensitive).",
        },
        "content": {
            "type": "string",
            "description": "Replacement text.",
        },
        "mode": {
            "type": "string",
            "description": "Replace mode: 'first' (default, replace first occurrence) or 'all' (replace all occurrences).",
        },
    },
    ["path", "search", "content"],
)
def edit_file(agent, args):
    p = Path(args["path"])
    search = args["search"]
    replace = args["content"]
    mode = args.get("mode", "first")
    if mode not in ("first", "all"):
        return tool_err("validation", f"invalid mode: {mode!r}, expected 'first' or 'all'")

    if not search:
        return tool_err("validation", "search text is required", "use read_file to get the exact text first")
    if not replace:
        return tool_err("validation", "content is required")

    txt, err = read_or_err(p, similar_hint=True)
    if err:
        return err

    valid_matches = token_ranges(txt, search)

    if not valid_matches:
        detail = f"search text not found (whitespace-insensitive): {search!r}"
        return tool_err("not found", detail + not_found_hint(txt, search), "use read_file to get the exact text first")

    matches = valid_matches[:1] if mode == "first" else valid_matches
    parts = []
    prev_end = 0
    for s, e in matches:
        parts.append(txt[prev_end:s])
        parts.append(replace)
        prev_end = e
    parts.append(txt[prev_end:])
    new_txt = "".join(parts)

    err = write_or_err(p, new_txt)
    if err:
        return err

    return report_edit(p, txt, new_txt, None)


@tool(
    "edit_file_blocks",
    "Apply multiple search/replace blocks to a file in one call. Each block replaces the unique match of its search text with content. Returns combined diff.",
    {
        "path": {
            "type": "string",
            "description": "File path relative to workspace root.",
        },
        "blocks": {
            "type": "array",
            "description": "Ordered list of search/replace blocks, each with search (string) and content (string).",
            "items": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Text to find and replace (unique, whitespace-insensitive).",
                    },
                    "content": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                },
                "required": ["search", "content"],
            },
        },
        "dry_run": {
            "type": "boolean",
            "description": "Compute and return the diff without writing the file (default false).",
        },
    },
    ["path", "blocks"],
)
def edit_file_blocks(agent, args):
    p = Path(args["path"])
    blocks = args["blocks"]
    dry_run = bool(args.get("dry_run", False))

    txt, err = read_or_err(p, similar_hint=True)
    if err:
        return err

    if not isinstance(blocks, list) or not blocks:
        return tool_err(
            "validation",
            "blocks must be a non-empty array of {search, content} objects",
        )

    for i, blk in enumerate(blocks):
        if not isinstance(blk, dict) or "search" not in blk or "content" not in blk:
            return tool_err("validation", f"block {i+1}: each block must have 'search' and 'content' fields")
        if not blk["search"].strip():
            return tool_err(
                "validation", f"block {i+1}: search text is required", "use read_file to get the exact text first"
            )
        if not blk["content"].strip():
            return tool_err("validation", f"block {i+1}: content is required")

    new_txt = txt
    for i, blk in enumerate(blocks):
        matches = token_ranges(new_txt, blk["search"])
        if not matches:
            detail = f"block {i+1}: search text not found (whitespace-insensitive): {blk['search']!r}"
            return tool_err(
                "not found",
                detail + not_found_hint(new_txt, blk["search"]),
                "use read_file to get the exact text first",
            )
        if len(matches) > 1:
            locs = ", ".join(str(line_no(new_txt, s)) for s, _e in matches[:5])
            return tool_err(
                "ambiguous",
                f"block {i+1}: search text matches {len(matches)} location(s): {blk['search']!r}; "
                f"add more context; matches at line(s): {locs}",
            )
        s, e = matches[0]
        new_txt = new_txt[:s] + blk["content"] + new_txt[e:]

    if dry_run:
        diff = compute_diff(txt, new_txt, str(p))
        return f"dry run: {p} (would apply {len(blocks)} block(s))\n{diff}"

    err = write_or_err(p, new_txt)
    if err:
        return err

    return report_edit(p, txt, new_txt, f"applied {len(blocks)} block(s)")


@tool(
    "delete_file",
    "Delete a file. Cannot delete directories.",
    {
        "path": {
            "type": "string",
            "description": "File path relative to workspace root.",
        },
    },
    ["path"],
)
def delete_file(agent, args):
    p = Path(args["path"])
    if p.is_dir():
        return tool_err(
            "validation",
            f"cannot delete directory '{p}'",
            "only files can be deleted",
        )
    try:
        p.unlink()
    except FileNotFoundError:
        return tool_err("not found", f"file not found: {p}")
    except PermissionError:
        return tool_err("io", f"permission denied deleting {p}")
    return f"deleted: {p}"


@tool(
    "mkdir",
    "Create a new directory (including parents).",
    {
        "path": {
            "type": "string",
            "description": "Directory path relative to workspace root.",
        },
    },
    ["path"],
)
def mkdir(agent, args):
    p = Path(args["path"])
    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"created: {p}"
    except PermissionError:
        return tool_err("io", f"permission denied creating {p}")


@tool(
    "rename_file",
    "Move or rename a file.",
    {
        "src": {
            "type": "string",
            "description": "Source file path relative to workspace root.",
        },
        "dst": {
            "type": "string",
            "description": "Destination file path relative to workspace root.",
        },
    },
    ["src", "dst"],
)
def rename_file(agent, args):
    src = Path(args["src"])
    dst = Path(args["dst"])
    try:
        if not src.is_file():
            return tool_err("not found", f"source not found: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return f"moved: {src} -> {dst}"
    except OSError as e:
        return tool_err("io", str(e))


@tool(
    "list_files",
    "List files and directories at the given path in the workspace. Returns [D] dir / [F] file entries, with line counts for files under 100KB.",
    {
        "path": {
            "type": "string",
            "description": "Directory path relative to workspace root. Defaults to '.'",
        },
    },
    [],
)
def list_files(agent, args):
    p = Path(args.get("path", "."))
    if not p.exists():
        return tool_err("not found", f"directory not found: {p}")
    if not p.is_dir():
        return tool_err("validation", f"'{p}' is not a directory")
    entries = sorted(p.iterdir())
    lines = []
    for entry in entries[:MAX_LIST_ENTRIES]:
        if entry.is_dir():
            lines.append(f"[D] {entry.name}")
        else:
            info = entry.stat()
            line_info = ""
            if info.st_size < 100 * 1024:
                try:
                    lc = len(entry.read_text(errors="ignore").splitlines())
                    if lc > 0:
                        line_info = f" {lc}L"
                except (OSError, PermissionError):
                    pass
            lines.append(f"[F] {entry.name}{line_info}")
    if len(entries) > MAX_LIST_ENTRIES:
        lines.append(f"... ({len(entries) - MAX_LIST_ENTRIES} more entries)")
    if not lines:
        return f"(empty directory: {p})"
    return f"[{p}]\n" + "\n".join(lines)


def glob_match(rel, pattern):
    s = str(rel)
    if fnmatch.fnmatch(s, pattern) or fnmatch.fnmatch(rel.name, pattern):
        return True
    if pattern.startswith("**/"):
        parts = s.split("/")
        return any(fnmatch.fnmatch("/".join(parts[i:]), pattern[3:]) for i in range(len(parts)))
    return False


@tool(
    "find_files",
    "Find files matching a glob pattern (e.g. '*.go', '**/test_*'). Returns relative paths.",
    {
        "pattern": {
            "type": "string",
            "description": "Glob pattern to match (e.g. '*.go', '**/*.test.*').",
        },
        "path": {
            "type": "string",
            "description": "Directory to search in, relative to workspace root. Defaults to '.'",
        },
    },
    ["pattern"],
)
def find_files(agent, args):
    pattern = args["pattern"]
    p = Path(args.get("path", "."))
    results = []
    for fpath in p.rglob("*"):
        if fpath.is_file():
            rel = fpath.relative_to(p)
            if glob_match(rel, pattern):
                results.append(str(rel))
    results.sort()
    if len(results) > MAX_FIND_RESULTS:
        results = results[:MAX_FIND_RESULTS] + [
            f"... ({len(results) - MAX_FIND_RESULTS} more files; narrow the pattern or set path=)"
        ]
    return "\n".join(results) if results else f"(no files matching {pattern!r})"


@tool(
    "search",
    "Search for a regex pattern in a file or directory. Returns matching lines with file paths, line numbers, and >>highlighted<< matches. Binary files skipped.",
    {
        "pattern": {
            "type": "string",
            "description": "Regex pattern to search for (case-sensitive).",
        },
        "path": {
            "type": "string",
            "description": "Directory or file path relative to workspace root. Defaults to '.'",
        },
        "context": {
            "type": "integer",
            "description": "Number of lines of context to show around each match. Defaults to 3.",
        },
        "case_insensitive": {
            "type": "boolean",
            "description": "If true, search case-insensitively. Defaults to false.",
        },
    },
    ["pattern"],
)
def search(agent, args):
    pattern = args["pattern"]
    root = Path(args.get("path", "."))
    if not root.exists():
        return tool_err("not found", f"path not found: {root}")
    ctx = int(args.get("context", 3))
    if ctx < 0:
        return tool_err("validation", f"context must be >= 0, got {ctx}")
    flags = re.IGNORECASE if args.get("case_insensitive") else 0

    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return tool_err("validation", f"invalid regex: {e}")

    matches = []

    if root.is_file():
        files_to_search = [root]
    else:
        files_to_search = sorted(f for f in root.rglob("*") if f.is_file())

    for fpath in files_to_search:

        try:
            raw = fpath.read_bytes()
        except (OSError, PermissionError):
            continue

        if b"\x00" in raw[:512]:
            continue

        lines = raw.decode("utf-8", errors="ignore").splitlines()

        rel = fpath.relative_to(root)
        if str(rel) == ".":
            rel = fpath.name

        for i, line in enumerate(lines):
            m = regex.search(line)
            if m:
                highlighted = line[: m.start()] + ">>" + line[m.start() : m.end()] + "<<" + line[m.end() :]
                ctx_start = max(i - ctx, 0)
                ctx_end = min(i + ctx + 1, len(lines))
                context_block = [f"  {k+1}:{lines[k]}" for k in range(ctx_start, ctx_end) if k != i]
                ctx_str = "\n" + "\n".join(context_block) if context_block else ""
                matches.append(f"{rel}:{i+1}:{highlighted}{ctx_str}")

    if len(matches) > MAX_SEARCH_MATCHES:
        matches = matches[:MAX_SEARCH_MATCHES] + [
            f"... ({len(matches) - MAX_SEARCH_MATCHES} more matches; narrow the pattern or set path=)"
        ]
    return "\n".join(matches) if matches else "(no matches)"


def truncate_output(output, limit=MAX_RUN_OUTPUT, head=200):
    if len(output) > limit + head:
        removed = len(output) - head - limit
        marker = f"\n... ({removed} chars removed from middle; output truncated)\n"
        return output[:head] + marker + output[-limit:]
    else:
        return output


@tool(
    "run_command",
    "Execute a shell command from the workspace root; `cd` into a project subdirectory first if the command must run there (e.g. `cd project && make`). Exit code shown on error.",
    {
        "command": {
            "type": "string",
            "description": "Shell command to execute.",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds. Defaults to 30.",
        },
    },
    ["command"],
)
def run_command(agent, args):
    command = args["command"]
    timeout = int(args.get("timeout", 30))
    if timeout < 1:
        return tool_err("validation", f"timeout must be >= 1, got {timeout}")

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return tool_err("command", f"command timed out after {timeout}s")

    output = truncate_output(proc.stdout + proc.stderr, MAX_RUN_OUTPUT)

    if proc.returncode != 0:
        return f"{output}\n{tool_err('command', f'{command!r} exited with code {proc.returncode}', 'check the command syntax and that required tools are installed')}"
    return output if output.strip() else "(success, no output)"


@tool(
    "current_time",
    "Return the current date and time in UTC and local timezone.",
    {},
    [],
)
def current_time(agent, args):
    now = datetime.datetime.now().astimezone()
    utc = now.astimezone(datetime.timezone.utc)
    return f"UTC: {utc.strftime('%Y-%m-%d %H:%M:%S %z')}\nLocal: {now.strftime('%Y-%m-%d %H:%M:%S %z')}"


@tool(
    "tree",
    "Show a recursive directory structure of the project.",
    {
        "path": {
            "type": "string",
            "description": "Directory path relative to workspace root. Defaults to '.'",
        },
        "depth": {
            "type": "integer",
            "description": "Maximum recursion depth (-1 = unlimited). Defaults to -1.",
        },
    },
    [],
)
def tree(agent, args):
    p = Path(args.get("path", "."))
    if not p.exists():
        return tool_err("not found", f"path not found: {p}")

    max_depth = int(args.get("depth", -1))
    if max_depth < -1:
        return tool_err("validation", f"depth must be >= -1, got {max_depth}")
    results = []

    results.append(str(p))
    if p.is_dir():
        walk_tree(p, "", 0, results, max_depth)
    if len(results) >= MAX_TREE_ENTRIES:
        results.append(f"... (tree truncated at {MAX_TREE_ENTRIES} entries; use depth to limit)")

    result = f"tree for {p}:\n" + "\n".join(results)
    return result


required_parameters = {t["function"]["name"]: t["function"]["parameters"]["required"] for t in tools}


def arg_repr(v):
    if isinstance(v, list):
        return f"[{len(v)} items]"
    if isinstance(v, str) and "\n" in v:
        return "..."
    return v


def execute(agent, tool_call):
    tool_call_id = tool_call["id"]
    name = tool_call["function"]["name"]
    try:
        args = json.loads(tool_call["function"]["arguments"])
    except (json.JSONDecodeError, TypeError):
        args = {}

    missing = [p for p in required_parameters.get(name, []) if p not in args]
    if missing:
        result = tool_err("validation", f"missing required parameter(s): {', '.join(missing)}")
    else:
        parts = sorted(f"{k}={arg_repr(v)}" for k, v in args.items())
        print(f"  -> {name}({', '.join(parts)})")

        handler = handlers.get(name)
        if handler:
            try:
                result = handler(agent, args)
            except Exception as e:  # noqa: BLE001
                result = tool_err("type", str(e), "check the arguments and try again")
        else:
            result = tool_err("type", f"unknown tool: {name}", f"available: {list(handlers.keys())}")

    if len(result) > MAX_TOOL_OUTPUT:
        result = result[:MAX_TOOL_OUTPUT] + f"\n... ({len(result) - MAX_TOOL_OUTPUT} more chars; result truncated)"

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": result,
    }
