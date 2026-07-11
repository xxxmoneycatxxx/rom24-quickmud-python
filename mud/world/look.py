from __future__ import annotations

from mud.math.c_compat import c_div
from mud.models.character import Character
from mud.models.constants import LEVEL_HERO, AffectFlag, CommFlag, Direction, FurnitureFlag, PlayerFlag, Position
from mud.world.vision import can_see_character, pers

# mirroring ROM src/act_info.c show_char_to_char_0 — buf[0] = UPPER(buf[0]) and
# position suffixes appended when a mob is not at its start/default position.
# This is the victim->on == NULL path; the furniture branch is _FURNITURE_POSITION
# below (LOOK-018).
_POSITION_SUFFIX: dict[Position, str] = {
    Position.DEAD: " is DEAD!!",
    Position.MORTAL: " is mortally wounded.",
    Position.INCAP: " is incapacitated.",
    Position.STUNNED: " is lying here stunned.",
    Position.SLEEPING: " is sleeping here.",
    Position.RESTING: " is resting here.",
    Position.SITTING: " is sitting here.",
    Position.STANDING: " is here.",
    # FIGHTING: handled separately (target-aware)
}

# LOOK-018: ROM show_char_to_char_0 furniture branch (src/act_info.c:304-401).
# When victim->on != NULL these positions render "is <verb> <at|on|in>
# <furniture>." — the preposition comes from the furniture's value[2] bits
# (X_AT → "at", else X_ON → "on", else "in"). DEAD/MORTAL/INCAP/STUNNED have no
# furniture branch and fall back to _POSITION_SUFFIX.
_FURNITURE_POSITION: dict[Position, tuple[str, FurnitureFlag, FurnitureFlag]] = {
    Position.SLEEPING: ("sleeping", FurnitureFlag.SLEEP_AT, FurnitureFlag.SLEEP_ON),
    Position.RESTING: ("resting", FurnitureFlag.REST_AT, FurnitureFlag.REST_ON),
    Position.SITTING: ("sitting", FurnitureFlag.SIT_AT, FurnitureFlag.SIT_ON),
    Position.STANDING: ("standing", FurnitureFlag.STAND_AT, FurnitureFlag.STAND_ON),
}


def _furniture_position_suffix(position, on) -> str | None:
    """Return ROM's " is <verb> <at|on|in> <furniture>." suffix, or None.

    ``None`` when the position has no furniture branch (DEAD/MORTAL/INCAP/STUNNED)
    so the caller falls back to the on==NULL suffix table.
    mirroring ROM src/act_info.c:304-401 show_char_to_char_0.
    """
    entry = _FURNITURE_POSITION.get(position)
    if entry is None:
        return None
    verb, at_bit, on_bit = entry
    # obj->value[2] furniture position bitfield (cf. position.py::_furn_flags).
    values = getattr(on, "value", None) or getattr(getattr(on, "prototype", None), "value", None)
    flags = 0
    if values and len(values) >= 3:
        try:
            flags = int(values[2])
        except (TypeError, ValueError):
            flags = 0
    if flags & int(at_bit):
        prep = "at"
    elif flags & int(on_bit):
        prep = "on"
    else:
        prep = "in"
    short_descr = getattr(on, "short_descr", None) or getattr(getattr(on, "prototype", None), "short_descr", "") or ""
    return f" is {verb} {prep} {short_descr}."


