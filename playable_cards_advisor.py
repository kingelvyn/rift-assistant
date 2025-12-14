# advisor.py (or create playable_cards_advisor.py)

from typing import List, Optional
from game_state import CardInHand, CardType
from card_db import CardRecord
from advisor_models import (
    PlayableCardsAdvice,
    PlayableCardRecommendation,
    ScoringDebugInfo,
    BattlefieldPlacement,
)


def analyze_playable_cards(
    hand: List[CardInHand],
    my_mana: int,
    turn: int,
    phase: str,
    my_legend: Optional[CardRecord] = None,
    opponent_legend: Optional[CardRecord] = None,
    my_legend_exhausted: bool = False,
    opponent_legend_exhausted: bool = False,
    battlefields: Optional[List[dict]] = None,
    going_first: bool = True
) -> PlayableCardsAdvice:
    """
    Analyze playable cards and provide strategic recommendations.
    
    Args:
        hand: Cards in player's hand
        my_mana: Available mana this turn
        turn: Current turn number
        phase: Game phase (main/combat/showdown)
        my_legend: Player's legend card
        opponent_legend: Opponent's legend card
        my_legend_exhausted: Whether player's legend is exhausted
        opponent_legend_exhausted: Whether opponent's legend is exhausted
        battlefields: Battlefield states (optional)
        going_first: Whether player went first
    
    Returns:
        PlayableCardsAdvice with recommendations
    """
    
    if not hand:
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            summary="No cards in hand to play."
        )
    
    # Filter playable cards based on mana
    playable = [card for card in hand if card.energy_cost <= my_mana]
    
    if not playable:
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            summary=f"No playable cards with {my_mana} mana. Cards in hand require more resources."
        )
    
    # Determine game phase
    early_game = turn <= 3
    mid_game = 4 <= turn <= 6
    late_game = turn > 6
    game_phase = "early" if early_game else ("mid" if mid_game else "late")
    
    # Analyze battlefield state
    battlefield_summary = _analyze_battlefield_state(battlefields) if battlefields else None
    
    # Categorize playable cards
    playable_units = [c for c in playable if c.card_type == CardType.UNIT]
    playable_spells = [c for c in playable if c.card_type == CardType.SPELL]
    playable_gear = [c for c in playable if c.card_type == CardType.GEAR]
    
    # Calculate card values
    card_values = {card.card_id: _calculate_card_value(card, turn, my_mana) for card in playable}
    
    # Generate recommendations
    recommendations: List[PlayableCardRecommendation] = []
    recommended_ids: List[str] = []
    priority = 1
    
    # Early game: prioritize cheap units
    if early_game and playable_units:
        cheap_units = sorted(
            [c for c in playable_units if c.energy_cost <= 2],
            key=lambda c: card_values.get(c.card_id, 0),
            reverse=True
        )
        
        for card in cheap_units[:2]:  # Top 2 cheap units
            battlefield_placement = _find_best_battlefield(card, battlefields, turn) if battlefields else None
            
            reason = f"Early game: develop board with cheap unit"
            if card.keywords:
                key_keywords = [k for k in card.keywords if k.lower() in ["assault", "guard", "ambush"]]
                if key_keywords:
                    reason += f" with {', '.join(key_keywords)}"
            
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=card.card_id,
                    name=card.name,
                    card_type=card.card_type,
                    energy_cost=card.energy_cost,
                    priority=priority,
                    recommended=True,
                    reason=reason,
                    battlefield_placement=battlefield_placement,
                    value_score=card_values.get(card.card_id, 0.0)
                )
            )
            recommended_ids.append(card.card_id)
            priority += 1
    
    # Mid/late game units
    if not early_game and playable_units:
        strong_units = sorted(
            playable_units,
            key=lambda c: (card_values.get(c.card_id, 0), c.might or 0),
            reverse=True
        )
        
        for card in strong_units[:2]:  # Top 2 units
            if card.card_id not in recommended_ids:
                battlefield_placement = _find_best_battlefield(card, battlefields, turn) if battlefields else None
                
                might_str = f" ({card.might} might)" if card.might else ""
                reason = f"Strong unit{might_str} for board presence"
                
                recommendations.append(
                    PlayableCardRecommendation(
                        card_id=card.card_id,
                        name=card.name,
                        card_type=card.card_type,
                        energy_cost=card.energy_cost,
                        priority=priority,
                        recommended=True,
                        reason=reason,
                        battlefield_placement=battlefield_placement,
                        value_score=card_values.get(card.card_id, 0.0)
                    )
                )
                recommended_ids.append(card.card_id)
                priority += 1
    
    # Removal spells (if opponent has units)
    has_opponent_units = battlefield_summary and battlefield_summary.get("opponent_units", 0) > 0
    if has_opponent_units and playable_spells:
        removal_spells = [
            c for c in playable_spells
            if any(tag.lower() in ["removal", "damage", "destroy"] for tag in (c.tags or []))
        ]
        
        if removal_spells and removal_spells[0].card_id not in recommended_ids:
            best_removal = min(removal_spells, key=lambda c: c.energy_cost)
            
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=best_removal.card_id,
                    name=best_removal.name,
                    card_type=best_removal.card_type,
                    energy_cost=best_removal.energy_cost,
                    priority=priority,
                    recommended=True,
                    reason="Removal spell to answer opponent's threats",
                    value_score=card_values.get(best_removal.card_id, 0.0)
                )
            )
            recommended_ids.append(best_removal.card_id)
            priority += 1
    
    # Add remaining playable cards as lower priority
    for card in playable:
        if card.card_id not in recommended_ids:
            reason = "Playable but lower priority"
            if card.energy_cost >= 4 and early_game:
                reason = "Expensive for early game - consider saving"
            
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=card.card_id,
                    name=card.name,
                    card_type=card.card_type,
                    energy_cost=card.energy_cost,
                    priority=priority,
                    recommended=False,
                    reason=reason,
                    value_score=card_values.get(card.card_id, 0.0)
                )
            )
            priority += 1
    
    # Calculate mana efficiency
    recommended_mana = sum(c.energy_cost for c in playable if c.card_id in recommended_ids)
    efficiency_score = recommended_mana / my_mana if my_mana > 0 else 0.0
    
    efficiency_pct = (recommended_mana / my_mana * 100) if my_mana > 0 else 0
    mana_note = f"Recommended plays use {recommended_mana}/{my_mana} mana ({efficiency_pct:.0f}%)"
    
    if efficiency_score >= 0.9:
        mana_note += " - efficient use of resources"
    elif efficiency_score < 0.5:
        mana_note += " - consider additional plays or hold for better opportunities"
    
    # Build summary
    summary_parts = []
    summary_parts.append(f"Turn {turn} ({game_phase} game, {phase} phase)")
    summary_parts.append(f"{len(recommended_ids)} recommended play(s) from {len(playable)} playable cards")
    
    if battlefield_summary:
        summary_parts.append(
            f"Board: {battlefield_summary['empty']} empty, "
            f"{battlefield_summary['my_units']} yours, "
            f"{battlefield_summary['opponent_units']} opponent's"
        )
    
    if early_game:
        summary_parts.append("Focus: early board development")
    elif mid_game:
        summary_parts.append("Focus: tempo and value trades")
    else:
        summary_parts.append("Focus: high-impact finishers")
    
    summary = ". ".join(summary_parts) + "."
    
    # Debug info
    scoring_debug = ScoringDebugInfo(
        card_value_scores=card_values,
        threat_assessment={"level": "calculated"},  # Simplified
        mana_efficiency_score=efficiency_score,
        battlefield_analyses=battlefields or [],
        game_phase=game_phase
    )
    
    return PlayableCardsAdvice(
        playable_cards=recommendations,
        recommended_plays=recommended_ids,
        summary=summary,
        mana_efficiency_note=mana_note,
        scoring_debug=scoring_debug
    )


