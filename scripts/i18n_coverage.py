"""i18n coverage audit — report untranslated player-facing strings.

Scans Python source files for string literals that are delivered to players
(command return values, send_to_char calls, etc.) and checks whether each
has a corresponding translation in zh.json.

Usage:
    python scripts/i18n_coverage.py              # human-readable report
    python scripts/i18n_coverage.py --json        # machine-readable JSON
    python scripts/i18n_coverage.py --threshold 80  # fail if < 80% covered

Exit code is non-zero when --threshold is given and coverage is below it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ZH_JSON_PATH = REPO_ROOT / "data" / "i18n" / "zh.json"

# ---------------------------------------------------------------------------
# Scan scope — player-facing modules only (excludes immortal/OLC commands)
# ---------------------------------------------------------------------------

PLAYER_SCAN_DIRS = [
    "mud/commands",
    "mud/combat",
    "mud/world",
    "mud/characters",
    "mud/skills",
    "mud/utils",
]

# Files/dirs excluded (immortal-only, internal, or noise)
EXCLUDE_PATTERNS = [
    "build.py",       # OLC builder — 300+ strings, immortal-only
    "imm_",           # immortal commands — admin-only
    "admin_",         # admin commands — admin-only
    "mobprog_tools",  # mobprog debug — immortal-only
    "string_editor",  # SEdit — immortal-only string editor
    "imc.py",         # IMC inter-MUD — internal
    "__pycache__",
    "test_",
]

# ---------------------------------------------------------------------------
# String extraction (same approach as i18n_extract_missing.py)
# ---------------------------------------------------------------------------

_RE_RETURN_STR = re.compile(r'''^\s*return\s+(?:f?["'])(.+?)(?:["'])\s*$''', re.MULTILINE)
_RE_RETURN_CONCAT = re.compile(r'''return\s+["'](.+?)["']\s*\+''')
_RE_SEND_TO_CHAR = re.compile(r'''(?:_send_to_char|push_message|send_to_char)\s*\([^,]+,\s*["'](.+?)["']\s*\)''')
_RE_ACT = re.compile(r'''(?:act_format|act_to_room|act)\s*\(\s*["'](.+?)["']\s*,''')
_RE_CONST = re.compile(r'''^_[A-Z][A-Z_]+\s*=\s*["'](.+?)["']''', re.MULTILINE)

_ENGLISH_RE = re.compile(r"[A-Za-z]{2,}")
# Regex artefacts: patterns that look like code fragments, not real strings.
_RE_CODE_FRAGMENT = re.compile(
    r'(?:^|[\s.])join\s*\(|\.split\s*\(|\.format\s*\(|\{[\w.]+:[\w]+\}|^\{\{'
)
# Lines containing these patterns already have translation calls — the regex
# extractor sometimes captures the surrounding expression as a "string".
_RE_ALREADY_TRANSLATED = re.compile(r'(?:_t|translate_\w+)\s*\(')
_SKIP_PREFIXES = (
    "mirroring", "ROM ", "TODO", "FIXME", "HACK", "NOTE",
    "INV-", "LOOK-", "BUY-", "TRAIN-", "INTERP-", "PARALLEL-",
    "VISION-", "CAP-", "DUPL-", "ARITH-", "FINDING-", "PROMPT-",
    "SEEdit:", "Syntax:", "usage:",
)
# Strings that end with these fragments are regex artefacts from apostrophes
# in contractions (e.g. "I don" from "I don't trade...").
_CONTRACTION_FRAGMENTS = (
    "don", "can", "won", "didn", "couldn", "wouldn", "shouldn",
    "isn", "aren", "wasn", "weren", "hasn", "haven", "hadn", "let",
)


def _is_player_facing(s: str) -> bool:
    s = s.strip()
    if len(s) < 3:
        return False
    if not _ENGLISH_RE.search(s):
        return False
    if any(s.startswith(p) for p in _SKIP_PREFIXES):
        return False
    if re.search(r"[\u4e00-\u9fff]", s):
        return False
    if _RE_CODE_FRAGMENT.search(s):
        return False
    if _RE_ALREADY_TRANSLATED.search(s):
        return False
    # Filter regex artefacts from apostrophe-split contractions
    last_word = s.rsplit(None, 1)[-1] if " " in s else s
    if last_word.lower() in _CONTRACTION_FRAGMENTS:
        return False
    if " " not in s and not any(c in s for c in ".,!?;?'\""):
        return False
    if "/" in s and "." in s and " " not in s:
        return False
    return True


def _is_excluded(rel_path: str) -> bool:
    return any(pat in rel_path for pat in EXCLUDE_PATTERNS)


def _load_zh() -> dict:
    with open(ZH_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def _existing_keys(data: dict) -> set[str]:
    keys: set[str] = set()
    for section in ("messages", "templates"):
        for k in data.get(section, {}).keys():
            keys.add(k)
            # Also add a stripped copy — source extraction strips trailing
            # whitespace (\n, \r\n) but zh.json keys often retain it.
            keys.add(k.strip())
    return keys


def _decode_escapes(s: str) -> str:
    """Decode Python escape sequences to match runtime string values.

    Source code contains literal ``\\n`` (two chars: backslash + n) but
    the runtime string has an actual newline byte.  zh.json keys (after
    JSON parsing) also contain actual newline bytes, so we must decode
    to match.
    """
    try:
        return s.encode("utf-8").decode("unicode_escape")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def _extract_from_file(filepath: Path) -> list[str]:
    try:
        source = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    results: list[str] = []
    for line in source.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pattern in [_RE_RETURN_STR, _RE_RETURN_CONCAT, _RE_SEND_TO_CHAR, _RE_ACT, _RE_CONST]:
            for m in pattern.finditer(line):
                s = m.group(1).strip()
                # Decode Python escape sequences (\n -> newline, \r -> CR, etc.)
                # so the extracted key matches the runtime string value and the
                # corresponding zh.json key (which JSON-parses escapes too).
                s = _decode_escapes(s)
                # Strip trailing whitespace variants for matching
                s = s.strip()
                if s and _is_player_facing(s):
                    results.append(s)
    return results


def audit() -> dict:
    """Run the coverage audit. Returns a summary dict."""
    zh_data = _load_zh()
    existing = _existing_keys(zh_data)

    total = 0
    translated = 0
    untranslated: list[dict] = []
    seen: set[str] = set()

    for scan_dir in PLAYER_SCAN_DIRS:
        base = REPO_ROOT / scan_dir
        if base.is_file():
            files = [base]
        else:
            files = sorted(base.rglob("*.py"))

        for filepath in files:
            rel = str(filepath.relative_to(REPO_ROOT)).replace("\\", "/")
            if _is_excluded(rel):
                continue

            strings = _extract_from_file(filepath)
            for s in strings:
                if s in seen:
                    continue
                seen.add(s)
                total += 1
                if s in existing:
                    translated += 1
                else:
                    untranslated.append({"file": rel, "string": s[:100]})

    pct = (translated / total * 100) if total > 0 else 100.0

    return {
        "total": total,
        "translated": translated,
        "untranslated_count": len(untranslated),
        "coverage_pct": round(pct, 1),
        "untranslated_samples": untranslated[:50],  # first 50 for debugging
    }


def main() -> None:
    output_json = "--json" in sys.argv
    threshold = None
    for i, arg in enumerate(sys.argv):
        if arg == "--threshold" and i + 1 < len(sys.argv):
            threshold = float(sys.argv[i + 1])

    result = audit()

    if output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"i18n Coverage Audit")
        print(f"{'=' * 50}")
        print(f"  Total player-facing strings: {result['total']}")
        print(f"  Translated:                  {result['translated']}")
        print(f"  Untranslated:                {result['untranslated_count']}")
        print(f"  Coverage:                    {result['coverage_pct']}%")
        print(f"{'=' * 50}")
        if result["untranslated_samples"]:
            print(f"\n  First {len(result['untranslated_samples'])} untranslated strings:")
            for item in result["untranslated_samples"]:
                print(f"    [{item['file']}] {item['string']!r}")

    if threshold is not None and result["coverage_pct"] < threshold:
        print(f"\nFAILED: coverage {result['coverage_pct']}% < threshold {threshold}%")
        sys.exit(1)


if __name__ == "__main__":
    main()