def _char_tags(observer: Character, victim) -> str:
    """Build ROM show_char_to_char_0's status-tag prefix (src/act_info.c:253-276).

    The full fixed order is [AFK] (Invis) (Wizi) (Hide) (Charmed) (Translucent)
    (Pink Aura) (Red Aura) (Golden Aura) (White Aura) (KILLER) (THIEF). Red/Golden
    auras depend on the *observer* carrying detect-evil/good and the victim's
    alignment; KILLER/THIEF are PC-only PLR flags. Tags live here (the room
    listing), not in PERS/``describe_character`` — see ``pers`` docstring.
    """
    tags: list[str] = []
    has_affect = getattr(victim, "has_affect", None)

    if int(getattr(victim, "comm", 0) or 0) & int(CommFlag.AFK):
        tags.append("[AFK]")
    if callable(has_affect):
        if victim.has_affect(AffectFlag.INVISIBLE):
            tags.append("(Invis)")
    if int(getattr(victim, "invis_level", 0) or 0) >= LEVEL_HERO:
        tags.append("(Wizi)")
    if callable(has_affect):
        if victim.has_affect(AffectFlag.HIDE):
            tags.append("(Hide)")
        if victim.has_affect(AffectFlag.CHARM):
            tags.append("(Charmed)")
        if victim.has_affect(AffectFlag.PASS_DOOR):
            tags.append("(Translucent)")
        if victim.has_affect(AffectFlag.FAERIE_FIRE):
            tags.append("(Pink Aura)")

    victim_align = int(getattr(victim, "alignment", 0) or 0)
    obs_has_affect = getattr(observer, "has_affect", None)
    # ROM IS_EVIL: alignment <= -350; IS_GOOD: alignment >= 350.
    if victim_align <= -350 and callable(obs_has_affect) and observer.has_affect(AffectFlag.DETECT_EVIL):
        tags.append("(Red Aura)")
    if victim_align >= 350 and callable(obs_has_affect) and observer.has_affect(AffectFlag.DETECT_GOOD):
        tags.append("(Golden Aura)")

    if callable(has_affect) and victim.has_affect(AffectFlag.SANCTUARY):
        tags.append("(White Aura)")

    if not getattr(victim, "is_npc", False):
        victim_act = int(getattr(victim, "act", 0) or 0)
        if victim_act & int(PlayerFlag.KILLER):
            tags.append("(KILLER)")
        if victim_act & int(PlayerFlag.THIEF):
            tags.append("(THIEF)")

    return (" ".join(tags) + " ") if tags else ""


def _room_occupant_line(observer: Character, victim) -> str:
    """Render a room-list occupant — ROM src/act_info.c show_char_to_char_0.

    An NPC whose position equals its start/default position and which has a
    non-empty long_descr is listed by that long_descr (with the status tags
    prefixed), e.g. "Hassan is here, waiting to dispense some justice."
    Otherwise show PERS(victim) + a position suffix ("is resting here.", etc.).
    """
    # LOOK char-tags: ROM builds the full status-tag prefix (all 12) then appends
    # either long_descr or PERS. Use pers() for the base name (pure PERS, no aura
    # injection) so the tags render once and in ROM order — describe_character is
    # left for its combat/other callers, which a direct unit test locks.
    prefix = _char_tags(observer, victim)

    long_descr = getattr(victim, "long_descr", None)
    # ROM uses start_pos for the long_descr gate; Python stores default_pos (same
    # value for normally-spawned mobs).  Fall back to start_pos if present.
    ref_pos = getattr(victim, "start_pos", getattr(victim, "default_pos", None))
    if getattr(victim, "is_npc", False) and long_descr and getattr(victim, "position", None) == ref_pos:
        return prefix + str(long_descr).rstrip("\r\n")

    base = prefix + pers(victim, observer)
    position = getattr(victim, "position", None)
    # LOOK-017: ROM src/act_info.c:285-288 appends the victim's pcdata->title
    # after PERS for a standing PC — gated on the OBSERVER's COMM_BRIEF and
    # furniture (ch->comm / ch->on), a deliberate ROM quirk.
    if (
        not getattr(victim, "is_npc", False)
        and not (int(getattr(observer, "comm", 0) or 0) & int(CommFlag.BRIEF))
        and position == Position.STANDING
        and getattr(observer, "on", None) is None
    ):
        _pcdata = getattr(victim, "pcdata", None)
        _title = getattr(_pcdata, "title", None) if _pcdata is not None else None
        if _title:
            base += _title
    fighting = getattr(victim, "fighting", None)
    if position == Position.FIGHTING:
        # mirroring ROM src/act_info.c:404-417 show_char_to_char_0 POS_FIGHTING
        if fighting is None:
            fight_str = "thin air??"
        elif fighting is observer:
            fight_str = "YOU!"
        elif getattr(victim, "room", None) is getattr(fighting, "room", object()):
            # ROM src/act_info.c:412 uses PERS(victim->fighting, ch) — the bare
            # name, NOT the show_char_to_char aura block. describe_character injects
            # (Pink/White Aura), which ROM never shows here (FINDING-043, same class
            # as the scan FINDING-042 aura/PERS leak).
            fight_str = pers(fighting, observer) + "."
        else:
            fight_str = "someone who left??"
        line = base + " is here, fighting " + fight_str
    else:
        # LOOK-018: victim->on furniture branch takes precedence over the generic
        # on==NULL suffix. mirroring ROM src/act_info.c:304-401 show_char_to_char_0.
        on = getattr(victim, "on", None)
        furn_suffix = _furniture_position_suffix(position, on) if on is not None else None
        if furn_suffix is not None:
            line = base + furn_suffix
        else:
            suffix = _POSITION_SUFFIX.get(position, "") if position is not None else ""
            line = base + suffix
    # mirroring ROM src/act_info.c:421 buf[0] = UPPER(buf[0])
    return line[0].upper() + line[1:] if line else line


