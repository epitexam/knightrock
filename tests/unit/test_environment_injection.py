"""Environment-reading helpers accept an explicit mapping.

Existing callers keep reading ``os.environ``, but tests and the future
application config can pass a mapping directly instead of monkeypatching
process-global state.
"""

from pathlib import Path

from src.application.attack_authoring import export_attack
from src.application.save_game import default_save_path
from src.application.settings_store import default_settings_path
from src.core.level.systems.combat_trace import CombatTrace
from src.core.settings import Debug
from src.data.roots import gameplay_data_root
from tests.unit.helpers import make_attack, make_phase


def test_debug_flag_accepts_an_explicit_environment() -> None:
    assert Debug.is_enabled({"DEBUG": "1"}) is True
    assert Debug.is_enabled({"DEBUG": "0"}) is False
    assert Debug.is_enabled({}) is False


def test_combat_trace_combines_both_flags_from_one_mapping() -> None:
    assert CombatTrace.is_enabled({"DEBUG": "1", "DEBUG_COMBAT_DUMP": "1"}) is True
    assert CombatTrace.is_enabled({"DEBUG": "1", "DEBUG_COMBAT_DUMP": "0"}) is False
    assert CombatTrace.is_enabled({"DEBUG": "0", "DEBUG_COMBAT_DUMP": "1"}) is False


def test_data_root_accepts_an_explicit_environment() -> None:
    assert gameplay_data_root({"KNIGHTROCK_DATA_DIR": "/mods"}) == Path("/mods/gameplay")
    assert gameplay_data_root({}).is_absolute()


def test_user_paths_accept_an_explicit_environment(tmp_path: Path) -> None:
    environ = {"KNIGHTROCK_SAVE_DIR": str(tmp_path)}

    assert default_save_path(environ) == tmp_path / ".knightrock" / "savegame.json"
    assert default_settings_path(environ) == tmp_path / ".knightrock" / "settings.json"


def test_export_destination_accepts_an_explicit_environment(tmp_path: Path) -> None:
    environ = {"KNIGHTROCK_EXPORT_DIR": str(tmp_path)}
    definition = make_attack(make_phase())

    destination = export_attack({"player": {"kick": definition}}, "kick", environ=environ)

    assert destination == tmp_path / "kick.json"
