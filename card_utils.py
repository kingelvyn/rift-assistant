# card_utils.py
#
# Helpers to bridge between the card database and GameState models.

from typing import Iterable, List, Tuple

from game_state import CardInHand, CardType, Rune
from card_db import CardRecord, get_card


def record_to_card_in_hand(record: CardRecord) -> CardInHand:
    """
    Convert a CardRecord (from cards.db) into a CardInHand model
    suitable for use inside GameState.
    """
    return CardInHand(
        card_id=record.card_id,
        name=record.name,
        card_type=record.card_type,
        domain=record.domain,
        energy_cost=record.energy_cost,
        power_cost=record.power_cost,
        # we don't have per-rune power_cost breakdown from dotgg yet
        power_cost_by_rune={},
        might=record.might,
        tags=record.tags,
        keywords=record.keywords,
        element=None,    # can be filled later if you want
        keep=True,       # mulligan logic will decide this later
    )


def make_hand_from_ids(card_ids: Iterable[str]) -> Tuple[List[CardInHand], List[str]]:
    """
    Convenience: load several cards by ID and build a list[CardInHand].
    
    Returns:
        Tuple of (hand, missing_ids) where:
        - hand: List of successfully loaded CardInHand objects
        - missing_ids: List of card IDs that weren't found in the database
    """
    hand: List[CardInHand] = []
    missing_ids: List[str] = []

    for cid in card_ids:
        rec = get_card(cid)
        if rec is None:
            print(f"[make_hand_from_ids] Warning: card_id '{cid}' not found in DB")
            missing_ids.append(cid)
            continue
        hand.append(record_to_card_in_hand(rec))

    return hand, missing_ids