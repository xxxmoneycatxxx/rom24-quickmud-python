"""TRIP-002: a failed `do_trip` delivers the miss dam_message exactly ONCE.

ROM `do_trip`'s failure branch (`src/fight.c:2749`) is:

    damage (ch, victim, 0, gsn_trip, DAM_BASH, TRUE);   # show = TRUE

`do_trip` is a **void** function — `damage()` delivers the miss dam_message to
the attacker (and victim/room) once via its own `act()`; there is no
return-value channel. The port called `apply_damage(..., show=True)` — which
pushes the attacker's miss line to `char.messages` — and then **returned that
same line**. The connection loop delivers a command's return value AND drains
`char.messages`, so a connected attacker saw `Your trip misses X.` twice
(INV-001 SINGLE-DELIVERY / the FIGHT-020 double-delivery shape). The fix
discards `apply_damage`'s return so the push is the single delivery.
"""

from __future__ import annotations

import pytest

from mud.commands.combat import do_trip
from mud.models.constants import Position
from mud.utils import rng_mm
from mud.world import create_test_character, initialize_world

_ROOM = 3001


@pytest.fixture(autouse=True)
def _world():
    initialize_world("area/area.lst")


def test_trip_miss_delivers_miss_line_once(monkeypatch: pytest.MonkeyPatch) -> None:
    char = create_test_character("Tripper", _ROOM)
    victim = create_test_character("Victim", _ROOM)
    char.is_npc = False
    char.skills["trip"] = 1  # low skill
    char.messages = []
    victim.is_npc = True
    victim.position = Position.FIGHTING
    victim.hit = 200
    victim.max_hit = 200
    char.fighting = victim
    victim.fighting = char

    # Force a miss (number_percent well above any chance).
    monkeypatch.setattr(rng_mm, "number_percent", lambda: 100)

    ret = do_trip(char, "")

    # ROM do_trip is void — the failure branch returns nothing to the connection
    # loop's return-value channel; the miss line reaches the attacker via the
    # single push done inside damage()/apply_damage.
    assert ret == "", f"failure branch must not return the miss line (double-delivery); got {ret!r}"

    miss_lines = [m for m in char.messages if "miss" in m.lower()]
    assert len(miss_lines) == 1, f"miss line must be delivered exactly once; mailbox={char.messages}"