def _ed_fields(ed) -> tuple[str | None, str | None]:
    """Return (keyword, description) for an EXTRA_DESCR entry.

    JSON-loaded prototypes store extra_descr as raw dicts (per ObjIndex's
    `list[dict]` annotation); runtime ObjectData/ExtraDescr instances expose
    them as attributes. Accept both shapes.
    """
    if isinstance(ed, dict):
        return ed.get("keyword"), ed.get("description")
    return getattr(ed, "keyword", None), getattr(ed, "description", None)


dir_names = {
    Direction.NORTH: "north",
    Direction.EAST: "east",
    Direction.SOUTH: "south",
    Direction.WEST: "west",
    Direction.UP: "up",
    Direction.DOWN: "down",
}


def look(char: Character, args: str = "") -> str:
    """
    Look command handler - ROM src/act_info.c do_look

    Supports:
    - look (show room)
    - look <character> (examine character)
    - look <object> (examine object)
    - look in <container> (show container contents)
    - look <direction> (peek through exit)
    """
    from mud.world.char_find import get_char_room
    from mud.world.obj_find import get_obj_carry, get_obj_here

    room = char.room
    if not room:
        return "You are floating in a void..."

    # Check position - ROM src/act_info.c lines 1053-1063
    position = getattr(char, "position", Position.STANDING)
    if position < Position.SLEEPING:
        return "You can't see anything but stars!"
    if position == Position.SLEEPING:
        return "You can't see anything, you're sleeping!"

    # Check blind - ROM src/act_info.c lines 1065-1066
    from mud.world.vision import check_blind

    if not check_blind(char):
        return "You can't see a thing!"

    # Check dark room - ROM src/act_info.c lines 1068-1074
    from mud.models.constants import PlayerFlag
    from mud.world.vision import room_is_dark

    is_npc = getattr(char, "is_npc", False)
    # mirroring ROM src/act_info.c:1068-1069 — the gate is
    # !IS_NPC && !IS_SET(ch->act, PLR_HOLYLIGHT) && room_is_dark (LOOK-006).
    try:
        has_holylight = bool(int(getattr(char, "act", 0) or 0) & int(PlayerFlag.HOLYLIGHT))
    except (TypeError, ValueError):
        has_holylight = False
    if not is_npc and not has_holylight and room_is_dark(room):
        lines = ["It is pitch black ..."]
        for occupant in room.people:
            if occupant is char:
                continue
            if not can_see_character(char, occupant):
                continue
            # mirroring ROM src/act_info.c show_char_to_char: when can_see is
            # True even in a dark room, show_char_to_char_0 is called (same as
            # the lit-room path) — not just the PERS name.
            lines.append(_room_occupant_line(char, occupant))
        return "\n".join(lines)

    # Parse arguments
    args = args.strip()
    if not args or args.lower() == "auto":
        # 'look' or 'look auto' - show room
        return _look_room(char, room)

    # Check for "look in <container>"
    parts = args.split(None, 1)
    if parts[0].lower() in ("i", "in", "on") and len(parts) > 1:
        return _look_in(char, parts[1])

    # Check for direction
    direction = _parse_direction(args)
    if direction is not None:
        return _look_direction(char, room, direction)

    # Try to find a character in the room
    victim = get_char_room(char, args)
    if victim:
        return _look_char(char, victim)

    # Try to find an object in the room or inventory
    obj = get_obj_here(char, args)
    if obj:
        return _look_obj(char, obj, args)

    # Check inventory
    obj = get_obj_carry(char, args)
    if obj:
        return _look_obj(char, obj, args)

    # Check extra descriptions in room
    for ed in getattr(room, "extra_descr", []):
        keyword, description = _ed_fields(ed)
        if keyword and args.lower() in keyword.lower().split():
            return description or "You see nothing special."

    return "You do not see that here."


