# Card evaluation and scoring logic
# card_evaluation.py

from typing import List, Optional
from game_state import GameState, CardInHand, PlayerState, CardType, Battlefield
from logger_config import advisor_logger, log_card_playability
from legend_analysis import requires_legend_exhaustion, can_exhaust_legend

def get_all_playable_cards(state: GameState) -> List[CardInHand]:
    """
    Get all cards that can actually be played using can_play().
    More accurate than playable_cards_by_mana() as it checks rune requirements.
    """
    me = state.me
    return [c for c in me.hand if can_play(c, me)]


def playable_cards_by_mana(state: GameState) -> List[CardInHand]:
    """
    Very simple playability check:
    - A card is considered playable if its energy_cost <= current mana_total.
    - We ignore colored rune constraints for now and focus on curve/tempo.
    """
    me = state.me
    if me.mana_total is None:
        return []

    playable = [c for c in me.hand if c.energy_cost <= (me.mana_total or 0)]
    # Sort by cost, then by type (units first)
    playable.sort(key=lambda c: (c.energy_cost, 0 if c.card_type == CardType.UNIT else 1))
    return playable


def describe_card(card: CardInHand) -> str:
    """Get a human-readable description of a card."""
    cost = card.energy_cost
    t = card.card_type.value
    name = card.name or card.card_id
    return f"{name} ({t}, cost {cost})"


def calculate_card_value(card: CardInHand) -> float:
    """
    Calculate a value score for a card to help prioritize plays.
    Higher score = better value.
    
    Factors:
    - Might per mana (for units)
    - Keyword value (Assault, Guard, etc.)
    - Card type value
    - Cost efficiency
    """
    score = 0.0
    
    if card.card_type == CardType.UNIT:
        # Base value: might per mana
        if card.might and card.energy_cost > 0:
            score += (card.might / card.energy_cost) * 2.0
        elif card.might:
            score += card.might * 2.0
        
        # Keyword bonuses
        keywords_lower = [k.lower() for k in card.keywords] if card.keywords else []
        if "assault" in keywords_lower:
            score += 1.5  # Aggressive keyword
        if "guard" in keywords_lower:
            score += 1.0  # Defensive keyword
        if "support" in keywords_lower:
            score += 0.5  # Utility keyword
        if "weaponmaster" in keywords_lower:
            score += 1.0  # Synergy keyword
        
        # Cost efficiency bonus (cheap units are more flexible)
        if card.energy_cost <= 2:
            score += 1.0
        elif card.energy_cost == 3:
            score += 0.5
    
    elif card.card_type == CardType.SPELL:
        # Spells get base value from tags
        tags_lower = [t.lower() for t in card.tags] if card.tags else []
        if "removal" in tags_lower:
            score += 3.0  # Removal is high value
        if "damage" in tags_lower:
            score += 2.0
        if "buff" in tags_lower or "protection" in tags_lower:
            score += 1.5
        
        # Cheap spells are more flexible
        if card.energy_cost <= 2:
            score += 1.0
    
    elif card.card_type == CardType.GEAR:
        # Gear value depends on context, but base value from cost
        score += 1.0
        if card.energy_cost <= 2:
            score += 0.5
    
    return score


def assess_threat_level(battlefield_analyses: List[dict], opponent: PlayerState) -> dict:
    """
    Assess the threat level from opponent's board.
    Returns threat assessment with priority targets.
    """
    total_opponent_might = sum(b["op_might"] for b in battlefield_analyses)
    contested_count = sum(1 for b in battlefield_analyses if b["state"] == "contested")
    losing_count = sum(1 for b in battlefield_analyses if b["state"] == "losing")
    
    # Find highest threat (largest opponent unit)
    highest_threat = None
    highest_might = 0
    for b in battlefield_analyses:
        if b["op_might"] > highest_might:
            highest_might = b["op_might"]
            highest_threat = b
    
    threat_level = "low"
    if total_opponent_might >= 10:
        threat_level = "high"
    elif total_opponent_might >= 5:
        threat_level = "medium"
    
    return {
        "threat_level": threat_level,
        "total_opponent_might": total_opponent_might,
        "contested_battlefields": contested_count,
        "losing_battlefields": losing_count,
        "highest_threat": highest_threat,
        "needs_removal": highest_might >= 6,  # Large threats need removal
    }


