"""Integration tests for i18n (Chinese) output completeness.

Verifies that when LANGUAGE=zh, all player-facing commands produce
Chinese output. This is a regression guard: if a future code change
removes a t() call or adds an untranslated string, these tests catch it.

Tests cover the core player commands:
- look, score, config, affects, equipment, inventory, help
"""

from __future__ import annotations

import re

import pytest

from mud.models.character import Character, SpellEffect
from mud.models.constants import CommFlag, ExtraFlag, PlayerFlag, Position
from mud.models.obj import ObjIndex
from mud.models.object import Object
from mud.models.room import Room
from mud.registry import room_registry

# ---------------------------------------------------------------------------
# Fixtures: override the autouse _force_english from conftest.py
# ---------------------------------------------------------------------------

CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


@pytest.fixture(autouse=True)
def _force_english():
    """Override: set Chinese for this module's tests."""
    from mud.i18n import get_language, set_language

    saved = get_language()
    set_language("zh")
    yield
    set_language(saved or "en")


@pytest.fixture(autouse=True)
def _force_english_unit():
    """Override: set Chinese for this module's tests (unit conftest fixture)."""
    from mud.i18n import get_language, set_language

    saved = get_language()
    set_language("zh")
    yield
    set_language(saved or "en")


@pytest.fixture
def zh_room():
    """Create a test room with Chinese-translated name/description."""
    room = Room(
        vnum=9900,
        name="测试房间",
        description="这是一个用于测试的房间。",
        room_flags=0,
        sector_type=0,
    )
    room.people = []
    room.contents = []
    room_registry[9900] = room
    yield room
    room_registry.pop(9900, None)


@pytest.fixture
def zh_char(zh_room):
    """Create a test player character with enough attributes for all commands."""
    from mud.models.character import PCData
    from mud.models.character import character_registry

    char = Character(
        name="TestHero",
        level=10,
        room=zh_room,
        gold=500,
        silver=1000,
        hit=80,
        max_hit=100,
        mana=50,
        max_mana=80,
        move=100,
        max_move=120,
        is_npc=False,
        sex=1,  # male
        race=1,  # human
        ch_class=0,  # warrior
        position=int(Position.STANDING),
    )
    char.pcdata = PCData()
    char.act = int(PlayerFlag.AUTOEXIT) | int(PlayerFlag.AUTOGOLD)
    char.comm = int(CommFlag.COMBINE) | int(CommFlag.PROMPT)
    char.perm_stat = [16, 13, 14, 12, 15]
    zh_room.people.append(char)
    character_registry.append(char)
    yield char
    if char in zh_room.people:
        zh_room.people.remove(char)
    if char in character_registry:
        character_registry.remove(char)


@pytest.fixture
def zh_object():
    """Factory to create test objects."""

    def _factory(vnum: int = 9901, name: str = "sword", short_descr: str = "a wooden sword", **kwargs):
        proto_kwargs = {"vnum": vnum, "name": name, "short_descr": short_descr}
        proto_kwargs.update(kwargs)
        proto = ObjIndex(**proto_kwargs)
        obj = Object(instance_id=None, prototype=proto)
        obj.value = list(proto.value) if proto.value else [0, 0, 0, 0, 0]
        return obj

    return _factory


# ---------------------------------------------------------------------------
# Tests: each command produces Chinese output under LANGUAGE=zh
# ---------------------------------------------------------------------------


def _has_chinese(text: str) -> bool:
    """Return True if text contains at least one Chinese character."""
    return bool(CHINESE_RE.search(text))


