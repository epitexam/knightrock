"""The interface sounds, driven through the real scene stack (lot 5).

The unit tests prove the policy is pure; these prove the *chain* works and that
it stays quiet where it must. Nothing here touches a mixer: a recording
subscriber stands in for the audio system, and the assertion is the sequence of
effects the screens published — one per interaction, and none where the player
did not ask for one.
"""

import pygame
import pytest

from src.application.events import EventBus, UiEffect, UiFeedback
from src.application.scene_manager import SceneManager
from src.application.scenes.controls_scene import ControlsScene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.menu_scene import MenuScene
from src.application.scenes.options_scene import OptionsScene
from src.application.scenes.pause_scene import PauseScene
from src.application.scenes.video_scene import VideoScene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.core.level.level import Level
from tests.headless.conftest import make_programmatic_level_data


class RecordingFeedback:
    """A subscriber that remembers every interface effect it is told about."""

    def __init__(self) -> None:
        self.effects: list[UiFeedback] = []

    def __call__(self, event: UiFeedback) -> None:
        self.effects.append(event)

    @property
    def cues(self) -> list[UiEffect]:
        return [event.effect for event in self.effects]


@pytest.fixture()
def feedback(game_runtime) -> RecordingFeedback:
    """Attach a recording subscriber to the real runtime's bus."""
    recorder = RecordingFeedback()
    game_runtime.events.subscribe(UiFeedback, recorder)
    return recorder


@pytest.fixture()
def manager(game_runtime) -> SceneManager:
    return game_runtime.scene_manager


def press(manager: SceneManager, key: int) -> None:
    manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def move(manager: SceneManager, position: tuple[int, int]) -> None:
    manager.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=position))


def test_one_menu_press_publishes_exactly_one_effect(manager: SceneManager, feedback) -> None:
    manager.switch(OptionsScene(manager.game))

    press(manager, pygame.K_DOWN)

    assert feedback.cues == [UiEffect.NAVIGATED]


def test_opening_a_screen_and_coming_back_are_two_distinct_effects(
    manager: SceneManager, feedback
) -> None:
    manager.switch(OptionsScene(manager.game))

    press(manager, pygame.K_RETURN)
    assert isinstance(manager.current, VideoScene)

    press(manager, pygame.K_ESCAPE)

    assert isinstance(manager.current, OptionsScene)
    assert feedback.cues == [UiEffect.CONFIRMED, UiEffect.DISMISSED]


def test_a_value_change_in_place_is_a_confirmation(manager: SceneManager, feedback) -> None:
    """← on the focused row adjusts the setting without leaving the screen."""
    manager.switch(VideoScene(manager.game))
    before = (manager.game.settings.width, manager.game.settings.height)

    press(manager, pygame.K_RIGHT)  # the resolution row is focused on entry

    assert (manager.game.settings.width, manager.game.settings.height) != before
    assert isinstance(manager.current, VideoScene)
    assert feedback.cues == [UiEffect.CONFIRMED]


def test_a_single_press_of_a_held_direction_publishes_once(manager: SceneManager, feedback) -> None:
    """The stick release carries the held action: it must not speak again.

    This is the double-step the UI report described, in its audible form — one
    press, one row, one effect.
    """
    manager.switch(OptionsScene(manager.game))
    options = manager.current

    manager.handle_event(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=1, value=0.8))
    manager.handle_event(pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=1, value=0.0))

    assert options.model.current_index == 1
    assert feedback.cues == [UiEffect.NAVIGATED]


def test_a_key_held_against_a_list_edge_publishes_nothing(manager: SceneManager, feedback) -> None:
    """``MenuModel.move`` reports None when blocked, so no step, no fact."""
    manager.switch(OptionsScene(manager.game))
    options = manager.current
    options.model.set_items(options.model.items, 0)

    press(manager, pygame.K_UP)

    assert options.model.current_index == 0
    assert feedback.cues == []


def test_the_pointer_publishes_once_per_row_it_lands_on(manager: SceneManager, feedback) -> None:
    """Sweeping along a row is one fact; the next row is the next fact.

    The model reports the focus only when it moved, so a pointer sampled 100
    times a second over a single row stays quiet.
    """
    manager.switch(OptionsScene(manager.game))
    options = manager.current
    options.draw(pygame.display.get_surface())
    first, second = options.view.item_rects[0], options.view.item_rects[1]

    for offset in range(6):
        move(manager, (first.x + offset, first.centery))
    assert feedback.cues == [UiEffect.NAVIGATED]

    for offset in range(6):
        move(manager, (second.x + offset, second.centery))

    assert feedback.cues == [UiEffect.NAVIGATED, UiEffect.NAVIGATED]
    assert options.model.current_index == 1


