"""DB-002 — pet-affect load dedup must match ROM ``check_pet_affected``.

ROM ``check_pet_affected`` (``src/db.c:3938``) is called by ``fread_pet``
(``src/save.c:1567``) for every ``Affc`` line read off a saved pet. It drops the
affect (prevents duplication) if — and only if —::

    paf->where == TO_AFFECTS  &&  IS_AFFECTED(get_mob_index(vnum), paf->bitvector)

i.e. the affect targets the ``affected_by`` bitfield AND at least one of its bits
is already inherent on the pet's **prototype** (``get_mob_index(vnum)->affected_by``).
This is the JR-2002 fix: without it, a spell that grants a bit the prototype
already has gets re-added on reload, and when the temporary affect wears off
``affect_modify`` strips the shared bit — clearing the pet's *inherent* flag too.

The Python port (``_deserialize_pet``) instead deduped on a ``(type, location,
modifier)`` match against the prototype's ``affected`` *list*, ignoring both
``where`` and ``bitvector`` — a different field and a different criterion, so the
real ROM dedup never fired. This test pins the ROM contract.
"""

from __future__ import annotations

from mud.db.serializers import PetAffectSave, PetSave, _deserialize_pet
from mud.models.constants import AffectFlag
from mud.models.mob import MobIndex
from mud.registry import mob_registry
from mud.world import create_test_character, initialize_world

# Skill slots (from data/skills.json): sanctuary=36, infravision=77,
# detect invis=19 — asserted by SN on the restored pet.affected list.
_SANCTUARY_SN = 36
_INFRAVISION_SN = 77
_DETECT_INVIS_SN = 19
_TEST_VNUM = 9998


def _register_warded_prototype() -> None:
    # Letter "H" == AFF_SANCTUARY (see AffectFlag.SANCTUARY comment). The pet
    # prototype is thus inherently sanctuary'd — get_mob_index(vnum)->affected_by
    # carries the SANCTUARY bit.
    mob_registry[_TEST_VNUM] = MobIndex(vnum=_TEST_VNUM, short_descr="a warded pet", level=10, affected_by="H")


def test_check_pet_affected_matches_rom_where_and_bitvector():
    initialize_world("area/area.lst")
    owner = create_test_character("PetOwner", 3001)
    _register_warded_prototype()
    try:
        snap = PetSave(
            vnum=_TEST_VNUM,
            name="pet",
            level=10,
            affects=[
                # A — TO_AFFECTS, bit already inherent on the prototype:
                #     ROM check_pet_affected() → TRUE → affect DROPPED.
                PetAffectSave(
                    skill_name="sanctuary",
                    where=0,  # TO_AFFECTS
                    level=10,
                    duration=6,
                    bitvector=int(AffectFlag.SANCTUARY),
                ),
                # B — TO_AFFECTS, bit NOT inherent: not a duplicate → KEPT.
                PetAffectSave(
                    skill_name="infravision",
                    where=0,  # TO_AFFECTS
                    level=10,
                    duration=6,
                    bitvector=int(AffectFlag.INFRARED),
                ),
                # C — bit overlaps the inherent SANCTUARY, but where != TO_AFFECTS:
                #     ROM only dedups TO_AFFECTS affects → KEPT.
                PetAffectSave(
                    skill_name="detect invis",
                    where=1,  # TO_OBJECT (not TO_AFFECTS)
                    level=10,
                    duration=6,
                    bitvector=int(AffectFlag.SANCTUARY),
                ),
            ],
        )
        pet = _deserialize_pet(snap, owner)
        assert pet is not None
        restored = {a.type for a in pet.affected}

        # A: sanctuary is inherent on the prototype → deduped per ROM.
        assert _SANCTUARY_SN not in restored, "TO_AFFECTS affect matching an inherent prototype bit must be dropped"
        # B: infravision bit not inherent → kept.
        assert _INFRAVISION_SN in restored, "non-duplicate TO_AFFECTS affect must be kept"
        # C: where != TO_AFFECTS → never deduped, even with an overlapping bit.
        assert _DETECT_INVIS_SN in restored, "non-TO_AFFECTS affect must not be deduped"
    finally:
        mob_registry.pop(_TEST_VNUM, None)