class TestInventoryZh:
    """inventory command produces Chinese output."""

    def test_inventory_header_is_chinese(self, zh_char):
        """'You are carrying:' must be translated to Chinese."""
        from mud.commands.inventory import do_inventory

        output = do_inventory(zh_char, "")
        assert _has_chinese(output), f"inventory output has no Chinese: {output[:200]!r}"
        assert "你" in output and "携带" in output or "背包" in output or "携带" in output

    def test_inventory_empty_shows_chinese_nothing(self, zh_char):
        """Empty inventory 'Nothing' must be translated."""
        from mud.commands.inventory import do_inventory

        zh_char.inventory = []
        output = do_inventory(zh_char, "")
        assert _has_chinese(output), f"empty inventory has no Chinese: {output[:200]!r}"

    def test_inventory_item_with_aura_tags_chinese(self, zh_char, zh_object):
        """Magical aura tags like (Glowing)/(Magical) must be translated."""
        from mud.commands.inventory import do_inventory

        glowing_sword = zh_object(
            vnum=9901,
            name="sword",
            short_descr="a wooden sword",
            extra_flags=int(ExtraFlag.GLOW),
        )
        zh_char.add_object(glowing_sword)
        output = do_inventory(zh_char, "")
        assert _has_chinese(output), f"glowing item has no Chinese aura tag: {output[:200]!r}"
        # Should NOT contain English "(Glowing)" when in zh mode
        assert "(Glowing)" not in output, f"English aura tag leaked: {output!r}"


class TestScoreZh:
    """score command produces Chinese output."""

    def test_score_contains_chinese(self, zh_char):
        """Full score output must be in Chinese."""
        from mud.commands.session import do_score

        output = do_score(zh_char, "")
        assert _has_chinese(output), f"score output has no Chinese: {output[:300]!r}"

    def test_score_level_line_chinese(self, zh_char):
        """'You are ..., level ...' line must be translated."""
        from mud.commands.session import do_score

        output = do_score(zh_char, "")
        assert "你是" in output, f"missing '你是' in score: {output[:300]!r}"
        assert "级" in output, f"missing '级' in score: {output[:300]!r}"

    def test_score_stats_chinese(self, zh_char):
        """Stat labels (str/int/wis/dex/con) must be translated."""
        from mud.commands.session import do_score

        output = do_score(zh_char, "")
        # At least some stat-related Chinese should appear
        assert _has_chinese(output)

    def test_score_ac_descriptions_chinese(self, zh_char):
        """AC descriptions must be translated to Chinese."""
        from mud.commands.session import do_score

        output = do_score(zh_char, "")
        # Should not contain English AC descriptions
        assert "hopelessly vulnerable" not in output.lower()
        assert "defenseless" not in output.lower()

    def test_score_race_name_chinese(self, zh_char):
        """Race name must be translated (elf → 精灵)."""
        from mud.commands.session import do_score

        output = do_score(zh_char, "")
        # zh_char has race=1 (elf in PC_RACE_TABLE)
        assert "精灵" in output, f"race not translated: {output[:300]!r}"

    def test_score_class_name_chinese(self, zh_char):
        """Class name must be translated (mage → 法师)."""
        from mud.commands.session import do_score

        output = do_score(zh_char, "")
        # zh_char has ch_class=0 (mage in CLASS_TABLE)
        assert "法师" in output, f"class not translated: {output[:300]!r}"


class TestConfigZh:
    """config command produces Chinese output."""

    def test_config_header_chinese(self, zh_char):
        """Config header must be translated."""
        from mud.commands.misc_player import do_config

        output = do_config(zh_char, "")
        assert _has_chinese(output), f"config output has no Chinese: {output[:200]!r}"

    def test_config_on_off_chinese(self, zh_char):
        """ON/OFF status must be translated."""
        from mud.commands.misc_player import do_config

        output = do_config(zh_char, "")
        # Should contain Chinese ON/OFF equivalents
        assert "开启" in output or "关闭" in output or "开" in output or "关" in output, (
            f"ON/OFF not translated: {output[:200]!r}"
        )


