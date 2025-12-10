# demo.py - example of advisor.py

# demo.py

from pprint import pprint

from game_state import (
    GameState,
    PlayerState,
    CardInHand,
    Unit,
    Lane,
    Rune,
    CardType,
    Phase,
)
from advisor import get_simple_advice


def build_mulligan_state() -> GameState:
    """Example: Turn 1 mulligan screen."""
    me = PlayerState(
        name="elyvn",
        leader_id="Yasuo",
        mana_total=0,
        mana_by_rune={
            Rune.CALM: 0,
            Rune.MIND: 0,
        },
        deck_size=34,
        hand_size=5,
        hand=[
            CardInHand(
                card_id="Discipline",
                name="Discipline",
                card_type=CardType.SPELL,
                domain=Rune.ORDER,
                energy_cost=1,
                power_cost=0,
                might=None,
                tags=["buff"],
                keywords=["Action"],
            ),
            CardInHand(
                card_id="MysticFlare",
                name="Mystic Flare",
                card_type=CardType.SPELL,
                domain=Rune.MIND,
                energy_cost=2,
                power_cost=1,
                might=None,
                tags=["removal"],
                keywords=["Reaction"],
            ),
            CardInHand(
                card_id="CalmSpirit",
                name="Calm Spirit",
                card_type=CardType.UNIT,
                domain=Rune.CALM,
                energy_cost=1,
                power_cost=0,
                might=1,
                tags=["unit"],
                keywords=["Support"],
            ),
            CardInHand(
                card_id="VeilDancer",
                name="Veil Dancer",
                card_type=CardType.UNIT,
                domain=Rune.MIND,
                energy_cost=2,
                power_cost=1,
                might=2,
                tags=["unit"],
                keywords=["Assault"],
            ),
            CardInHand(
                card_id="BodyGuard",
                name="Body Guard",
                card_type=CardType.UNIT,
                domain=Rune.BODY,
                energy_cost=3,
                power_cost=1,
                might=3,
                tags=["unit"],
                keywords=["Guard"],
            ),
        ],
    )

    opponent = PlayerState(
        name="Player6479",
        mana_total=0,
        mana_by_rune={},
        deck_size=35,
        hand_size=5,
        hand=[],  # we don't know exact cards in their hand
    )

    state = GameState(
        source="arena",
        turn=1,
        phase=Phase.MULLIGAN,
        active_player="me",
        me=me,
        opponent=opponent,
        lanes=[],
        environment_cards=["Trefarian_War_Camp"],
    )

    return state


def build_main_phase_state() -> GameState:
    """Example: later turn with units on board and some mana."""

    me = PlayerState(
        name="elyvn",
        leader_id="Yasuo",
        mana_total=3,
        mana_by_rune={
            Rune.CALM: 1,
            Rune.MIND: 2,
        },
        deck_size=28,
        hand_size=3,
        hand=[
            CardInHand(
                card_id="VeilDancer",
                name="Veil Dancer",
                card_type=CardType.UNIT,
                domain=Rune.MIND,
                energy_cost=2,
                power_cost=1,
                might=2,
                tags=["unit"],
                keywords=["Assault"],
            ),
            CardInHand(
                card_id="ShieldCharm",
                name="Shield Charm",
                card_type=CardType.SPELL,
                domain=Rune.CALM,
                energy_cost=1,
                power_cost=0,
                might=None,
                tags=["protection"],
                keywords=["Reaction"],
            ),
            CardInHand(
                card_id="BodyGuard",
                name="Body Guard",
                card_type=CardType.UNIT,
                domain=Rune.BODY,
                energy_cost=3,
                power_cost=1,
                might=3,
                tags=["unit"],
                keywords=["Guard"],
            ),
        ],
    )

    opponent = PlayerState(
        name="Player6479",
        mana_total=2,
        mana_by_rune={
            Rune.FURY: 2,
        },
        deck_size=27,
        hand_size=4,
        hand=[],
    )

    lane_1 = Lane(
        my_unit=Unit(
            card_id="CalmSpirit",
            might=1,
            base_might=1,
            current_might=1,
            damage_marked=0,
            domain=Rune.CALM,
            keywords=["Support"],
            attached_gear_ids=[],
            exhausted=False,
        ),
        op_unit=Unit(
            card_id="FuryRaider",
            might=2,
            base_might=2,
            current_might=2,
            damage_marked=0,
            domain=Rune.FURY,
            keywords=["Charge"],
            attached_gear_ids=[],
            exhausted=False,
        ),
    )

    lane_2 = Lane(
        my_unit=None,
        op_unit=None,
    )

    state = GameState(
        source="arena",
        turn=3,
        phase=Phase.MAIN,
        active_player="me",
        me=me,
        opponent=opponent,
        lanes=[lane_1, lane_2],
        environment_cards=["Trefarian_War_Camp"],
    )

    return state


def main() -> None:
    print("=== Mulligan GameState ===")
    mull_state = build_mulligan_state()
    pprint(mull_state.model_dump(), sort_dicts=False)
    print("\nAdvisor says (mulligan):")
    print(get_simple_advice(mull_state))

    print("\n=== Main Phase GameState ===")
    main_state = build_main_phase_state()
    pprint(main_state.model_dump(), sort_dicts=False)
    print("\nAdvisor says (main phase):")
    print(get_simple_advice(main_state))


if __name__ == "__main__":
    main()
