"""LOCK-003 — the door lock/unlock key guard uses ROM's `pexit->key < 0`.

ROM `do_lock`/`do_unlock` door branches gate on `pexit->key < 0`
(`src/act_move.c:669`, `:805`): a key vnum of exactly 0 is NOT "can't be
locked" — it falls through to `has_key(ch, 0)`, which no real object matches,
so the actor gets "You lack the key." The port used `key_vnum <= 0`, which
wrongly treated a `key: 0` exit as unlockable ("It can't be [un]locked.").

This is the EXIT-arm sibling of LOCK-002 (the container arm, already `< 0`).
It is latent in stock data — every JSON exit `key` is `-1` — but a future area
authored with `key: 0` would diverge, so the guard is corrected for
source-faithfulness (the WEAR-016/017 / DESC-001 pattern).
"""

from __future__ import annotations

import pytest

from mud.commands.doors import do_lock, do_unlock
from mud.models.character import Character, PCData
from mud.models.constants import EX_CLOSED, EX_ISDOOR, EX_LOCKED
from mud.models.room import Exit, Room
from mud.registry import room_registry


@pytest.fixture
def room_with_key0_door():
    room = Room(vnum=99751, name="Key0 Probe")
    room.people = []
    room.contents = []
    room.exits = [None] * 6
    room_registry[99751] = room

    # Closed door east with key vnum 0 (the reachable-only-via-custom-data case).
    exit_e = Exit(vnum=0, exit_info=EX_ISDOOR | EX_CLOSED, keyword="door", key=0)
    exit_e.to_room = None
    room.exits[1] = exit_e

    actor = Character(name="Locker", level=10, room=room, is_npc=False, position=5)
    actor.pcdata = PCData()
    actor.messages = []
    actor.inventory = []  # no key of any vnum
    room.people.append(actor)

    yield actor, exit_e, room

    room_registry.pop(99751, None)


def test_lock_key0_door_reports_lack_of_key_not_cant_be_locked(room_with_key0_door):
    actor, _exit_e, _room = room_with_key0_door
    # ROM: key (0) is not < 0 → has_key(ch, 0) fails → "You lack the key."
    assert do_lock(actor, "east") == "You lack the key."


def test_unlock_key0_door_reports_lack_of_key_not_cant_be_unlocked(room_with_key0_door):
    actor, exit_e, _room = room_with_key0_door
    exit_e.exit_info = EX_ISDOOR | EX_CLOSED | EX_LOCKED
    # ROM: key (0) is not < 0 → has_key(ch, 0) fails → "You lack the key."
    assert do_unlock(actor, "east") == "You lack the key."