def _look_room(char: Character, room) -> str:
    """Show room description - ROM src/act_info.c lines 1081-1116"""
    lines = []

    # Room name with optional vnum for immortals/builders - ROM src/act_info.c lines 1088-1094
    from mud.models.constants import LEVEL_IMMORTAL, PlayerFlag

    level = getattr(char, "level", 1)
    act_flags = getattr(char, "act", 0)
    is_immortal = level >= LEVEL_IMMORTAL
    has_holylight = act_flags & PlayerFlag.HOLYLIGHT
    is_builder = False  # TODO: Implement IS_BUILDER check when area builders are added

    room_name = room.name or ""
    if (is_immortal and (getattr(char, "is_npc", False) or has_holylight)) or is_builder:
        # Show room vnum for immortals with holylight or builders
        vnum = getattr(room, "vnum", 0)
        lines.append(f"[Room {vnum}] {room_name}")
    else:
        lines.append(room_name)

    # Room description - ROM src/act_info.c lines 1098-1105
    # Skip description if COMM_BRIEF is set
    from mud.models.constants import CommFlag

    comm_flags = getattr(char, "comm", 0)
    if not (comm_flags & CommFlag.BRIEF):
        room_desc = room.description or ""
        lines.append(room_desc)

    # Objects in room — ROM src/act_info.c:1106
    # show_list_to_char(ch->in_room->contents, ch, FALSE, FALSE)
    # Uses f_short=False (ground description), f_show_nothing=False (no "Nothing."),
    # can_see_obj visibility filter, and COMBINE coalescing for NPC/COMBINE viewers.
    from mud.utils.act import show_list_to_char

    obj_text = show_list_to_char(room.contents, char, f_short=False, f_show_nothing=False)
    if obj_text:
        lines.append(obj_text.rstrip("\n"))

    # Characters in room — ROM appends raw character lines via show_char_to_char.
    for occupant in room.people:
        if occupant is char:
            continue
        if not can_see_character(char, occupant):
            continue
        lines.append(_room_occupant_line(char, occupant))

    result = "\n".join(lines).strip()

    # AUTOEXIT integration - ROM src/act_info.c lines 1107-1111
    # Auto-show exits if PLR_AUTOEXIT is set
    from mud.commands.inspection import do_exits
    from mud.models.constants import PlayerFlag

    if not getattr(char, "is_npc", False) and (act_flags & PlayerFlag.AUTOEXIT):
        # Call do_exits with "auto" to get concise exit display
        exit_text = do_exits(char, "auto")
        if exit_text:
            result += "\n" + exit_text

    return result


