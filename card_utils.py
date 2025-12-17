# card_utils.py
#
# Helpers to bridge between the card database and GameState models.

import logging 

from typing import Iterable, List, Tuple
from game_state import CardInHand, CardType, Rune
from card_db import CardRecord, get_card
from advisor_models import BattlefieldState

logger = logging.getLogger(__name__)

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
            logger.warning(f"[make_hand_from_ids] Warning: card_id '{cid}' not found in DB")
            missing_ids.append(cid)
            continue
        hand.append(record_to_card_in_hand(rec))

    return hand, missing_ids


def load_battlefield_state(battlefield_state: BattlefieldState) -> BattlefieldState:
    """
    Enrich battlefield state with full card data from database.
    
    Takes a BattlefieldState with just IDs and might values,
    returns a BattlefieldState with full unit dictionaries.
    """
    my_unit = None
    opponent_unit = None
    
    # Load my unit if present
    if battlefield_state.my_unit_id:
        my_card = get_card(battlefield_state.my_unit_id)
        if my_card:
            my_unit = {
                "card_id": my_card.card_id,
                "name": my_card.name,
                "might": battlefield_state.my_unit_might if battlefield_state.my_unit_might is not None else my_card.might
            }
    
    # Load opponent unit if present
    if battlefield_state.opponent_unit_id:
        op_card = get_card(battlefield_state.opponent_unit_id)
        if op_card:
            opponent_unit = {
                "card_id": op_card.card_id,
                "name": op_card.name,
                "might": battlefield_state.opponent_unit_might if battlefield_state.opponent_unit_might is not None else op_card.might
            }
    
    # Return a new BattlefieldState with enriched data
    return BattlefieldState(
        battlefield_id=battlefield_state.battlefield_id,
        my_unit_id=battlefield_state.my_unit_id,
        my_unit_might=battlefield_state.my_unit_might,
        opponent_unit_id=battlefield_state.opponent_unit_id,
        opponent_unit_might=battlefield_state.opponent_unit_might,
        # These are used internally by the analyzer
        my_unit=my_unit,
        opponent_unit=opponent_unit
    )
