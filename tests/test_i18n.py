"""Tests for the i18n translation layer.

Verifies that:
- Translation files load correctly
- Template translation works (preserving $n/$p tokens)
- Fixed message translation works (exact-match)
- Pronoun translation works
- English fallback works (no translation when language is "en")
- Integration with act_format() and push_message() works
"""

from __future__ import annotations

import pytest

from mud.i18n import (
    get_language,
    get_pronouns,
    is_translated,
    set_language,
    t,
    translate_help,
    translate_object,
    translate_room,
    translate_template,
)


@pytest.fixture(autouse=True)
def _reset_language():
    """Reset language to English after each test."""
    yield
    set_language("en")


# ---------------------------------------------------------------------------
# Core translation API
# ---------------------------------------------------------------------------


class TestLanguageSwitch:
    def test_default_language_is_english(self):
        set_language("en")
        assert get_language() == "en"
        assert not is_translated()

    def test_switch_to_chinese(self):
        set_language("zh")
        assert get_language() == "zh"
        assert is_translated()

    def test_switch_back_to_english(self):
        set_language("zh")
        assert is_translated()
        set_language("en")
        assert not is_translated()

    def test_unknown_language_falls_through(self):
        set_language("xx_nonexistent")
        assert is_translated()  # language is set
        assert t("Huh?") == "Huh?"  # but no translations loaded


class TestFixedMessageTranslation:
    def test_translate_known_message(self):
        set_language("zh")
        assert t("Huh?") == "啊？"

    def test_translate_unknown_message_returns_original(self):
        set_language("zh")
        assert t("This is not translated") == "This is not translated"

    def test_english_mode_returns_original(self):
        set_language("en")
        assert t("Huh?") == "Huh?"

    def test_translate_position_messages(self):
        set_language("zh")
        assert t("Lie still; you are DEAD.") == "躺好；你已经死了。"
        assert t("You are too stunned to do that.") == "你被击晕了，做不了那个。"
        assert t("In your dreams, or what?") == "做梦去吧。"

    def test_translate_combat_messages(self):
        set_language("zh")
        assert t("Kill whom?") == "杀谁？"
        assert t("You aren't fighting anyone.") == "你没有在和任何人战斗。"
        assert t("You flee from combat!") == "你从战斗中逃跑了！"


class TestTemplateTranslation:
    def test_translate_template_with_tokens(self):
        set_language("zh")
        result = translate_template("$n hits $N.")
        assert result == "$n 击中了 $N。"

    def test_translate_unknown_template_returns_original(self):
        set_language("zh")
        result = translate_template("$n does something unknown.")
        assert result == "$n does something unknown."

    def test_english_mode_returns_original_template(self):
        set_language("en")
        result = translate_template("$n hits $N.")
        assert result == "$n hits $N."

    def test_translate_wear_templates(self):
        set_language("zh")
        assert translate_template("You wear $p on your head.") == "你把 $p 戴在头上。"
        assert translate_template("You wield $p.") == "你挥舞着 $p。"

    def test_translate_social_templates(self):
        set_language("zh")
        assert translate_template("$n slaps $N.") == "$n 扇了 $N 一巴掌。"
        assert translate_template("$n slaps you.") == "$n 扇了你一巴掌。"


class TestPronounTranslation:
    def test_english_pronouns_returns_none(self):
        set_language("en")
        assert get_pronouns() is None

    def test_chinese_pronouns_loaded(self):
        set_language("zh")
        pronouns = get_pronouns()
        assert pronouns is not None
        assert pronouns["subject"]["male"] == "他"
        assert pronouns["subject"]["female"] == "她"
        assert pronouns["subject"]["none"] == "它"
        assert pronouns["possessive"]["male"] == "他的"


# ---------------------------------------------------------------------------
# Integration with act_format()
# ---------------------------------------------------------------------------