def _look_char(char: Character, victim: Character) -> str:
    """Show character description - ROM src/act_info.c show_char_to_char_1"""
    # LOOK-007: ROM show_char_to_char_1 (src/act_info.c:438-446) broadcasts the look,
    # gated by can_see(victim, ch) — the victim must be able to see the looker.
    room = getattr(char, "room", None)
    if room is not None and can_see_character(victim, char):
        from mud.utils.act import act_format, act_to_room
        from mud.utils.messaging import push_message

        if victim is char:
            act_to_room(room, "$n looks at $mself.", char, exclude=char)
        else:
            push_message(victim, act_format("$n looks at you.", recipient=victim, actor=char))
            act_to_room(room, "$n looks at $N.", char, arg2=victim, exclude=victim)

    lines = []

    # Show description
    desc = getattr(victim, "description", None)
    if desc:
        lines.append(desc)
    else:
        # ROM src/act_info.c:453 — act("You see nothing special about $M.", ch,
        # NULL, victim, TO_CHAR): $M renders the victim's OBJECTIVE PRONOUN
        # (him/her/it), NOT the name/short_descr (LOOK-009). A sexless char — and
        # any self-look on one — renders "it".
        from mud.utils.act import act_format

        lines.append(act_format("You see nothing special about $M.", recipient=char, actor=char, arg2=victim))

    # Show health condition - ROM health_str equivalent
    max_hit = getattr(victim, "max_hit", 100) or 100
    hit = getattr(victim, "hit", max_hit)
    # ROM src/act_info.c:456-459 — `percent = max_hit > 0 ? 100*hit/max_hit : -1`.
    # The -1 (NOT 100) buckets a non-positive max_hit to the worst tier. Reachable
    # for negative max_hit since ARITH-208 (a mob can spawn with dice()+bonus < 0).
    percent = c_div(hit * 100, max_hit) if max_hit > 0 else -1

    short = getattr(victim, "short_descr", None) or getattr(victim, "name", "Someone")
    if percent >= 100:
        condition = f"{short} is in excellent condition."
    elif percent >= 90:
        condition = f"{short} has a few scratches."
    elif percent >= 75:
        condition = f"{short} has some small wounds and bruises."
    elif percent >= 50:
        condition = f"{short} has quite a few wounds."
    elif percent >= 30:
        condition = f"{short} has some big nasty wounds and scratches."
    elif percent >= 15:
        condition = f"{short} looks pretty hurt."
    elif percent >= 0:
        condition = f"{short} is in awful condition."
    else:
        condition = f"{short} is bleeding to death."
    # ROM src/act_info.c:480 — `buf[0] = UPPER(buf[0])` capitalizes the first
    # char of the health line, so a mob's lowercase short_descr ("the beastly
    # fido ...") renders "The beastly fido ..." (LOOK-014).
    condition = condition[0].upper() + condition[1:] if condition else condition
    lines.append(condition)

    # Show equipment if visible — ROM src/act_info.c:483-499 (LOOK-016).
    equipment = _show_equipment(victim, char)
    if equipment:
        # ROM act("$N is using:", ...) capitalizes the rendered first char.
        header = f"{short} is using:"
        header = header[0].upper() + header[1:]
        lines.append(f"\n{header}")
        lines.append(equipment)

    return "\n".join(lines)


