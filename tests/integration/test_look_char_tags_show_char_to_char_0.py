"""LOOK char-tags — show_char_to_char_0 renders all 12 status tags in ROM order.

ROM ``show_char_to_char_0`` (``src/act_info.c:253-276``) prepends, in this fixed
order: ``[AFK]`` ``(Invis)`` ``(Wizi)`` ``(Hide)`` ``(Charmed)`` ``(Translucent)``
``(Pink Aura)`` ``(Red Aura)`` ``(Golden Aura)`` ``(White Aura)`` ``(KILLER)``
``(THIEF)``. The Python room-occupant line rendered only ``(Pink Aura)`` and
``(White Aura)`` (via ``describe_character``); the other ten were missing.
"""

from __future__ import annotations

import pytest

from mud.models.character import Character
from mud.models.constants import AffectFlag, CommFlag, FurnitureFlag, PlayerFlag, Position
from mud.models.room import Room
from mud.world.look import _room_occupant_line


def _pc(name: str, **kw) -> Character:
    c = Character(name=name, level=30, is_npc=False, position=Position.STANDING)
    c.messages = []
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_room_occupant_line_renders_all_tags_in_rom_order():
    room = Room(vnum=3001, name="Test Room", description="A test room.")
    # Observer: HOLYLIGHT (sees everything) + DETECT_EVIL/GOOD to trigger the auras.
    observer = _pc("Observer")
    observer.act = int(PlayerFlag.HOLYLIGHT)
    observer.affected_by = int(AffectFlag.DETECT_EVIL) | int(AffectFlag.DETECT_GOOD)

    victim = _pc("Victim")
    victim.comm = int(CommFlag.AFK)
    victim.invis_level = 60  # >= LEVEL_HERO (51) → (Wizi)
    victim.affected_by = (
        int(AffectFlag.INVISIBLE)
        | int(AffectFlag.HIDE)
        | int(AffectFlag.CHARM)
        | int(AffectFlag.PASS_DOOR)
        | int(AffectFlag.FAERIE_FIRE)
        | int(AffectFlag.SANCTUARY)
    )
    victim.alignment = -1000  # IS_EVIL → (Red Aura) with observer DETECT_EVIL
    victim.act = int(PlayerFlag.KILLER) | int(PlayerFlag.THIEF)

    room.add_character(observer)
    room.add_character(victim)

    line = _room_occupant_line(observer, victim)

    expected_order = [
        "[AFK]",
        "(Invis)",
        "(Wizi)",
        "(Hide)",
        "(Charmed)",
        "(Translucent)",
        "(Pink Aura)",
        "(Red Aura)",
        "(White Aura)",  # golden requires IS_GOOD; this victim is evil, so it is absent
        "(KILLER)",
        "(THIEF)",
    ]
    positions = []
    for tag in expected_order:
        assert tag in line, f"{tag!r} missing from {line!r}"
        positions.append(line.index(tag))
    assert positions == sorted(positions), f"tags out of ROM order in {line!r}"
    assert "(Golden Aura)" not in line  # victim is evil, not good


def test_golden_aura_requires_good_alignment_and_observer_detect_good():
    room = Room(vnum=3001, name="Test Room", description="A test room.")
    observer = _pc("Observer")
    observer.act = int(PlayerFlag.HOLYLIGHT)
    observer.affected_by = int(AffectFlag.DETECT_GOOD)

    victim = _pc("Saint")
    victim.alignment = 1000  # IS_GOOD

    room.add_character(observer)
    room.add_character(victim)

    line = _room_occupant_line(observer, victim)
    assert "(Golden Aura)" in line
    assert "(Red Aura)" not in line