class TestActFormatIntegration:
    def test_act_format_translates_template(self):
        """act_format() should translate templates before token expansion."""
        set_language("zh")
        from mud.utils.act import act_format

        # Create mock actor and target with names
        # Mock needs enough attributes for can_see_character() to pass.
        class MockChar:
            name = "tester"
            is_npc = False
            affected_by = 0

        class MockTarget:
            name = "goblin"
            is_npc = True
            short_descr = "a goblin"
            affected_by = 0

        actor = MockChar()
        target = MockTarget()

        result = act_format(
            "$n hits $N.",
            recipient=actor,
            actor=actor,
            arg2=target,
        )
        # Template is translated to "$n 击中了 $N。"
        # Then $n → actor name, $N → target name (or "someone" if can_see fails)
        assert "击中" in result

    def test_act_format_pronouns_translated(self):
        """act_format() should use translated pronouns."""
        set_language("zh")
        from mud.models.constants import Sex
        from mud.utils.act import act_format

        class MockMob:
            name = "guard"
            is_npc = True
            short_descr = "the guard"
            sex = Sex.MALE

        mob = MockMob()
        result = act_format(
            "$n swings $s weapon.",
            recipient=mob,
            actor=mob,
        )
        # $s should be translated to "他的" (male possessive)
        assert "他的" in result


# ---------------------------------------------------------------------------
# Integration with push_message()
# ---------------------------------------------------------------------------


class TestPushMessageIntegration:
    def test_push_message_translates_mailbox(self):
        """push_message() should translate for the mailbox fallback."""
        set_language("zh")
        from typing import Any
        from mud.utils.messaging import push_message

        char: Any = type("MockChar", (), {"connection": None, "messages": []})()
        push_message(char, "Huh?")
        assert char.messages[-1] == "啊？"

    def test_push_message_english_no_translation(self):
        """push_message() should not translate when language is English."""
        set_language("en")
        from typing import Any
        from mud.utils.messaging import push_message

        char: Any = type("MockChar", (), {"connection": None, "messages": []})()
        push_message(char, "Huh?")
        assert char.messages[-1] == "Huh?"

    def test_push_message_untranslated_falls_through(self):
        """push_message() should pass through untranslated messages."""
        set_language("zh")
        from typing import Any
        from mud.utils.messaging import push_message

        char: Any = type("MockChar", (), {"connection": None, "messages": []})()
        push_message(char, "This message is not in the translation file.")
        assert char.messages[-1] == "This message is not in the translation file."


# ---------------------------------------------------------------------------
# Direction translation
# ---------------------------------------------------------------------------


class TestDirectionTranslation:
    def test_translate_direction(self):
        set_language("zh")
        from mud.i18n import get_direction

        assert get_direction("north") == "北"
        assert get_direction("south") == "南"
        assert get_direction("east") == "东"
        assert get_direction("west") == "西"

    def test_translate_exit_name(self):
        set_language("zh")
        from mud.i18n import get_exit_name

        assert get_exit_name("north") == "北"
        assert get_exit_name("up") == "上"

    def test_unknown_direction_falls_through(self):
        set_language("zh")
        from mud.i18n import get_direction

        assert get_direction("sideways") == "sideways"


# ---------------------------------------------------------------------------
# Pattern-based (dynamic string) translation
# ---------------------------------------------------------------------------


