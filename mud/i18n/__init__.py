"""Internationalization (i18n) translation layer.

Provides a non-invasive translation hook at the two message delivery
chokepoints:

1. ``act_format()`` — template strings (``$n hits $N``) are translated
   *before* token expansion, so entity names are inserted into the
   translated template in the correct word order.
2. ``send_to_char()`` — fully-formed messages are translated via
   exact-match lookup.

Translation data is loaded from JSON files under ``data/i18n/``.
The active language is controlled by the ``LANGUAGE`` environment
variable (default: ``"en"`` = no translation).

Design: zero engine code changes — the original English strings
remain in the source.  The translation layer intercepts at delivery
time and maps English → target language.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TRANSLATIONS_DIR = _REPO_ROOT / "data" / "i18n"

# Active language code (e.g. "en", "zh").  Read once at import time
# from the LANGUAGE env var; call ``set_language()`` to change at runtime.
# NOTE: .env loading happens in mud.config which may be imported after
# this module, so we defer the env var read to first use via _ensure_init().
_language: str | None = None

# Cached translation table for the active language.
_table: dict[str, Any] = {}

# Whether the table has been loaded (even if empty).
_loaded: bool = False

# Compiled regex patterns for dynamic string translation (lazy init).
_compiled_patterns: list[tuple[re.Pattern[str], str]] | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _ensure_init() -> None:
    """Lazily initialize _language from env var on first use.

    This defers the env var read until after mud.config has loaded .env,
    ensuring the LANGUAGE setting from .env takes effect.
    """
    global _language
    if _language is None:
        _language = os.getenv("LANGUAGE", "en").strip().lower() or "en"


def get_language() -> str:
    """Return the active language code (e.g. ``"en"``, ``"zh"``)."""
    _ensure_init()
    return _language  # type: ignore[return-value]


def set_language(lang: str) -> None:
    """Switch the active language and reload the translation table.

    Pass ``"en"`` to disable translation (all lookups fall through to
    the original English string).
    """
    global _language, _table, _loaded, _compiled_patterns
    _ensure_init()
    _language = lang.strip().lower() or "en"
    _table = {}
    _loaded = False
    _compiled_patterns = None
    if _language != "en":
        _load()


def is_translated() -> bool:
    """Return True when a non-English language is active."""
    _ensure_init()
    return _language != "en"


def t(key: str) -> str:
    """Translate a message string via exact-match, then pattern-match.

    Lookup order:
    1. Exact match in ``messages`` section.
    2. Regex pattern match in ``patterns`` section (for dynamic strings
       containing numbers, names, etc.).
    3. Fall through to the original English string.
    """
    if not is_translated():
        return key
    _ensure_loaded()
    # 1. Exact match
    messages = _table.get("messages", {})
    if key in messages:
        return messages[key]
    # 2. Pattern match (for dynamic f-strings)
    return _translate_pattern(key)


def _translate_pattern(msg: str) -> str:
    """Try to translate *msg* via the ``patterns`` regex table.

    Patterns are compiled lazily on first use and cached.  Returns the
    translated string if a pattern matches, otherwise returns *msg*
    unchanged.
    """
    global _compiled_patterns
    if _compiled_patterns is None:
        _compiled_patterns = _compile_patterns()
    for pattern, replacement in _compiled_patterns:
        result, n = pattern.subn(replacement, msg)
        if n > 0:
            return result
    return msg


def _compile_patterns() -> list[tuple[re.Pattern[str], str]]:
    """Compile the ``patterns`` section of the translation table.

    Each entry has ``"pattern"`` (regex string) and ``"replacement"``
    (replacement string, may use ``\\1`` back-references).
    """
    raw = _table.get("patterns", [])
    compiled: list[tuple[re.Pattern[str], str]] = []
    for entry in raw:
        pat_str = entry.get("pattern", "")
        replacement = entry.get("replacement", "")
        if not pat_str:
            continue
        try:
            compiled.append((re.compile(pat_str), replacement))
        except re.error:
            continue  # skip invalid patterns silently
    return compiled


def translate_template(template: str) -> str:
    """Translate an ``act_format()`` template before token expansion.

    The template may contain ``$n``, ``$N``, ``$p``, ``$P`` etc. tokens.
    Translation happens at the template level so that entity names are
    inserted into the translated text in the correct word order.

    After template lookup, English pronoun tokens ($e/$m/$s/$E/$M/$S/$mself)
    are converted to the target language's pronouns so social templates
    written with English pronouns render correctly in translation.

    Returns the translated template, or the original if no translation
    is available.
    """
    if not is_translated():
        return template
    _ensure_loaded()
    templates = _table.get("templates", {})
    result = templates.get(template, template)
    # Convert English pronoun tokens to target language pronouns
    if result is not template:
        result = _convert_pronouns(result)
    return result


def _convert_pronouns(text: str) -> str:
    """Convert actor ROM pronoun tokens to target language pronouns.

    Only actor pronouns ($e/$m/$s/$mself) are converted here because
    the target language form is known at translation time.  Victim
    pronouns ($E/$M/$S) are left as English tokens for
    ``expand_placeholders()`` to resolve — they need the victim's
    gender which is only available at render time.

    Order matters: ``$mself`` must be replaced before ``$m`` to avoid
    partial overlap (same logic as ROM ``src/comm.c:act_new``).
    """
    pronouns = _table.get("pronouns")
    if not pronouns:
        return text

    subj = pronouns.get("subject", {})
    obj_pron = pronouns.get("object", {})
    poss = pronouns.get("possessive", {})
    refl = pronouns.get("reflexive", {})

    # Actor pronouns (lowercase) — converted at template level
    text = text.replace("$mself", refl.get("none", "$mself"))
    text = text.replace("$e", subj.get("none", "$e"))
    text = text.replace("$m", obj_pron.get("none", "$m"))
    text = text.replace("$s", poss.get("none", "$s"))

    # Victim pronouns ($E/$M/$S) are intentionally NOT converted here.
    # They are resolved by expand_placeholders() at render time using
    # the victim's gender, which is unknown at template translation time.

    return text


def get_pronouns() -> dict[str, dict[str, str]] | None:
    """Return translated pronoun tables, or None for English defaults.

    The returned dict has keys ``"subject"``, ``"object"``,
    ``"possessive"``, each mapping sex names (``"male"``, ``"female"``,
    ``"none"``) to translated pronouns.
    """
    if not is_translated():
        return None
    _ensure_loaded()
    return _table.get("pronouns")


def get_direction(name: str) -> str:
    """Translate a direction name (north/south/east/...)."""
    if not is_translated():
        return name
    _ensure_loaded()
    directions = _table.get("directions", {})
    return directions.get(name, name)


def get_exit_name(direction: str) -> str:
    """Translate a direction for exit display (e.g. 'north' → '北')."""
    if not is_translated():
        return direction
    _ensure_loaded()
    exits = _table.get("exits", {})
    return exits.get(direction, direction)


def translate_help(keywords: list[str], text: str) -> str:
    """Translate a help entry's text by keyword lookup.

    The ``help`` section of the translation table maps the first keyword
    (case-insensitive) to a translated text block.  Returns the original
    *text* if no translation is available.
    """
    if not is_translated():
        return text
    _ensure_loaded()
    help_table = _table.get("help", {})
    if not help_table:
        return text
    for kw in keywords:
        translated = help_table.get(kw.lower())
        if translated:
            return translated
    return text


def translate_room(vnum: int, field: str, default: str) -> str:
    """Translate a room's name or description by vnum.

    The ``areas.rooms`` section maps vnum (as string) to a dict with
    ``"name"`` and/or ``"description"`` keys.  Returns *default* if no
    translation is available.
    """
    if not is_translated():
        return default
    _ensure_loaded()
    rooms = _table.get("areas", {}).get("rooms", {})
    entry = rooms.get(str(vnum))
    if entry and field in entry:
        return entry[field]
    return default


def translate_room_extra(vnum: int, keyword: str, default: str) -> str:
    """Translate a room's extra description by vnum and keyword.

    The ``areas.rooms`` section may contain an ``"extras"`` dict mapping
    keywords to translated descriptions.  Returns *default* if no
    translation is available.
    """
    if not is_translated():
        return default
    _ensure_loaded()
    rooms = _table.get("areas", {}).get("rooms", {})
    entry = rooms.get(str(vnum))
    if entry:
        extras = entry.get("extras", {})
        if extras and keyword in extras:
            return extras[keyword]
    return default


def translate_object(vnum: int, field: str, default: str) -> str:
    """Translate an object's name or description by vnum.

    The ``areas.objects`` section maps vnum (as string) to a dict with
    ``"name"`` and/or ``"description"`` keys.  Returns *default* if no
    translation is available.
    """
    if not is_translated():
        return default
    _ensure_loaded()
    objects = _table.get("areas", {}).get("objects", {})
    entry = objects.get(str(vnum))
    if entry and field in entry:
        return entry[field]
    return default


def translate_mob(vnum: int, field: str, default: str) -> str:
    """Translate a mob's name or description by vnum.

    The ``areas.mobs`` section maps vnum (as string) to a dict with
    ``"short_descr"`` and/or ``"long_descr"`` keys.  Returns *default*
    if no translation is available.
    """
    if not is_translated():
        return default
    _ensure_loaded()
    mobs = _table.get("areas", {}).get("mobs", {})
    entry = mobs.get(str(vnum))
    if entry and field in entry:
        return entry[field]
    return default


def translate_skill_name(name: str) -> str:
    """Translate a skill/spell name to the active language.

    The ``skills`` section maps English name to translated name.
    Returns *name* unchanged if no translation is available.
    """
    if not is_translated():
        return name
    _ensure_loaded()
    skills = _table.get("skills", {})
    return skills.get(name, name)


def translate_social(social_name: str, field: str, default: str) -> str:
    """Translate a social command message by social name and field.

    The ``socials`` section maps social name to a dict with fields like
    ``"char_no_arg"``, ``"others_no_arg"``, ``"char_found"``, etc.
    Returns *default* if no translation is available.
    """
    if not is_translated():
        return default
    _ensure_loaded()
    socials = _table.get("socials", {})
    entry = socials.get(social_name)
    if entry and field in entry:
        return entry[field]
    return default


def translate_skill(message: str) -> str:
    """Translate a skill/spell message string.

    The ``skills.messages`` section maps English message strings to
    their translations. Returns the original message if no translation
    is available.
    """
    if not is_translated():
        return message
    _ensure_loaded()
    skills = _table.get("skills", {})
    messages = skills.get("messages", {})
    return messages.get(message, message)


def translate_skill_name(name: str) -> str:
    """Translate a skill/spell name.

    Lookup order:
    1. ``skills.names.<name>`` — dedicated name-translation sub-section.
    2. ``skills.<name>`` — top-level skill entries (legacy / flat layout).

    Returns *name* unchanged if no translation is available.
    """
    if not is_translated():
        return name
    _ensure_loaded()
    skills = _table.get("skills", {})
    # Prefer dedicated names sub-section, fall back to top-level skill entries
    names = skills.get("names", {})
    if name in names:
        return names[name]
    # Top-level skills section (exclude meta keys like "messages", "names")
    if name in skills and name not in ("messages", "names"):
        val = skills[name]
        if isinstance(val, str):
            return val
    return name


def translate_shop(message: str) -> str:
    """Translate a shop/shopkeeper message string.

    The ``shop.messages`` section maps English message strings to
    their translations. Returns the original message if no translation
    is available.
    """
    if not is_translated():
        return message
    _ensure_loaded()
    shop = _table.get("shop", {})
    messages = shop.get("messages", {})
    return messages.get(message, message)


def translate_shop_type(name: str) -> str:
    """Translate a shop type name.

    The ``shop.types`` section maps English shop type names to
    their translations. Returns the original name if no translation
    is available.
    """
    if not is_translated():
        return name
    _ensure_loaded()
    shop = _table.get("shop", {})
    types = shop.get("types", {})
    return types.get(name, name)


def translate_item(message: str) -> str:
    """Translate an item usage message string.

    The ``items.messages`` section maps English message strings to
    their translations. Returns the original message if no translation
    is available.
    """
    if not is_translated():
        return message
    _ensure_loaded()
    items = _table.get("items", {})
    messages = items.get("messages", {})
    return messages.get(message, message)


def translate_item_type(name: str) -> str:
    """Translate an item type name.

    The ``items.types`` section maps English item type names to
    their translations. Returns the original name if no translation
    is available.
    """
    if not is_translated():
        return name
    _ensure_loaded()
    items = _table.get("items", {})
    types = items.get("types", {})
    return types.get(name, name)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_loaded() -> None:
    global _loaded
    if not _loaded:
        _load()


def _load() -> None:
    global _table, _loaded
    _loaded = True
    if _language == "en":
        _table = {}
        return
    path = _TRANSLATIONS_DIR / f"{_language}.json"
    if not path.exists():
        _table = {}
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            _table = json.load(f)
    except (json.JSONDecodeError, OSError):
        _table = {}