def _show_equipment(victim: Character, observer: Character) -> str:
    """Show *victim*'s equipped items to *observer* — ROM show_char_to_char_1.

    LOOK-016: mirrors ROM ``src/act_info.c:483-499`` — loop wear slots in
    ascending order, gate each on ``can_see_obj(observer, obj)``, and render
    ``where_name[iWear] + format_obj_to_char(obj, observer, TRUE)`` (no indent,
    with aura/status tags). The prior code read a **phantom** ``equipped``
    attribute (via ``getattr``) where the real one is ``char.equipment``
    (int-keyed by WearLocation), so the whole block was dead — the equipment-key
    convention class via a wrong attribute NAME, invisible to the string-key
    grep-guard.
    """
    from mud.models.constants import WearLocation  # noqa: F401  (enum keys hash-equal to int)
    from mud.utils.act import format_obj_to_char
    from mud.world.vision import can_see_object

    wear_names = {
        WearLocation.LIGHT: "<used as light>     ",
        WearLocation.FINGER_L: "<worn on finger>    ",
        WearLocation.FINGER_R: "<worn on finger>    ",
        WearLocation.NECK_1: "<worn around neck>  ",
        WearLocation.NECK_2: "<worn around neck>  ",
        WearLocation.BODY: "<worn on torso>     ",
        WearLocation.HEAD: "<worn on head>      ",
        WearLocation.LEGS: "<worn on legs>      ",
        WearLocation.FEET: "<worn on feet>      ",
        WearLocation.HANDS: "<worn on hands>     ",
        WearLocation.ARMS: "<worn on arms>      ",
        WearLocation.SHIELD: "<worn as shield>    ",
        WearLocation.ABOUT: "<worn about body>   ",
        WearLocation.WAIST: "<worn about waist>  ",
        WearLocation.WRIST_L: "<worn around wrist> ",
        WearLocation.WRIST_R: "<worn around wrist> ",
        WearLocation.WIELD: "<wielded>           ",
        WearLocation.HOLD: "<held>              ",
        WearLocation.FLOAT: "<floating nearby>   ",
    }

    lines = []
    equipment = getattr(victim, "equipment", {})
    if isinstance(equipment, dict):
        # ROM iterates iWear 0..MAX_WEAR ascending; equipment is int-keyed.
        for slot in sorted(equipment.keys()):
            obj = equipment[slot]
            if obj is None or not can_see_object(observer, obj):
                continue
            loc_name = wear_names.get(slot, "<unknown>           ")
            lines.append(f"{loc_name}{format_obj_to_char(obj, observer, True)}")

    return "\n".join(lines)


def _look_obj(char: Character, obj, keyword: str = "") -> str:
    """ROM ``do_look`` object resolution — src/act_info.c:1179-1213.

    For the looked-at object, an extra description whose keyword matches the
    lookup argument is shown **alone** (ED-priority, mutually exclusive with the
    object's ``description``); only when *no* ED matches does a bare name match
    show ``obj->description``. ROM never shows the description AND an extra
    description together — the prior implementation appended the first ED
    unconditionally (regardless of the lookup keyword), which is the
    LOOK / FINDING-021/022/033 act-rendering divergence surfaced by
    ``examine`` on a money pile (LOOK-008). Instance ``extra_descr`` take
    priority over the prototype's, mirroring ROM's two `get_extra_descr` calls.
    """
    from mud.world.char_find import is_name

    # ROM matches against arg3 — the single keyword `one_argument` yields after
    # `number_argument` strips any leading "N." selector.
    key = (keyword or "").strip()
    if key:
        key = key.split()[0]
        if "." in key and key.split(".", 1)[0].lstrip("-").isdigit():
            key = key.split(".", 1)[1]

    if key:
        instance_eds = getattr(obj, "extra_descr", []) or []
        prototype = getattr(obj, "prototype", None)
        proto_eds = (getattr(prototype, "extra_descr", []) or []) if prototype else []
        # ROM src/act_info.c:1183-1205 — instance EDs, then prototype EDs; the
        # first whose keyword matches the argument is shown and resolution stops.
        for ed in (*instance_eds, *proto_eds):
            ed_keyword, description = _ed_fields(ed)
            if ed_keyword and description and is_name(key, ed_keyword):
                return description

    # ROM src/act_info.c:1207-1212 — name match (no ED match): show description.
    desc = getattr(obj, "description", None)
    if desc:
        return desc
    short = getattr(obj, "short_descr", None) or getattr(obj, "name", "something")
    return f"You see nothing special about {short}."