def should_hold_card(card: CardInHand, state: GameState, threat_assessment: dict) -> bool:
    """
    Determine if a card should be held for a better opportunity.
    Returns True if card should be held, False if should play now.
    """
    # Always play cheap cards (cost 0-1) if playable
    if card.energy_cost <= 1:
        return False
    
    # Hold expensive cards early game unless critical
    if state.turn <= 3 and card.energy_cost >= 4:
        # Exception: critical removal against high threat
        if threat_assessment["needs_removal"] and "removal" in [t.lower() for t in (card.tags or [])]:
            return False
        return True
    
    # Hold reaction spells if no immediate threat
    if card.card_type == CardType.SPELL:
        keywords_lower = [k.lower() for k in (card.keywords or [])]
        if "reaction" in keywords_lower and threat_assessment["threat_level"] == "low":
            return True
    
    # Hold expensive units if we're ahead on board
    if card.card_type == CardType.UNIT and card.energy_cost >= 5:
        # Import here to avoid circular dependency
        from battlefield_analysis import analyze_battlefield
        my_total_might = sum(
            b["my_might"] for b in [
                analyze_battlefield(bf, i) for i, bf in enumerate(state.battlefields)
            ]
        )
        if my_total_might > threat_assessment["total_opponent_might"]:
            return True  # We're ahead, can afford to hold
    
    return False


def calculate_mana_efficiency_score(
    cards: List[CardInHand],
    available_mana: int
) -> float:
    """
    Calculate how efficiently we're using mana.
    Returns a score 0-1 where 1 is perfect efficiency.
    """
    if available_mana == 0:
        return 0.0
    
    total_cost = sum(c.energy_cost for c in cards)
    efficiency = min(total_cost / available_mana, 1.0)
    
    # Bonus for using most/all mana
    if efficiency >= 0.9:
        return 1.0
    elif efficiency >= 0.7:
        return efficiency + 0.1
    else:
        return efficiency


def can_play(card: CardInHand, player: PlayerState) -> bool:
    """Check if a card can be played given the player's current resources."""
    # Check total mana
    if player.mana_total is None:
        log_card_playability(
            advisor_logger,
            card.card_id,
            False,
            "No mana available",
            card_name=card.name,
            energy_cost=card.energy_cost
        )
        return False
    
    # Check energy cost (rune tap cost)
    if card.energy_cost > 0:
        # Need to check if player has the required rune tapped
        # For now, simple check: need at least energy_cost total mana
        if player.mana_total < card.energy_cost:
            log_card_playability(
                advisor_logger,
                card.card_id,
                False,
                f"Insufficient mana: need {card.energy_cost}, have {player.mana_total}",
                card_name=card.name,
                energy_cost=card.energy_cost,
                available_mana=player.mana_total
            )
            return False
    
    # Check power cost (rune recycle cost)
    if card.power_cost > 0:
        # Need to check if player has the required runes available
        # For now, simplified check
        if player.mana_total < card.power_cost:
            log_card_playability(
                advisor_logger,
                card.card_id,
                False,
                f"Insufficient mana for power cost: need {card.power_cost}, have {player.mana_total}",
                card_name=card.name,
                power_cost=card.power_cost,
                available_mana=player.mana_total
            )
            return False
    
    # Check power cost by rune
    if hasattr(card, 'power_cost_by_rune') and card.power_cost_by_rune:
        for rune, cost in card.power_cost_by_rune.items():
            available = player.mana_by_rune.get(rune, 0)
            if available < cost:
                log_card_playability(
                    advisor_logger,
                    card.card_id,
                    False,
                    f"Insufficient {rune} rune: need {cost}, have {available}",
                    card_name=card.name,
                    required_rune=rune,
                    required_cost=cost,
                    available_rune=available
                )
                return False
    
    # Check if card requires legend exhaustion and if legend is available
    if requires_legend_exhaustion(card):
        if not can_exhaust_legend(player):
            log_card_playability(
                advisor_logger,
                card.card_id,
                False,
                "Requires legend exhaustion but legend is not available or exhausted",
                available_mana=player.mana_total,
                legend_status="exhausted" if player.legend and player.legend.exhausted else "unavailable"
            )
            return False
    
    log_card_playability(
        advisor_logger,
        card.card_id,
        True,
        "Card is playable",
        card_name=card.name,
        energy_cost=card.energy_cost,
        available_mana=player.mana_total
    )
    return True