def _analyze_battlefield_state(battlefields: List[dict]) -> dict:
    """Analyze battlefield state for strategic decisions."""
    empty = sum(1 for b in battlefields if not b.get("my_unit") and not b.get("op_unit"))
    my_units = sum(1 for b in battlefields if b.get("my_unit"))
    opponent_units = sum(1 for b in battlefields if b.get("op_unit"))
    
    return {
        "empty": empty,
        "my_units": my_units,
        "opponent_units": opponent_units,
        "contested": sum(1 for b in battlefields if b.get("my_unit") and b.get("op_unit"))
    }


def _calculate_card_value(card: CardInHand, turn: int, available_mana: int) -> float:
    """Calculate simple value score for a card."""
    value = 0.0
    
    # Base value from might/cost ratio
    if card.card_type == CardType.UNIT and card.might:
        value += (card.might / max(card.energy_cost, 1)) * 10
    
    # Keyword bonuses
    if card.keywords:
        important_keywords = ["assault", "guard", "flying", "ambush"]
        value += sum(2 for k in card.keywords if k.lower() in important_keywords)
    
    # Early game bonus for cheap cards
    if turn <= 3 and card.energy_cost <= 2:
        value += 5
    
    # Penalty for overcosted cards
    if card.energy_cost > available_mana * 0.7:
        value -= 3
    
    return max(value, 0.0)


def _find_best_battlefield(
    card: CardInHand,
    battlefields: List[dict],
    turn: int
) -> Optional[BattlefieldPlacement]:
    """Find best battlefield placement for a unit."""
    if not battlefields:
        return None
    
    # Prefer empty battlefields
    for idx, battlefield in enumerate(battlefields):
        if not battlefield.get("my_unit") and not battlefield.get("op_unit"):
            return BattlefieldPlacement(
                battlefield_index=idx,
                reason="Empty battlefield - free development",
                priority=1
            )
    
    # Then consider contested battlefields where we can win
    for idx, battlefield in enumerate(battlefields):
        if not battlefield.get("my_unit") and battlefield.get("op_unit"):
            op_might = battlefield["op_unit"].get("might", 0)
            if card.might and card.might > op_might:
                return BattlefieldPlacement(
                    battlefield_index=idx,
                    reason=f"Contest and win against {op_might} might opponent",
                    priority=2
                )
    
    return None