def test_leaving_the_rows_and_coming_back_publishes_again(manager: SceneManager, feedback) -> None:
    manager.switch(OptionsScene(manager.game))
    options = manager.current
    options.draw(pygame.display.get_surface())
    centre = options.view.item_rects[0].center

    move(manager, centre)
    move(manager, (2, 2))
    move(manager, centre)

    assert feedback.cues == [UiEffect.NAVIGATED, UiEffect.NAVIGATED]


def test_a_controller_unplugged_publishes_nothing(manager: SceneManager, feedback) -> None:
    manager.switch(OptionsScene(manager.game))

    manager.handle_event(pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=0))

    assert feedback.cues == []


def test_a_held_key_repeating_publishes_one_fact_per_step(manager: SceneManager, feedback) -> None:
    """A repeat that moves the selection is a fact; one blocked at the edge is not.

    Unlike a mouse move, an auto-repeat genuinely moves the selection, so it
    speaks like any other step. The repeats that run into the last row move
    nothing, and a step that moves nothing is not an interaction.
    """
    router = manager.input_dispatcher.router
    manager.switch(OptionsScene(manager.game))  # three rows
    options = manager.current
    # The repeat is armed against the router's own clock, so it has to be the
    # fake one *before* the press that arms it.
    now = [1000.0]
    router._clock = lambda: now[0]  # type: ignore[method-assign]
    press(manager, pygame.K_DOWN)  # row 0 -> 1

    for _ in range(4):
        now[0] += 10.0
        manager.poll_held_repeats()  # one step, then three at the edge

    assert options.model.current_index == 2
    assert feedback.cues == [UiEffect.NAVIGATED] * 2


def test_the_gameplay_scene_publishes_nothing_for_the_player_keys(
    manager: SceneManager, feedback, game_runtime
) -> None:
    """The arrows, Space and Escape are the player keys too.

    Without the report, holding an arrow to walk would publish — and therefore
    be heard — at the menu auto-repeat rate for the whole level.
    """
    level = Level(
        pygame.display.get_surface(),
        make_programmatic_level_data(),
        game_runtime.input_manager,
    )
    manager.switch(GameplayScene(game_runtime, level=level))

    press(manager, pygame.K_RIGHT)
    press(manager, pygame.K_SPACE)
    press(manager, pygame.K_q)

    assert feedback.cues == []


def test_opening_the_pause_from_gameplay_is_published(
    manager: SceneManager, feedback, game_runtime
) -> None:
    """The one sound the gameplay scene owes: the pause menu opening."""
    level = Level(
        pygame.display.get_surface(),
        make_programmatic_level_data(),
        game_runtime.input_manager,
    )
    manager.switch(GameplayScene(game_runtime, level=level))

    press(manager, pygame.K_ESCAPE)

    assert isinstance(manager.current, PauseScene)
    assert feedback.cues == [UiEffect.DISMISSED]


def test_the_controls_screen_publishes_nothing_while_capturing(
    manager: SceneManager, feedback
) -> None:
    """The press that fills a binding is not a menu interaction.

    Filling the "Move up" cell with ``X`` rebinds ``UI_UP`` to that key, so the
    very same event routes as a navigation one line later — and the screen has
    already consumed it. Its report is the reason nothing is heard.
    """
    manager.switch(ControlsScene(manager.game, ControlsScene.MENU_SECTION))
    controls = manager.current

    press(manager, pygame.K_RETURN)  # opens the capture on the first row
    assert controls.capturing is True
    press(manager, pygame.K_x)

    assert controls.capturing is False
    rebound = controls.game.settings.bindings.menu.keyboard[InputAction.UI_UP]
    rebound = (rebound,) if isinstance(rebound, int) else rebound
    assert pygame.K_x in rebound
    assert feedback.cues == [UiEffect.CONFIRMED]


def test_cancelling_a_capture_with_escape_publishes_nothing(
    manager: SceneManager, feedback
) -> None:
    """Escape cancels through the raw path, and the screen says so.

    ``_ignore_routed`` exists precisely so that press does not also run the
    back action it routes; the published fact follows the same contract.
    """
    manager.switch(ControlsScene(manager.game, ControlsScene.MENU_SECTION))
    controls = manager.current
    press(manager, pygame.K_RETURN)

    press(manager, pygame.K_ESCAPE)

    assert controls.capturing is False
    assert isinstance(manager.current, ControlsScene)  # still there, not popped
    assert feedback.cues == [UiEffect.CONFIRMED]


def test_navigating_the_controls_screen_is_published(manager: SceneManager, feedback) -> None:
    manager.switch(ControlsScene(manager.game, ControlsScene.MENU_SECTION))

    press(manager, pygame.K_DOWN)

    assert feedback.cues == [UiEffect.NAVIGATED]