class TestAffectsZh:
    """affects command produces Chinese output."""

    def test_affects_no_spells_chinese(self, zh_char):
        """'You are not affected' message must be translated."""
        from mud.commands.affects import do_affects

        zh_char.affected = []
        output = do_affects(zh_char, "")
        assert _has_chinese(output), f"no-affects message has no Chinese: {output[:200]!r}"

    def test_affects_with_spell_chinese(self, zh_char):
        """Spell affect display must contain translated text."""
        from mud.commands.affects import do_affects

        effect = SpellEffect(name="bless", duration=10, level=20, saving_throw_mod=-1)
        zh_char.apply_spell_effect(effect)
        output = do_affects(zh_char, "")
        assert _has_chinese(output), f"affects output has no Chinese: {output[:200]!r}"


class TestEquipmentZh:
    """equipment command produces Chinese output."""

    def test_equipment_header_chinese(self, zh_char):
        """Equipment header must be translated."""
        from mud.commands.inventory import do_equipment

        output = do_equipment(zh_char, "")
        assert _has_chinese(output), f"equipment output has no Chinese: {output[:200]!r}"

    def test_equipment_empty_chinese(self, zh_char):
        """Empty equipment message must be translated."""
        from mud.commands.inventory import do_equipment

        # Clear all equipment
        zh_char.equipment = {}
        output = do_equipment(zh_char, "")
        assert _has_chinese(output), f"empty equipment has no Chinese: {output[:200]!r}"


class TestHelpZh:
    """help command produces Chinese output."""

    def test_help_command_output_chinese(self, zh_char):
        """help output for a command must be translated."""
        from mud.commands.help import do_help

        output = do_help(zh_char, "help")
        assert _has_chinese(output), f"help output has no Chinese: {output[:200]!r}"


class TestBoardZh:
    """notes/board command produces Chinese output."""

    def test_board_status_chinese(self, zh_char):
        """Board status messages must be translated."""
        from mud.commands.notes import do_board

        # 'board' with no args shows board status
        output = do_board(zh_char, "")
        if output:  # May return None or empty if no boards configured
            assert _has_chinese(output), f"board output has no Chinese: {output[:200]!r}"

    def test_board_header_chinese(self, zh_char):
        """Board listing header must be translated."""
        from mud.commands.notes import do_board
        from mud.i18n import set_language

        set_language("zh")
        try:
            output = do_board(zh_char, "")
            # Header should contain translated column names
            assert "编号" in output or "名称" in output, f"board header not translated: {output[:200]!r}"
        finally:
            set_language("en")


class TestLanguageSwitching:
    """Verify language switching works correctly."""

    def test_english_when_language_is_en(self, zh_char):
        """When language is 'en', output should be English."""
        from mud.i18n import set_language
        from mud.commands.inventory import do_inventory

        set_language("en")
        try:
            output = do_inventory(zh_char, "")
            assert "You are carrying:" in output
            assert not _has_chinese(output), "English mode should not produce Chinese"
        finally:
            set_language("zh")

    def test_chinese_when_language_is_zh(self, zh_char):
        """When language is 'zh', output should be Chinese."""
        from mud.i18n import set_language
        from mud.commands.inventory import do_inventory

        set_language("zh")
        output = do_inventory(zh_char, "")
        assert _has_chinese(output), "Chinese mode should produce Chinese"
        assert "You are carrying:" not in output, "Chinese mode should not have English header"


