# Legend analysis and synergy logic
# legend_analysis.py

from typing import Optional
from game_state import CardInHand, PlayerState, CardType
from logger_config import advisor_logger, log_legend_interaction

def requires_legend_exhaustion(card: CardInHand) -> bool:
    """Check if a card's rules text indicates it requires exhausting the legend."""
    if card.rules_text and "exhaust your legend as an additional cost" in card.rules_text.lower():
        return True
    return False


def can_exhaust_legend(player: PlayerState) -> bool:
    """Check if the player has a legend and it is not exhausted."""
    if player.legend is None:
        return False
    return not player.legend.exhausted


def analyze_legend_synergy(card: CardInHand, player: PlayerState, opponent: Optional[PlayerState] = None) -> Optional[str]:
    """
    Analyze how a card interacts with the player's legend abilities and opponent's legend.
    Returns a string describing the synergy, or None if no relevant interaction.
    """
    synergy_notes = []
    legend = player.legend
    
    if legend is None:
        return None
    
    # Check if card requires legend exhaustion
    if requires_legend_exhaustion(card):
        if can_exhaust_legend(player):
            synergy_notes.append(f"Can exhaust {legend.name or 'legend'} for additional effect")
            log_legend_interaction(
                advisor_logger,
                card.card_id,
                legend.card_id,
                "legend_exhaustion_available",
                card_name=card.name,
                legend_name=legend.name
            )
        else:
            synergy_notes.append(f"Requires legend exhaustion but {legend.name or 'legend'} is already exhausted")
            log_legend_interaction(
                advisor_logger,
                card.card_id,
                legend.card_id,
                "legend_exhaustion_unavailable",
                card_name=card.name,
                legend_name=legend.name
            )
    
    # Check if card benefits from legend passive abilities
    if legend.passive_abilities:
        # Simple keyword matching - could be expanded
        for ability in legend.passive_abilities:
            ability_lower = ability.lower()
            # Check for common synergies
            if "bonus damage" in ability_lower and card.card_type == CardType.SPELL:
                synergy_notes.append(f"Benefits from {legend.name or 'legend'}'s bonus damage passive")
            elif "buff" in ability_lower and card.card_type == CardType.UNIT:
                synergy_notes.append(f"May benefit from {legend.name or 'legend'}'s buff abilities")
    
    # Check if card can ready/exhaust legend
    if card.rules_text:
        rules_lower = card.rules_text.lower()
        if "ready" in rules_lower and "legend" in rules_lower:
            if legend.exhausted:
                synergy_notes.append(f"Can ready exhausted {legend.name or 'legend'}")
        elif "exhaust" in rules_lower and "legend" in rules_lower and "exhaust your legend" not in rules_lower:
            if not legend.exhausted:
                synergy_notes.append(f"Can exhaust {legend.name or 'legend'} (may be useful for setup)")
    
    # Check if legend has activated abilities that could help
    if legend.activated_abilities and not legend.exhausted:
        for ability in legend.activated_abilities:
            ability_lower = ability.lower()
            # Check if legend ability could support this card
            if card.card_type == CardType.UNIT:
                if "move" in ability_lower or "battlefield" in ability_lower:
                    synergy_notes.append(f"{legend.name or 'Legend'} can move units to support this play")
                elif "buff" in ability_lower or "might" in ability_lower:
                    synergy_notes.append(f"{legend.name or 'Legend'} can use ability to support this unit")
            elif card.card_type == CardType.GEAR and "attach" in ability_lower:
                synergy_notes.append(f"{legend.name or 'Legend'} can help attach equipment")
    
    # Analyze opponent's legend (for defensive considerations)
    if opponent and opponent.legend:
        op_legend = opponent.legend
        
        # Check if opponent legend has abilities that might counter this play
        if op_legend.triggered_abilities:
            for ability in op_legend.triggered_abilities:
                ability_lower = ability.lower()
                # Warn about opponent legend abilities that might affect our play
                if card.card_type == CardType.UNIT and ("kill" in ability_lower or "destroy" in ability_lower):
                    synergy_notes.append(f"Opponent {op_legend.name or 'legend'} may counter this unit")
                elif card.card_type == CardType.SPELL and "counter" in ability_lower:
                    synergy_notes.append(f"Opponent {op_legend.name or 'legend'} may counter spells")
        
        # Check if opponent legend passive might affect us
        if op_legend.passive_abilities:
            for ability in op_legend.passive_abilities:
                ability_lower = ability.lower()
                if "damage" in ability_lower and card.card_type == CardType.UNIT:
                    synergy_notes.append(f"Opponent {op_legend.name or 'legend'} passive may affect this unit")
    
    if synergy_notes:
        return " | ".join(synergy_notes)
    return None

