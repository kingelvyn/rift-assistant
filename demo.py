# demo.py
#
# Demo: build GameState objects using real cards from cards.db
# and run them through the advisor.

from pprint import pprint

from game_state import (
    GameState,
    PlayerState,
    Lane,
    Phase,
    Rune,
)
from advisor import get_simple_advice
from card_utils import make_hand_from_ids
from card_db import count_cards


def build_mulligan_state_from_db() -> GameState:
    """
    Example mulligan state using real card IDs from the database.
    Replace the card IDs below with actual IDs you care about
    (check /cards API to find them).
    """

    # Example: these IDs should match real card_id values in your DB.
    # You can grab them from /cards or directly from DotGG's JSON.
    my_hand_ids = [
        "OGN-179",  # Acceptable Losses (example)
        "OGN-045",  # some unit
        "OGN-185",  # some spell
        "OGN-192",  # some gear
    ]

    hand = make_hand_from_ids(my_hand_ids)

    me = PlayerState(
        name="elyvn",
        leader_id="Yasuo",
        mana_total=0,
        mana_by_rune={
            Rune.CHAOS: 1,
            Rune.CALM: 1,
        },
        deck_size=35,
        hand_size=len(hand),
        hand=hand,
    )

    opponent = PlayerState(
        name="Opponent",
        mana_total=0,
        mana_by_rune={},
        deck_size=35,
        hand_size=5,
        hand=[],
    )

    state = GameState(
        source="arena",
        turn=1,
        phase=Phase.MULLIGAN,
        active_player="me",
        me=me,
        opponent=opponent,
        lanes=[],                    # no units on board yet
        environment_cards=[],        # add battlefield IDs here later
    )

    return state


def main() -> None:
    print(f"Cards currently in DB: {count_cards()}")

    mull_state = build_mulligan_state_from_db()

    print("\n=== Mulligan GameState (from DB) ===")
    pprint(mull_state.model_dump(), sort_dicts=False)

    print("\nAdvisor says:")
    print(get_simple_advice(mull_state))


if __name__ == "__main__":
    main()