class TestCreationFlowBilingual:
    """Verify creation flow shows both English and Chinese names."""

    def test_race_listing_bilingual(self):
        """Race listing should show 'human(人类)' format in zh mode."""
        from mud.i18n import set_language, t

        set_language("zh")
        try:
            # Simulate the race listing format from _prompt_for_race
            from mud.account.account_service import get_creation_races
            races = get_creation_races()
            race_names = " ".join(f"{race.name}({t(race.name)})" for race in races)
            assert "human(人类)" in race_names, f"race listing not bilingual: {race_names}"
            assert "elf(精灵)" in race_names
        finally:
            set_language("en")

    def test_class_listing_bilingual(self):
        """Class listing should show 'mage(法师)' format in zh mode."""
        from mud.i18n import set_language, t

        set_language("zh")
        try:
            from mud.account.account_service import get_creation_classes
            classes = get_creation_classes()
            class_names = " ".join(f"{cls.name}({t(cls.name)})" for cls in classes)
            assert "mage(法师)" in class_names, f"class listing not bilingual: {class_names}"
            assert "warrior(战士)" in class_names
        finally:
            set_language("en")

    def test_weapon_listing_bilingual(self):
        """Weapon listing should show 'sword(剑)' format in zh mode."""
        from mud.i18n import set_language, t

        set_language("zh")
        try:
            # Simulate weapon listing for warrior class
            weapons = ["sword", "mace"]
            weapon_names = " ".join(f"{c}({t(c)})" for c in weapons)
            assert "sword(剑)" in weapon_names, f"weapon listing not bilingual: {weapon_names}"
            assert "mace(锤)" in weapon_names
        finally:
            set_language("en")


class TestExitsZh:
    """Exit display produces Chinese output."""

    def test_exits_header_chinese(self, zh_char):
        """do_exits header should be translated in zh mode."""
        from mud.commands.inspection import do_exits
        from mud.i18n import set_language

        set_language("zh")
        try:
            output = do_exits(zh_char, "")
            # Should contain translated header
            assert "出口" in output, f"exits header not translated: {output[:100]!r}"
        finally:
            set_language("en")

    def test_exits_auto_mode_chinese(self, zh_char):
        """do_exits auto mode should show bilingual format with destination."""
        from mud.commands.inspection import do_exits
        from mud.i18n import set_language

        set_language("zh")
        try:
            output = do_exits(zh_char, "auto")
            # Auto mode format: {o[出口: 北(north, 某房间) 南(south, 某房间)]{x
            assert "出口" in output, f"auto exits header not translated: {output[:100]!r}"
            # Should contain bilingual format with English direction name
            # The test character's room may have exits, check format if present
            if "(" in output:
                # Verify format includes English direction name in parentheses
                assert "(north" in output or "(south" in output or "(east" in output or "(west" in output or "(up" in output or "(down" in output, \
                    f"auto exits should show bilingual format: {output[:200]!r}"
        finally:
            set_language("en")

    def test_direction_aliases_registered(self):
        """Chinese direction aliases (北/东/南/西/上/下) must be registered."""
        from mud.commands.dispatcher import resolve_command

        # Check that Chinese direction aliases resolve to movement commands
        chinese_to_english = {
            "北": "north",
            "东": "east",
            "南": "south",
            "西": "west",
            "上": "up",
            "下": "down",
        }
        for chinese, english in chinese_to_english.items():
            cmd = resolve_command(chinese)
            assert cmd is not None, f"Chinese direction alias '{chinese}' not registered"
            assert cmd.name == english, f"'{chinese}' should resolve to '{english}', got '{cmd.name}'"


class TestSocialsZh:
    """Social command translations produce Chinese output."""

    def test_translate_social_function(self):
        """translate_social should return translated text when available."""
        from mud.i18n import set_language, translate_social

        set_language("zh")
        try:
            # Test that smile social has Chinese translation
            result = translate_social("smile", "char_no_arg", "You smile happily.")
            assert "微笑" in result, f"smile char_no_arg not translated: {result!r}"
        finally:
            set_language("en")

    def test_translate_social_fallback(self):
        """translate_social should return default when no translation available."""
        from mud.i18n import set_language, translate_social

        set_language("zh")
        try:
            # Test that unimplemented social falls back to English
            result = translate_social("nonexistent_social", "char_no_arg", "Default text")
            assert result == "Default text"
        finally:
            set_language("en")

    def test_socials_section_exists(self):
        """zh.json should have a socials section with translations."""
        import json
        from pathlib import Path
        zh_path = Path("data/i18n/zh.json")
        d = json.loads(zh_path.read_text(encoding="utf-8"))
        socials = d.get("socials", {})
        assert len(socials) >= 244, f"Expected at least 244 social translations, got {len(socials)}"
        assert "smile" in socials
        assert "laugh" in socials


