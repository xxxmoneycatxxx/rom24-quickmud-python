"""Extract untranslated player-facing strings from the codebase.

Uses targeted regex patterns to find strings that are actually delivered to
players (return values from command functions, send_to_char calls, etc.),
then compares against zh.json to find gaps.

Usage:
    python scripts/i18n_extract_missing.py [--category all|commands|look|prompt|combat|shop|other]
    python scripts/i18n_extract_missing.py --json   # output JSON for further processing
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ZH_JSON_PATH = REPO_ROOT / "data" / "i18n" / "zh.json"

# ---------------------------------------------------------------------------
# Scan targets by category
# ---------------------------------------------------------------------------

SCAN_TARGETS: dict[str, list[str]] = {
    "commands": ["mud/commands"],
    "look": ["mud/world/look.py"],
    "prompt": ["mud/utils/prompt.py"],
    "combat": ["mud/combat"],
    "shop": ["mud/commands/shop.py"],
    "other": [
        "mud/characters/conditions.py",
        "mud/world/movement.py",
        "mud/world/vision.py",
        "mud/skills/handlers.py",
        "mud/net/connection.py",
        "mud/handler.py",
        "mud/advancement.py",
        "mud/mobprog.py",
        "mud/spec_funs.py",
    ],
}

# ---------------------------------------------------------------------------
# Regex patterns for player-facing string extraction
# ---------------------------------------------------------------------------

# return "Some English message."  or  return f"..."
_RE_RETURN_STR = re.compile(
    r'''^\s*return\s+(?:f?["'])(.+?)(?:["'])\s*$''',
    re.MULTILINE,
)
# return "string" + variable  (partial — grab the static part)
_RE_RETURN_CONCAT = re.compile(
    r'''return\s+["'](.+?)["']\s*\+''',
)
# _send_to_char(char, "message") or push_message(char, "message")
_RE_SEND_TO_CHAR = re.compile(
    r'''(?:_send_to_char|push_message|send_to_char)\s*\([^,]+,\s*["'](.+?)["']\s*\)''',
)
# act_format("template", ...) or act_to_room(room, "template", ...)
_RE_ACT = re.compile(
    r'''(?:act_format|act_to_room|act)\s*\(\s*["'](.+?)["']\s*,''',
)
# Hardcoded dict values in look.py style:  Position.X: " is here."
_RE_DICT_VALUE = re.compile(
    r'''[:\,]\s*["'](.+?)["']\s*$''',
    re.MULTILINE,
)
# String constants assigned:  _CLOSED_EARLY = "Sorry, I am closed..."
_RE_CONST = re.compile(
    r'''^_[A-Z][A-Z_]+\s*=\s*["'](.+?)["']''',
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

_ENGLISH_RE = re.compile(r"[A-Za-z]{2,}")
_SKIP_PREFIXES = (
    "mirroring", "ROM ", "TODO", "FIXME", "HACK", "NOTE",
    "INV-", "LOOK-", "BUY-", "TRAIN-", "INTERP-", "PARALLEL-",
    "VISION-", "CAP-", "DUPL-", "ARITH-", "FINDING-", "PROMPT-",
)


def _is_player_facing(s: str) -> bool:
    """Heuristic: does this string look like a player-visible message?"""
    s = s.strip()
    if not s:
        return False
    if len(s) < 3:
        return False
    if not _ENGLISH_RE.search(s):
        return False
    if any(s.startswith(p) for p in _SKIP_PREFIXES):
        return False
    # Skip if mostly Chinese already
    if re.search(r"[\u4e00-\u9fff]", s):
        return False
    # Skip pure code references (no spaces, no punctuation — likely identifiers)
    if " " not in s and not any(c in s for c in ".,!?;'\""):
        return False
    # Skip strings that look like file paths or module names
    if "/" in s and "." in s and " " not in s:
        return False
    return True


def _load_existing_messages() -> set[str]:
    with open(ZH_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("messages", {}).keys())


def _load_existing_templates() -> set[str]:
    """Load existing template keys from zh.json templates section."""
    with open(ZH_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("templates", {}).keys())


def _extract_from_file(filepath: Path) -> list[tuple[int, str, str]]:
    """Extract player-facing strings from a single Python file.

    Returns list of (line_number, string, source_type).
    """
    try:
        source = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    results: list[tuple[int, str, str]] = []
    lines = source.split("\n")

    for lineno_0, line in enumerate(lines):
        lineno = lineno_0 + 1
        stripped = line.strip()

        # Skip comments and docstrings
        if stripped.startswith("#"):
            continue

        # return "message"
        for m in _RE_RETURN_STR.finditer(line):
            s = m.group(1)
            if _is_player_facing(s):
                results.append((lineno, s, "return"))

        # return "msg" + var
        for m in _RE_RETURN_CONCAT.finditer(line):
            s = m.group(1)
            if _is_player_facing(s):
                results.append((lineno, s, "return+"))

        # send_to_char / push_message
        for m in _RE_SEND_TO_CHAR.finditer(line):
            s = m.group(1)
            if _is_player_facing(s):
                results.append((lineno, s, "send"))

        # act_format / act_to_room templates
        for m in _RE_ACT.finditer(line):
            s = m.group(1)
            if _is_player_facing(s):
                results.append((lineno, s, "act"))

        # _CONSTANT = "message"
        for m in _RE_CONST.finditer(line):
            s = m.group(1)
            if _is_player_facing(s):
                results.append((lineno, s, "const"))

    return results


def extract_missing(category: str = "all") -> dict[str, list[dict]]:
    """Extract missing translations grouped by category."""
    existing_msgs = _load_existing_messages()
    existing_tmpl = _load_existing_templates()
    all_existing = existing_msgs | existing_tmpl

    targets = SCAN_TARGETS if category == "all" else {category: SCAN_TARGETS[category]}
    report: dict[str, list[dict]] = {}

    for cat, paths in targets.items():
        entries: list[dict] = []
        seen: set[str] = set()

        for rel_path in paths:
            full_path = REPO_ROOT / rel_path
            if full_path.is_file():
                files = [full_path]
            else:
                files = sorted(full_path.glob("*.py"))

            for filepath in files:
                strings = _extract_from_file(filepath)
                for lineno, s, src_type in strings:
                    normalized = s.strip().rstrip("\r\n")
                    # Also try with trailing \n\r stripped
                    normalized = normalized.replace("\\n\\r", "").replace("\\r\\n", "").strip()
                    if not normalized:
                        continue
                    if normalized in seen:
                        continue
                    if normalized in all_existing:
                        continue

                    seen.add(normalized)
                    entries.append({
                        "file": str(filepath.relative_to(REPO_ROOT)),
                        "line": lineno,
                        "string": normalized,
                        "source": src_type,
                    })

        if entries:
            report[cat] = entries

    return report


def print_report(report: dict[str, list[dict]]) -> None:
    """Print a human-readable report."""
    total = 0
    by_source: dict[str, int] = {}

    for cat, entries in sorted(report.items()):
        print(f"\n{'=' * 70}")
        print(f"  {cat.upper()}: {len(entries)} missing")
        print(f"{'=' * 70}")

        by_file: dict[str, list[dict]] = {}
        for e in entries:
            by_file.setdefault(e["file"], []).append(e)

        for fpath, file_entries in sorted(by_file.items()):
            print(f"\n  --- {fpath} ({len(file_entries)}) ---")
            for e in sorted(file_entries, key=lambda x: x["line"]):
                s = e["string"]
                if len(s) > 85:
                    s = s[:82] + "..."
                print(f"    L{e['line']:4d} [{e['source']:5s}] {s!r}")
                total += 1
                by_source[e["source"]] = by_source.get(e["source"], 0) + 1

    print(f"\n{'=' * 70}")
    print(f"  SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total missing: {total}")
    for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"    {src}: {cnt}")
    print()


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    category = args[0] if args else "all"
    output_json = "--json" in sys.argv

    if category not in SCAN_TARGETS and category != "all":
        print(f"Unknown category: {category}")
        print(f"Available: {', '.join(SCAN_TARGETS.keys())}, all")
        sys.exit(1)

    report = extract_missing(category)
    if not report:
        print("No missing translations found!")
        return

    if output_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