def test_fighting_target_uses_bare_pers_not_aura_tags():
    """ROM show_char_to_char_0 POS_FIGHTING (src/act_info.c:412) renders the
    victim's fighting target with PERS(victim->fighting, ch) — the bare name,
    NOT the show_char_to_char aura block. A sanctuary'd target must show as
    "... fighting Target." not "... fighting (White Aura) Target." (FINDING-043,
    same class as the scan FINDING-042 aura/PERS bug)."""
    room = Room(vnum=3001, name="Test Room", description="A test room.")
    observer = _pc("Observer")
    observer.act = int(PlayerFlag.HOLYLIGHT)

    target = _pc("Target")
    target.affected_by = int(AffectFlag.SANCTUARY)  # (White Aura), ungated

    victim = _pc("Victim", position=Position.FIGHTING)
    victim.fighting = target

    room.add_character(observer)
    room.add_character(victim)
    room.add_character(target)

    line = _room_occupant_line(observer, victim)
    assert "is here, fighting Target." in line, line
    assert "(White Aura)" not in line, f"scan/PERS aura leak into fight line: {line!r}"


def _furniture(short_descr: str, furn_flags: int):
    """Build a furniture Object with value[2] = furn_flags and a short_descr."""
    from mud.models.constants import ItemType
    from mud.models.object import Object, ObjIndex

    proto = ObjIndex(vnum=6000, short_descr=short_descr, item_type=int(ItemType.FURNITURE))
    obj = Object(instance_id=None, prototype=proto)
    obj.short_descr = short_descr
    obj.value = [8, 0, furn_flags, 0, 0]  # value[0]=capacity, value[2]=position bits
    return obj


@pytest.mark.parametrize(
    "position, furn_flag, expected",
    [
        # ROM show_char_to_char_0 (src/act_info.c:304-401) — AT/ON/IN preposition
        # comes from the furniture's value[2] bits; absent AT and ON → "in".
        (Position.SITTING, FurnitureFlag.SIT_ON, "is sitting on a wooden chair."),
        (Position.SITTING, FurnitureFlag.SIT_AT, "is sitting at a wooden chair."),
        (Position.SITTING, FurnitureFlag.SIT_IN, "is sitting in a wooden chair."),
        (Position.RESTING, FurnitureFlag.REST_ON, "is resting on a wooden chair."),
        (Position.RESTING, FurnitureFlag.REST_AT, "is resting at a wooden chair."),
        (Position.SLEEPING, FurnitureFlag.SLEEP_ON, "is sleeping on a wooden chair."),
        (Position.SLEEPING, FurnitureFlag.SLEEP_AT, "is sleeping at a wooden chair."),
        (Position.STANDING, FurnitureFlag.STAND_ON, "is standing on a wooden chair."),
        (Position.STANDING, FurnitureFlag.STAND_AT, "is standing at a wooden chair."),
        (Position.STANDING, FurnitureFlag.STAND_IN, "is standing in a wooden chair."),
    ],
)
def test_room_occupant_line_renders_furniture_position(position, furn_flag, expected):
    """LOOK-018: show_char_to_char_0 renders the furniture branch when victim->on.

    ROM src/act_info.c:304-401 — when victim->on != NULL, each of
    SLEEPING/RESTING/SITTING/STANDING renders "is <verb> <at|on|in> <furniture>."
    using the furniture short_descr and the AT/ON/IN bits in obj->value[2].
    Python previously only ported the on==NULL path (generic "is sitting here.").
    """
    room = Room(vnum=3001, name="Test Room", description="A test room.")
    observer = _pc("Observer")
    observer.act = int(PlayerFlag.HOLYLIGHT)

    chair = _furniture("a wooden chair", int(furn_flag))
    victim = _pc("Victim", position=position)
    victim.on = chair

    room.add_character(observer)
    room.add_character(victim)

    line = _room_occupant_line(observer, victim)
    assert expected in line, f"expected {expected!r} in {line!r}"


def test_room_occupant_line_no_furniture_keeps_here_suffix():
    """LOOK-018 guard: with victim->on == NULL the on-NULL suffix is unchanged."""
    room = Room(vnum=3001, name="Test Room", description="A test room.")
    observer = _pc("Observer")
    observer.act = int(PlayerFlag.HOLYLIGHT)
    victim = _pc("Victim", position=Position.SITTING)
    victim.on = None

    room.add_character(observer)
    room.add_character(victim)

    line = _room_occupant_line(observer, victim)
    assert "is sitting here." in line, line