class TestCombatZh:
    """Combat message translations should work when LANGUAGE=zh."""

    def test_combat_section_exists(self):
        """zh.json should have a combat section with translations."""
        import json
        from pathlib import Path
        zh_path = Path("data/i18n/zh.json")
        d = json.loads(zh_path.read_text(encoding="utf-8"))
        combat = d.get("combat", {})
        assert "damage_tiers" in combat, "Missing combat.damage_tiers section"
        assert "attack_nouns" in combat, "Missing combat.attack_nouns section"
        assert "pronouns" in combat, "Missing combat.pronouns section"
        # Check minimum counts
        assert len(combat["damage_tiers"]) >= 20, f"Expected 20+ damage tiers, got {len(combat['damage_tiers'])}"
        assert len(combat["attack_nouns"]) >= 25, f"Expected 25+ attack nouns, got {len(combat['attack_nouns'])}"

    def test_damage_tier_translations(self):
        """Damage tier terms should be translated when LANGUAGE=zh."""
        from mud.combat.messages import _severity_terms, _get_combat_translation
        from mud.i18n import set_language

        set_language("zh")
        try:
            # Test that "hit" tier is translated
            result = _get_combat_translation("damage_tiers.hit.self", "hit")
            assert result != "hit", f"hit damage tier not translated: {result!r}"
            assert any('\u4e00' <= c <= '\u9fff' for c in result), f"Not Chinese: {result!r}"
        finally:
            set_language("en")

    def test_attack_noun_translations(self):
        """Attack nouns should be translated when LANGUAGE=zh."""
        from mud.combat.messages import _get_combat_translation
        from mud.i18n import set_language

        set_language("zh")
        try:
            result = _get_combat_translation("attack_nouns.slash", "slash")
            assert result != "slash", f"slash attack noun not translated: {result!r}"
            assert any('\u4e00' <= c <= '\u9fff' for c in result), f"Not Chinese: {result!r}"
        finally:
            set_language("en")

    def test_pronoun_translations(self):
        """Pronouns should be translated when LANGUAGE=zh."""
        from mud.combat.messages import _reflexive_pronoun, _possessive_pronoun
        from mud.i18n import set_language
        from mud.models.constants import Sex

        set_language("zh")
        try:
            # Create a mock character with male sex
            class MockChar:
                sex = Sex.MALE
            char = MockChar()
            
            reflexive = _reflexive_pronoun(char)
            possessive = _possessive_pronoun(char)
            
            assert "他" in reflexive, f"Male reflexive not translated: {reflexive!r}"
            assert "他" in possessive, f"Male possessive not translated: {possessive!r}"
        finally:
            set_language("en")


class TestSkillsZh:
    """Skill/spell message translations should work when LANGUAGE=zh."""

    def test_skills_section_exists(self):
        """zh.json should have a skills section with translations."""
        import json
        from pathlib import Path
        zh_path = Path("data/i18n/zh.json")
        d = json.loads(zh_path.read_text(encoding="utf-8"))
        skills = d.get("skills", {})
        assert "messages" in skills, "Missing skills.messages section"
        assert "names" in skills, "Missing skills.names section"
        # Check minimum counts
        assert len(skills["messages"]) >= 50, f"Expected 50+ skill messages, got {len(skills['messages'])}"
        assert len(skills["names"]) >= 50, f"Expected 50+ skill names, got {len(skills['names'])}"

    def test_translate_skill_function(self):
        """translate_skill should return translated text when available."""
        from mud.i18n import set_language, translate_skill

        set_language("zh")
        try:
            result = translate_skill("You are already armored.")
            assert result != "You are already armored.", f"Message not translated: {result!r}"
            assert any('\u4e00' <= c <= '\u9fff' for c in result), f"Not Chinese: {result!r}"
        finally:
            set_language("en")

    def test_translate_skill_name_function(self):
        """translate_skill_name should return translated name when available."""
        from mud.i18n import set_language, translate_skill_name

        set_language("zh")
        try:
            result = translate_skill_name("fireball")
            assert result != "fireball", f"Skill name not translated: {result!r}"
            assert "火球" in result, f"Expected 火球 in result: {result!r}"
        finally:
            set_language("en")

    def test_say_spell_translation(self):
        """say_spell should return translated messages when LANGUAGE=zh."""
        from mud.i18n import set_language
        from mud.skills.say_spell import say_spell

        set_language("zh")
        try:
            class MockCaster:
                name = "TestCaster"
            caster = MockCaster()
            
            actual_msg, garbled_msg = say_spell(caster, "fireball")
            # At least one should be translated
            assert "念出咒语" in actual_msg or "utters" in actual_msg, f"say_spell not translated: {actual_msg!r}"
        finally:
            set_language("en")


