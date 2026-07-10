"""Regression + parity: `_char_affected` mirrors ROM `IS_AFFECTED(ch, AFF_*)`.

`mud/utils/act.py:format_obj_to_char` renders object aura tags (Red/Blue Aura,
Magical) exactly as ROM does (`src/act_info.c`):

    if (IS_AFFECTED(ch, AFF_DETECT_EVIL) && IS_OBJ_STAT(obj, ITEM_EVIL))
        strcat(buf, "(Red Aura) ");

`IS_AFFECTED` is a pure bitfield test on `ch->affected_by`. The port previously
implemented `_char_affected` with a non-ROM affect-list walk that resolved each
affect's `type` through `from mud.skills.registry import skill_lookup` — a name
that never existed in that module. Any player carrying a string-typed affect who
ran `inventory` (or anything rendering an object short description) hit

    ImportError: cannot import name 'skill_lookup' from 'mud.skills.registry'

and the command aborted with "Sorry, there was an error processing that command."

The fix makes `_char_affected` *be* `IS_AFFECTED` — a bitfield test — matching ROM.
"""

from __future__ import annotations

from types import SimpleNamespace

from mud.models.constants import AffectFlag, ExtraFlag
from mud.utils.act import _char_affected, format_obj_to_char


def test_char_affected_is_bitfield_test_not_list_walk():
    """DETECT_EVIL in affected_by → True; the affect list is irrelevant (ROM IS_AFFECTED)."""
    char = SimpleNamespace(affected_by=int(AffectFlag.DETECT_EVIL))
    assert _char_affected(char, "detect_evil") is True
    assert _char_affected(char, "detect_good") is False


def test_char_affected_string_typed_affect_does_not_crash():
    """The old broken import fired on any string-typed affect; must not raise now."""
    char = SimpleNamespace(
        affected=[SimpleNamespace(name=None, spell_name=None, type="sanctuary")],
        affected_by=0,
    )
    assert _char_affected(char, "detect_magic") is False


def test_detect_magic_aura_renders_via_affected_by_bit():
    """ROM src/act_info.c: IS_AFFECTED(ch, AFF_DETECT_MAGIC) && ITEM_MAGIC → (Magical)."""
    seer = SimpleNamespace(affected_by=int(AffectFlag.DETECT_MAGIC))
    blind = SimpleNamespace(affected_by=0)
    obj = SimpleNamespace(
        short_descr="a glowing wand", description="A wand lies here.", extra_flags=int(ExtraFlag.MAGIC)
    )

    assert format_obj_to_char(obj, seer, True) == "(Magical) a glowing wand"
    assert format_obj_to_char(obj, blind, True) == "a glowing wand"