class TestPatternTranslation:
    def test_level_requirement_pattern(self):
        set_language("zh")
        result = t("You must be level 15 to use this object.")
        assert result == "你必须达到 15 级才能使用这个物品。"

    def test_save_failed_pattern(self):
        set_language("zh")
        result = t("Save failed: disk full")
        assert result == "存档失败：disk full"

    def test_armor_description_patterns(self):
        set_language("zh")
        assert t("hopelessly vulnerable to fire.") == "对 fire 毫无防御。"
        assert t("well-armored against cold.") == "对 cold 防护良好。"
        assert t("divinely armored against acid.") == "对 acid 神圣护体。"

    def test_inventory_dynamic_patterns(self):
        set_language("zh")
        assert t("I see no sword here.") == "我在这里没看到 sword。"
        assert t("I see nothing in the bag.") == "我在 bag 里什么也没看到。"
        assert t("The chest is closed.") == "chest 关着。"
        assert t("You drop the sword.") == "你放下了 the sword。"

    def test_door_dynamic_patterns(self):
        set_language("zh")
        assert t("You open the gate.") == "你打开了 the gate。"
        assert t("You close the door.") == "你关上了 the door。"
        assert t("You lock the chest.") == "你锁上了 the chest。"
        assert t("You pick the lock on the box.") == "你撬开了 the box 的锁。"

    def test_combat_dynamic_patterns(self):
        set_language("zh")
        assert t("You disarm the guard!") == "你缴了 the guard 的械！"
        assert t("You fail to disarm the guard.") == "你没能缴了 the guard 的械。"

    def test_equipment_dynamic_patterns(self):
        set_language("zh")
        assert t("You wield a longsword.") == "你挥舞着 a longsword。"
        assert t("a longsword feels like a part of you!") == "a longsword 感觉像你身体的一部分！"
        assert t("You fumble and almost drop the ring.") == "你手一滑，差点掉了 the ring。"

    def test_pattern_falls_through_when_no_match(self):
        set_language("zh")
        result = t("This string has no matching pattern.")
        assert result == "This string has no matching pattern."

    def test_exact_match_takes_priority_over_pattern(self):
        """Exact match in messages should win over a pattern match."""
        set_language("zh")
        # "Huh?" is in messages section as exact match
        assert t("Huh?") == "啊？"

    def test_english_mode_skips_patterns(self):
        set_language("en")
        result = t("You must be level 15 to use this object.")
        assert result == "You must be level 15 to use this object."


class TestHelpTranslation:
    """Tests for help text translation."""

    def test_translate_help_known_topic(self):
        set_language("zh")
        result = translate_help(["RACE", "RACES"], "ROM has the following races...")
        assert "人类" in result
        assert "矮人" in result

    def test_translate_help_unknown_topic_falls_through(self):
        set_language("zh")
        original = "Some untranslated help text."
        result = translate_help(["NONEXISTENT"], original)
        assert result == original

    def test_translate_help_english_mode(self):
        set_language("en")
        original = "ROM has the following races..."
        result = translate_help(["RACE"], original)
        assert result == original

    def test_translate_help_newbie_topics(self):
        """Verify high-frequency newbie help topics are translated."""
        set_language("zh")
        # areas/commands/score overview
        result = translate_help(["areas"], "AREAS shows you a list...")
        assert "区域" in result
        # practice/training
        result = translate_help(["practice"], "PRACTICE without an argument...")
        assert "练习" in result
        # recall
        result = translate_help(["recall"], "RECALL transports you...")
        assert "神殿" in result
        # death
        result = translate_help(["death"], "When your character dies...")
        assert "死亡" in result or "重生" in result
        # follow/group
        result = translate_help(["follow"], "FOLLOW starts you following...")
        assert "跟随" in result
        # train
        result = translate_help(["train"], "TRAIN increases one...")
        assert "属性" in result


class TestPronounConversion:
    """Tests for actor pronoun token conversion in templates."""

    def test_actor_pronouns_converted_in_translated_template(self):
        set_language("zh")
        # Template that exists in zh.json templates section
        result = translate_template("$n smiles happily.")
        assert "$n" in result  # name token preserved
        assert "微笑" in result  # translated

    def test_untranslated_template_keeps_english_pronouns(self):
        set_language("zh")
        # Template NOT in zh.json → returned unchanged
        result = translate_template("$n does something unknown.")
        assert result == "$n does something unknown."

    def test_actor_pronoun_mself_converted(self):
        """$mself in a translated template should be converted to Chinese reflexive."""
        set_language("zh")
        # "$n smiles at $mself." is in zh.json
        result = translate_template("$n smiles at $mself.")
        assert "$n" in result
        assert "自己" in result

    def test_victim_pronouns_preserved_in_template(self):
        """$E/$M/$S should NOT be converted by translate_template (needs victim gender)."""
        set_language("zh")
        # Template with victim pronouns - they should remain as tokens
        result = translate_template("You smile at $M.")
        assert "$M" in result  # victim pronoun preserved

    def test_english_mode_no_pronoun_conversion(self):
        set_language("en")
        result = translate_template("$n smiles at $mself.")
        assert result == "$n smiles at $mself."  # unchanged in English mode