def _look_in(char: Character, args: str) -> str:
    """Look inside a container - ROM src/act_info.c lines 1070-1130"""
    from mud.models.constants import LIQUID_TABLE, ContainerFlag, ItemType
    from mud.utils.act import capitalize_act_line
    from mud.world.obj_find import get_obj_here

    obj = get_obj_here(char, args)
    if not obj:
        return "You do not see that here."

    item_type = getattr(obj, "item_type", 0)

    if item_type == ItemType.DRINK_CON:
        value = getattr(obj, "value", [0, 0, 0, 0, 0])
        if len(value) < 3:
            return "It is empty."
        if value[1] <= 0:
            return "It is empty."
        if value[0] > 0:
            # LOOK-015: mirror ROM's exact integer comparisons
            # (src/act_info.c:1141-1145) — `value[1] < value[0]/4` and
            # `value[1] < 3*value[0]/4`. A rewritten `value[1]*100//value[0]`
            # percentage truncates at a different point and mislabels boundary
            # amounts (e.g. value=(10,2): ROM "about half-", percent form
            # "less than half-"). value[0]/value[1] are non-negative, so // == C /.
            if value[1] < value[0] // 4:
                amount = "less than half-"
            elif value[1] < 3 * value[0] // 4:
                amount = "about half-"
            else:
                amount = "more than half-"
        else:
            amount = ""
        liquid_index = int(value[2]) if len(value) > 2 else 0
        if 0 <= liquid_index < len(LIQUID_TABLE):
            liquid_color = LIQUID_TABLE[liquid_index].color
        else:
            liquid_color = "clear"
        return f"It's {amount}filled with  a {liquid_color} liquid."

    if item_type in (ItemType.CONTAINER, ItemType.CORPSE_NPC, ItemType.CORPSE_PC):
        value = getattr(obj, "value", [0, 0, 0, 0, 0])
        if len(value) > 1 and (value[1] & int(ContainerFlag.CLOSED)):
            return "It is closed."

        # ROM src/act_info.c:1166-1167 — `act("$p holds:")` then
        # `show_list_to_char(obj->contains, ch, TRUE, TRUE)`. `act_new` caps the
        # header's first visible char (INV-029 ACT-CAP), so "a bag" → "A bag
        # holds:". `show_list_to_char` then formats the contents: for NPC or
        # COMM_COMBINE viewers, duplicates are coalesced with `(%2d) ` counts or
        # 5-space padding; for non-COMBINE PCs, items are listed with no indent.
        # FINDING-022: the old code always prepended 2-space indent, matching
        # neither the no-indent PC path nor the 5-space COMBINE path.
        short = getattr(obj, "short_descr", None) or "It"
        header = capitalize_act_line(f"{short} holds:")

        contents = getattr(obj, "contains", None) or getattr(obj, "contained_items", [])
        from mud.utils.act import show_list_to_char

        body = show_list_to_char(contents, char, f_short=True, f_show_nothing=True)
        # show_list_to_char returns trailing \n; strip it since we join with \n
        return header + "\n" + body.rstrip("\n")

    return "That is not a container."


def _look_direction(char: Character, room, direction: int) -> str:
    """Look in a direction - ROM src/act_info.c lines 1268-1312"""
    exits = getattr(room, "exits", [])
    if direction >= len(exits) or not exits[direction]:
        return "Nothing special there."

    exit_obj = exits[direction]
    lines = []

    # Show exit description if present
    desc = getattr(exit_obj, "description", None)
    if desc:
        lines.append(desc)

    # Show door status - ROM src/act_info.c lines 1298-1309
    keyword = getattr(exit_obj, "keyword", None)
    exit_info = getattr(exit_obj, "exit_info", 0)

    # ROM merc.h: EX_ISDOOR = (A) = 1, EX_CLOSED = (B) = 2. Never hardcode these
    # (AGENTS.md flag-values rule) — the values below were previously swapped,
    # so every keyword'd door (which always has the ISDOOR bit) rendered as
    # "closed" even when open (LOOK-012).
    from mud.models.constants import EX_CLOSED, EX_ISDOOR

    if keyword and keyword.strip():
        if exit_info & EX_CLOSED:
            lines.append(f"The {keyword} is closed.")
        elif exit_info & EX_ISDOOR:
            lines.append(f"The {keyword} is open.")

    if lines:
        return "\n".join(lines)
    return "Nothing special there."


def _parse_direction(arg: str) -> int | None:
    """Parse direction argument"""
    dir_map = {
        "n": 0,
        "north": 0,
        "e": 1,
        "east": 1,
        "s": 2,
        "south": 2,
        "w": 3,
        "west": 3,
        "u": 4,
        "up": 4,
        "d": 5,
        "down": 5,
    }
    return dir_map.get(arg.lower())
