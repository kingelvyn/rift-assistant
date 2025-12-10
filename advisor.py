# Riftbound advisor
# advisor.py

from typing import Optional
from game_state import GameState, CardInHand, PlayerState, Rune

def get_simple_advice(state: GameState) -> str:
    """Generate simple advice based on the current game state."""
    if not state.me.hand:
        return "You have no cards in hand. Trade on board or end your turn."

    # Simple rule-based advice
    if state.me.mana_total is None or state.me.mana_total == 0:
        return "You have no mana. Consider passing or ending your turn."

    # Find playable cards
    playable_cards = [
        card for card in state.me.hand
        if can_play(card, state.me)
    ]

    if not playable_cards:
        return "No playable cards in hand. Consider passing or ending your turn."

    # Simple heuristic: suggest the first playable card
    suggested_card = playable_cards[0]
    return f"Consider playing '{suggested_card.name or suggested_card.card_id}' this turn with your {state.me.mana_total} mana."


def can_play(card: CardInHand, player: PlayerState) -> bool:
    """Check if a card can be played given the player's current resources."""
    # Check total mana
    if player.mana_total is None:
        return False
    
    # Check energy cost (rune tap cost)
    if card.energy_cost > 0:
        # Need to check if player has the required rune tapped
        # For now, simple check: need at least energy_cost total mana
        if player.mana_total < card.energy_cost:
            return False
    
    # Check power cost (rune recycle cost)
    if card.power_cost > 0:
        # Need to check if player has the required runes available
        # For now, simplified check
        if player.mana_total < card.power_cost:
            return False
    
    # Check power cost by rune
    if card.power_cost_by_rune:
        for rune, cost in card.power_cost_by_rune.items():
            available = player.mana_by_rune.get(rune, 0)
            if available < cost:
                return False
    
    return True