class TestSkillMessageTranslation:
    """Tests for skill wear_off message translation via send_to_char path."""

    def test_wear_off_message_translated(self):
        """Skill wear_off messages should be translated via exact match."""
        set_language("zh")
        assert t("You feel less armored.") == "你感觉护甲消退了。"
        assert t("You can see again.") == "你又能看见了。"
        assert t("The detect magic wears off.") == "侦测魔法效果消退了。"

    def test_skill_object_message_translated(self):
        """Skill object messages with $p should be translated."""
        set_language("zh")
        assert t("$p fades into view.") == "$p 渐渐显现。"
        assert t("$p's holy aura fades.") == "$p 的神圣光环消散了。"


class TestAreaContentTranslation:
    """Tests for room/object translation by vnum."""

    def test_room_name_translated(self):
        """Room name should be translated by vnum."""
        set_language("zh")
        result = translate_room(3001, "name", "The Temple Of Mota")
        assert result == "莫塔神殿"

    def test_room_description_translated(self):
        """Room description should be translated by vnum."""
        set_language("zh")
        result = translate_room(3001, "description", "English description")
        assert "莫塔神殿" in result

    def test_room_unknown_vnum_returns_default(self):
        """Unknown vnum should return default (English) text."""
        set_language("zh")
        result = translate_room(99999, "name", "Unknown Room")
        assert result == "Unknown Room"

    def test_room_english_mode_returns_default(self):
        """English mode should return default text."""
        set_language("en")
        result = translate_room(3001, "name", "The Temple Of Mota")
        assert result == "The Temple Of Mota"

    def test_object_translation_infrastructure(self):
        """Object translation should work (infrastructure test)."""
        set_language("zh")
        # No objects translated yet, should return default
        result = translate_object(3000, "name", "a barrel of beer")
        assert result == "a barrel of beer"


class TestLanguageCommand:
    """Tests for the language switching command.

    do_language stores preference in pcdata.language (per-player), NOT
    in the global i18n state.  This avoids one player's command affecting
    all connected players.
    """

    def _load_do_language(self):
        """Load do_language directly to avoid dotenv dependency chain."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "player_config", "mud/commands/player_config.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.do_language

    def test_language_show_current(self):
        """'language' with no args should show current language from pcdata."""
        from mud.models.character import Character, PCData
        do_language = self._load_do_language()

        char = Character()
        char.is_npc = False
        char.pcdata = PCData()
        char.pcdata.language = "en"
        result = do_language(char, "")
        assert "English" in result

    def test_language_show_chinese(self):
        """'language' with no args should show Chinese if that's the preference."""
        from mud.models.character import Character, PCData
        do_language = self._load_do_language()

        char = Character()
        char.is_npc = False
        char.pcdata = PCData()
        char.pcdata.language = "zh"
        result = do_language(char, "")
        assert "中文" in result

    def test_language_switch_to_chinese(self):
        """'language zh' should store Chinese preference in pcdata."""
        from mud.models.character import Character, PCData
        do_language = self._load_do_language()

        char = Character()
        char.is_npc = False
        char.pcdata = PCData()
        result = do_language(char, "zh")
        assert "中文" in result
        assert char.pcdata.language == "zh"

    def test_language_switch_to_english(self):
        """'language en' should store English preference in pcdata."""
        from mud.models.character import Character, PCData
        do_language = self._load_do_language()

        char = Character()
        char.is_npc = False
        char.pcdata = PCData()
        char.pcdata.language = "zh"
        result = do_language(char, "en")
        assert "English" in result
        assert char.pcdata.language == "en"

    def test_language_does_not_affect_global_state(self):
        """'language zh' must NOT change the global i18n language."""
        from mud.models.character import Character, PCData
        do_language = self._load_do_language()

        set_language("en")
        char = Character()
        char.is_npc = False
        char.pcdata = PCData()
        do_language(char, "zh")
        # Global state should remain unchanged
        assert get_language() == "en"

    def test_language_invalid_argument(self):
        """'language foo' should show usage."""
        from mud.models.character import Character
        do_language = self._load_do_language()

        char = Character()
        char.is_npc = False
        result = do_language(char, "foo")
        assert "Usage" in result