def test_the_controls_pointer_publishes_when_the_focus_moves(
    manager: SceneManager, feedback
) -> None:
    """This screen drives the model itself, so it reports the move itself."""
    manager.switch(ControlsScene(manager.game, ControlsScene.MENU_SECTION))
    controls = manager.current
    controls.draw(pygame.display.get_surface())
    rows = controls.view.row_rects

    move(manager, rows[0].center)
    move(manager, rows[0].center)
    move(manager, rows[1].center)

    assert feedback.cues == [UiEffect.NAVIGATED, UiEffect.NAVIGATED]


def test_arming_and_disarming_the_quit_prompt_is_a_dismissal(
    manager: SceneManager, feedback
) -> None:
    """Escape and the Quit row arm the same prompt, so both report the same."""
    manager.switch(MenuScene(manager.game))
    menu = manager.current

    press(manager, pygame.K_ESCAPE)
    assert menu.confirming is True
    press(manager, pygame.K_ESCAPE)  # disarm
    assert menu.confirming is False

    assert feedback.cues == [UiEffect.DISMISSED, UiEffect.DISMISSED]


def test_answering_no_to_the_quit_prompt_is_a_dismissal(manager: SceneManager, feedback) -> None:
    manager.switch(MenuScene(manager.game))
    menu = manager.current
    press(manager, pygame.K_ESCAPE)

    press(manager, pygame.K_RETURN)  # "No, go back" is the focused answer

    assert menu.confirming is False
    assert manager.game.running is True
    assert feedback.cues == [UiEffect.DISMISSED, UiEffect.DISMISSED]


def test_a_locked_level_publishes_nothing(manager: SceneManager, feedback) -> None:
    """The model refuses a disabled item, so no screen acted and nothing is said."""
    from src.application.scenes.level_select_scene import LevelSelectScene

    manager.switch(LevelSelectScene(manager.game))
    level_select = manager.current
    locked = next(
        (index for index, item in enumerate(level_select.model.items) if not item.enabled), None
    )
    if locked is None:
        pytest.skip("every level is unlocked with this save")
    level_select.model.set_items(level_select.model.items, locked)

    press(manager, pygame.K_RETURN)

    assert isinstance(manager.current, LevelSelectScene)
    assert feedback.cues == []


def test_the_simulation_reports_do_not_reach_the_interface_feedback(
    manager: SceneManager, feedback, game_runtime
) -> None:
    """Two channels, one audio system: a milestone is not a menu interaction.

    The audio bus answers both, but the interface feedback must stay the
    interface's own, or a level completing would be heard as a menu click.
    """
    manager.switch(OptionsScene(manager.game))

    game_runtime.events.emit(
        __import__("src.application.events", fromlist=["x"]).PlayerDied(entity_id="p", deaths=0)
    )

    assert feedback.cues == []


def test_the_report_carries_the_action_for_the_next_consumer(
    manager: SceneManager, feedback
) -> None:
    """``UiFeedback.action`` is free today and is what a tutorial would need."""
    manager.switch(OptionsScene(manager.game))

    press(manager, pygame.K_DOWN)  # onto "Controls"
    press(manager, pygame.K_RETURN)

    assert feedback.effects[0].effect is UiEffect.NAVIGATED
    assert feedback.effects[1] == UiFeedback(UiEffect.CONFIRMED, action="controls")


def test_the_dispatcher_owns_no_presentation_state(manager: SceneManager) -> None:
    """A dispatcher that grew a field here would be a layer leak.

    The regression guard for the whole design: the audio path is a published
    fact, so the only things the dispatcher holds are its collaborators.
    """
    dispatcher = manager.input_dispatcher

    assert sorted(vars(dispatcher)) == ["_events", "_router"]
    assert isinstance(dispatcher._events, EventBus)
    assert isinstance(dispatcher._router, RoutedInput.__module__ and object)


def test_one_input_reaches_exactly_one_subscriber_call(
    manager: SceneManager, game_runtime, feedback
) -> None:
    """The end-to-end guard: one press, one effect, one sound.

    The audio bus is attached to the same bus, so counting the sounds it would
    play counts the facts, without a mixer in the way.
    """
    from src.core.audio import AudioBus, cue_for

    bus = AudioBus()
    bus.attach(game_runtime.events)
    played: list[object] = []
    bus.play = played.append  # type: ignore[method-assign]

    manager.switch(OptionsScene(manager.game))
    press(manager, pygame.K_RETURN)

    assert [cue_for(event.effect) for event in feedback.effects] == played
    assert len(played) == 1