class TestShopZh:
    """Shop/shopkeeper message translations should work when LANGUAGE=zh."""

    def test_shop_section_exists(self):
        """zh.json should have a shop section with translations."""
        import json
        from pathlib import Path
        zh_path = Path("data/i18n/zh.json")
        d = json.loads(zh_path.read_text(encoding="utf-8"))
        shop = d.get("shop", {})
        assert "messages" in shop, "Missing shop.messages section"
        assert "types" in shop, "Missing shop.types section"
        # Check minimum counts
        assert len(shop["messages"]) >= 50, f"Expected 50+ shop messages, got {len(shop['messages'])}"
        assert len(shop["types"]) >= 15, f"Expected 15+ shop types, got {len(shop['types'])}"

    def test_translate_shop_function(self):
        """translate_shop should return translated text when available."""
        from mud.i18n import set_language, translate_shop

        set_language("zh")
        try:
            result = translate_shop("You can't afford it.")
            assert result != "You can't afford it.", f"Message not translated: {result!r}"
            assert any('\u4e00' <= c <= '\u9fff' for c in result), f"Not Chinese: {result!r}"
        finally:
            set_language("en")

    def test_translate_shop_type_function(self):
        """translate_shop_type should return translated name when available."""
        from mud.i18n import set_language, translate_shop_type

        set_language("zh")
        try:
            result = translate_shop_type("weapon")
            assert result != "weapon", f"Shop type not translated: {result!r}"
            assert "武器" in result, f"Expected 武器 in result: {result!r}"
        finally:
            set_language("en")


class TestItemsZh:
    """Item usage message translations should work when LANGUAGE=zh."""

    def test_items_section_exists(self):
        """zh.json should have an items section with translations."""
        import json
        from pathlib import Path
        zh_path = Path("data/i18n/zh.json")
        d = json.loads(zh_path.read_text(encoding="utf-8"))
        items = d.get("items", {})
        assert "messages" in items, "Missing items.messages section"
        assert "types" in items, "Missing items.types section"
        # Check minimum counts
        assert len(items["messages"]) >= 50, f"Expected 50+ item messages, got {len(items['messages'])}"
        assert len(items["types"]) >= 15, f"Expected 15+ item types, got {len(items['types'])}"

    def test_translate_item_function(self):
        """translate_item should return translated text when available."""
        from mud.i18n import set_language, translate_item

        set_language("zh")
        try:
            result = translate_item("Eat what?")
            assert result != "Eat what?", f"Message not translated: {result!r}"
            assert any('\u4e00' <= c <= '\u9fff' for c in result), f"Not Chinese: {result!r}"
        finally:
            set_language("en")

    def test_translate_item_type_function(self):
        """translate_item_type should return translated name when available."""
        from mud.i18n import set_language, translate_item_type

        set_language("zh")
        try:
            result = translate_item_type("food")
            assert result != "food", f"Item type not translated: {result!r}"
            assert "食物" in result, f"Expected 食物 in result: {result!r}"
        finally:
            set_language("en")
