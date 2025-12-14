# advisor.py (or create playable_cards_advisor.py)

from typing import List, Optional, Dict
from game_state import CardInHand, CardType, Rune
from card_db import CardRecord
from advisor_models import (
    PlayableCardsAdvice,
    PlayableCardRecommendation,
    ScoringDebugInfo,
    BattlefieldPlacement,
    BattlefieldState,
)



def _filter_playable_cards(
    hand: List[CardInHand],
    my_energy: int,
    my_power: Dict[str, int]
) -> List[CardInHand]:
    """Filter cards that can actually be played with available resources."""
    playable = []
    
    for card in hand:
        # Check energy cost
        if card.energy_cost > my_energy:
            continue
        
        # Check power cost
        # If card has a domain/color, we need power of that color
        if card.domain and card.domain != Rune.COLORLESS:
            domain_str = card.domain.value if hasattr(card.domain, 'value') else str(card.domain)
            available_power = my_power.get(domain_str.lower(), 0)
            
            # Assuming card.power_cost is the required power
            required_power = card.power_cost or 0
            
            if required_power > available_power:
                continue  # Can't afford power cost
        
        playable.append(card)
    
    return playable


def _determine_game_phase(turn: int) -> str:
    """Determine if we're in early, mid, or late game."""
    if turn <= 3:
        return "early"
    elif turn <= 6:
        return "mid"
    else:
        return "late"


def _assess_threat_level(
    battlefield_analysis: dict,
    opponent_health: Optional[int],
    my_health: Optional[int]
) -> str:
    """Assess overall threat level from opponent."""
    # High threat if:
    # - Opponent controls both battlefields
    # - Opponent has significantly more might
    # - We're low on health and opponent has units
    
    if battlefield_analysis['opponent_only_battlefields'] == 2:
        return "critical"  # Opponent controls both battlefields
    
    might_diff = battlefield_analysis['opponent_total_might'] - battlefield_analysis['my_total_might']
    
    if might_diff >= 4:
        return "high"  # Opponent has much more board presence
    
    if my_health and my_health <= 10 and battlefield_analysis['opponent_units'] > 0:
        return "high"  # Low health with opponent units threatening
    
    if battlefield_analysis['losing_battlefields'] >= 1:
        return "medium"  # Losing at least one battlefield
    
    return "low"


def _recommend_battlefield_development(
    playable_units: List[CardInHand],
    battlefields: List[BattlefieldState],
    battlefield_analysis: dict,
    card_values: dict,
    recommendations: List,
    recommended_ids: List[str],
    priority: int,
    game_phase: str
) -> int:
    """Recommend units to play into empty battlefields."""
    # Sort units by value
    sorted_units = sorted(
        playable_units,
        key=lambda c: card_values.get(c.card_id, 0),
        reverse=True
    )
    
    units_placed = 0
    for card in sorted_units:
        if card.card_id in recommended_ids:
            continue
        
        # Find best empty battlefield
        for idx, bf in enumerate(battlefields):
            if bf.my_unit is None and bf.opponent_unit is None:
                reason = f"Develop empty battlefield #{idx + 1}"
                
                if game_phase == "early":
                    reason += " - early board control is critical"
                
                if card.keywords:
                    key_keywords = [k for k in card.keywords if k.lower() in ["assault", "guard", "ambush", "flying"]]
                    if key_keywords:
                        reason += f" ({', '.join(key_keywords)})"
                
                recommendations.append(
                    PlayableCardRecommendation(
                        card_id=card.card_id,
                        name=card.name,
                        card_type=card.card_type,
                        energy_cost=card.energy_cost,
                        priority=priority,
                        recommended=True,
                        reason=reason,
                        battlefield_placement=BattlefieldPlacement(
                            battlefield_index=idx,
                            reason=f"Empty battlefield - free development",
                            priority=1
                        ),
                        value_score=card_values.get(card.card_id, 0.0)
                    )
                )
                recommended_ids.append(card.card_id)
                priority += 1
                units_placed += 1
                break
        
        if units_placed >= battlefield_analysis['empty_battlefields']:
            break
    
    return priority


def _recommend_contested_plays(
    playable_units: List[CardInHand],
    battlefields: List[BattlefieldState],
    battlefield_analysis: dict,
    card_values: dict,
    recommendations: List,
    recommended_ids: List[str],
    priority: int
) -> int:
    """Recommend units to contest opponent-controlled battlefields."""
    for card in playable_units:
        if card.card_id in recommended_ids:
            continue
        
        # Find battlefields where opponent has a unit but we don't
        for idx, bf in enumerate(battlefields):
            if bf.my_unit is None and bf.opponent_unit is not None:
                op_might = bf.opponent_unit.get('might', 0)
                my_might = card.might or 0
                
                if my_might > op_might:
                    reason = f"Contest battlefield #{idx + 1} and win ({my_might} vs {op_might} might)"
                    recommended = True
                    placement_priority = 2
                elif my_might == op_might:
                    reason = f"Contest battlefield #{idx + 1} (tied at {my_might} might)"
                    recommended = True
                    placement_priority = 3
                else:
                    reason = f"Contest battlefield #{idx + 1} but losing ({my_might} vs {op_might} might) - may need support"
                    recommended = False
                    placement_priority = 4
                
                recommendations.append(
                    PlayableCardRecommendation(
                        card_id=card.card_id,
                        name=card.name,
                        card_type=card.card_type,
                        energy_cost=card.energy_cost,
                        priority=priority,
                        recommended=recommended,
                        reason=reason,
                        battlefield_placement=BattlefieldPlacement(
                            battlefield_index=idx,
                            reason=reason,
                            priority=placement_priority
                        ),
                        value_score=card_values.get(card.card_id, 0.0)
                    )
                )
                if recommended:
                    recommended_ids.append(card.card_id)
                priority += 1
                break
    
    return priority


def _recommend_removal_spells(
    playable_spells: List[CardInHand],
    threat_level: str,
    card_values: dict,
    recommendations: List,
    recommended_ids: List[str],
    priority: int
) -> int:
    """Recommend removal spells based on threat level."""
    removal_spells = [
        c for c in playable_spells
        if any(tag.lower() in ["removal", "damage", "destroy", "kill"] for tag in (c.tags or []))
    ]
    
    if not removal_spells:
        return priority
    
    # Sort by cost (cheaper first unless high threat)
    if threat_level in ["high", "critical"]:
        # High threat: prioritize effectiveness over cost
        removal_spells.sort(key=lambda c: -card_values.get(c.card_id, 0))
    else:
        removal_spells.sort(key=lambda c: c.energy_cost)
    
    best_removal = removal_spells[0]
    if best_removal.card_id not in recommended_ids:
        threat_desc = {
            "critical": "Critical threat - opponent controls board",
            "high": "High threat - significant opponent presence",
            "medium": "Moderate threat - contested board",
            "low": "Answer opponent's unit"
        }
        
        recommendations.append(
            PlayableCardRecommendation(
                card_id=best_removal.card_id,
                name=best_removal.name,
                card_type=best_removal.card_type,
                energy_cost=best_removal.energy_cost,
                priority=priority if threat_level in ["high", "critical"] else priority + 5,
                recommended=True,
                reason=f"Removal: {threat_desc.get(threat_level, 'Answer threat')}",
                value_score=card_values.get(best_removal.card_id, 0.0)
            )
        )
        recommended_ids.append(best_removal.card_id)
        priority += 1
    
    return priority


def _recommend_gear(
    playable_gear: List[CardInHand],
    battlefield_analysis: dict,
    card_values: dict,
    recommendations: List,
    recommended_ids: List[str],
    priority: int
) -> int:
    """Recommend gear to equip on existing units."""
    if battlefield_analysis['my_units'] == 0:
        return priority
    
    # Prioritize cheap gear
    playable_gear.sort(key=lambda c: c.energy_cost)
    best_gear = playable_gear[0] if playable_gear else None
    
    if best_gear and best_gear.card_id not in recommended_ids:
        unit_context = f"{battlefield_analysis['my_units']} unit(s)"
        reason = f"Equip gear on your {unit_context} for value"
        
        if battlefield_analysis['contested_battlefields'] > 0:
            reason += " - can swing contested battlefields"
        
        recommendations.append(
            PlayableCardRecommendation(
                card_id=best_gear.card_id,
                name=best_gear.name,
                card_type=best_gear.card_type,
                energy_cost=best_gear.energy_cost,
                priority=priority,
                recommended=True,
                reason=reason,
                value_score=card_values.get(best_gear.card_id, 0.0)
            )
        )
        recommended_ids.append(best_gear.card_id)
        priority += 1
    
    return priority


def _recommend_utility_spells(
    playable_spells: List[CardInHand],
    phase: str,
    battlefield_analysis: dict,
    card_values: dict,
    recommendations: List,
    recommended_ids: List[str],
    priority: int
) -> int:
    """Recommend utility and buff spells."""
    utility_spells = [
        c for c in playable_spells
        if c.card_id not in recommended_ids
        and any(tag.lower() in ["buff", "protection", "draw", "utility"] for tag in (c.tags or []))
    ]
    
    for spell in utility_spells[:2]:  # Top 2 utility spells
        reason = "Utility spell"
        recommended = False
        
        # Buff spells are good if we have units
        if "buff" in [t.lower() for t in (spell.tags or [])] and battlefield_analysis['my_units'] > 0:
            reason = f"Buff spell to enhance your {battlefield_analysis['my_units']} unit(s)"
            recommended = True
        
        # Draw spells
        elif "draw" in [t.lower() for t in (spell.tags or [])]:
            reason = "Card draw for more options"
            recommended = True
        
        # Protection
        elif "protection" in [t.lower() for t in (spell.tags or [])]:
            if battlefield_analysis['contested_battlefields'] > 0:
                reason = "Protection spell - save for contested battlefield"
                recommended = False  # Hold for the right moment
            else:
                reason = "Protection spell - hold for critical moment"
                recommended = False
        
        recommendations.append(
            PlayableCardRecommendation(
                card_id=spell.card_id,
                name=spell.name,
                card_type=spell.card_type,
                energy_cost=spell.energy_cost,
                priority=priority + (0 if recommended else 10),
                recommended=recommended,
                reason=reason,
                value_score=card_values.get(spell.card_id, 0.0)
            )
        )
        if recommended:
            recommended_ids.append(spell.card_id)
        priority += 1
    
    return priority


def _calculate_card_value(
    card: CardInHand,
    turn: int,
    battlefield_analysis: dict,
    my_legend: Optional[CardRecord]
) -> float:
    """Calculate value score for a card in context."""
    value = 0.0
    
    # Base value from stats
    if card.card_type == CardType.UNIT and card.might:
        # Might per energy is key metric
        value += (card.might / max(card.energy_cost, 1)) * 10
    
    # Keyword bonuses
    if card.keywords:
        keyword_values = {
            "assault": 3,      # Extra damage
            "guard": 2,        # Protects other units
            "flying": 2,       # Hard to block
            "ambush": 2,       # Surprise factor
            "overwhelm": 3,    # Damage through
            "lifesteal": 2,    # Sustain
        }
        for keyword in card.keywords:
            value += keyword_values.get(keyword.lower(), 1)
    
    # Context bonuses
    game_phase = _determine_game_phase(turn)
    
    if game_phase == "early" and card.energy_cost <= 2:
        value += 5  # Early game values cheap cards
    
    if game_phase == "late" and card.card_type == CardType.UNIT and (card.might or 0) >= 4:
        value += 3  # Late game values big units
    
    # Removal is valuable when opponent has units
    if card.card_type == CardType.SPELL and battlefield_analysis['opponent_units'] > 0:
        if any(tag.lower() in ["removal", "destroy"] for tag in (card.tags or [])):
            value += battlefield_analysis['opponent_units'] * 2
    
    # Gear is valuable when we have units
    if card.card_type == CardType.GEAR and battlefield_analysis['my_units'] > 0:
        value += battlefield_analysis['my_units'] * 1.5
    
    return max(value, 0.0)


def _get_low_priority_reason(
    card: CardInHand,
    game_phase: str,
    battlefield_analysis: dict
) -> str:
    """Generate reason for why a card is low priority."""
    if card.card_type == CardType.UNIT:
        if card.energy_cost >= 4 and game_phase == "early":
            return "Expensive unit for early game - consider holding"
        if battlefield_analysis['empty_battlefields'] == 0 and battlefield_analysis['my_only_battlefields'] == 2:
            return "Both battlefields already occupied - may be overcommitting"
        return "Lower value unit - play if needed"
    
    elif card.card_type == CardType.SPELL:
        if not card.tags:
            return "Situational spell - wait for right moment"
        if "draw" in [t.lower() for t in card.tags]:
            return "Card draw - good but not urgent"
        return "Utility spell - play when specific situation arises"
    
    elif card.card_type == CardType.GEAR:
        if battlefield_analysis['my_units'] == 0:
            return "Gear requires units on board first"
        return "Equipment - good value but lower priority"
    
    return "Playable but situational"


def _analyze_riftbound_battlefields(battlefields: List[BattlefieldState]) -> dict:
    """Analyze the state of both battlefields in 1v1."""
    analysis = {
        'empty_battlefields': 0,           # No units on either side
        'my_only_battlefields': 0,         # Only I have a unit
        'opponent_only_battlefields': 0,   # Only opponent has a unit
        'contested_battlefields': 0,       # Both have units
        'my_units': 0,                     # Total units I control
        'opponent_units': 0,               # Total opponent units
        'my_total_might': 0,               # Sum of my unit might
        'opponent_total_might': 0,         # Sum of opponent might
        'winning_battlefields': 0,         # Battlefields where my might > opponent
        'losing_battlefields': 0,          # Battlefields where opponent might > mine
        'tied_battlefields': 0,            # Equal might
    }
    
    for bf in battlefields:
        has_my_unit = bf.my_unit is not None
        has_op_unit = bf.opponent_unit is not None
        
        if not has_my_unit and not has_op_unit:
            analysis['empty_battlefields'] += 1
        elif has_my_unit and not has_op_unit:
            analysis['my_only_battlefields'] += 1
        elif not has_my_unit and has_op_unit:
            analysis['opponent_only_battlefields'] += 1
        else:  # Both have units
            analysis['contested_battlefields'] += 1
            
            my_might = bf.my_unit.get('might', 0)
            op_might = bf.opponent_unit.get('might', 0)
            
            if my_might > op_might:
                analysis['winning_battlefields'] += 1
            elif op_might > my_might:
                analysis['losing_battlefields'] += 1
            else:
                analysis['tied_battlefields'] += 1
        
        if has_my_unit:
            analysis['my_units'] += 1
            analysis['my_total_might'] += bf.my_unit.get('might', 0)
        
        if has_op_unit:
            analysis['opponent_units'] += 1
            analysis['opponent_total_might'] += bf.opponent_unit.get('might', 0)
    
    return analysis


def _find_best_battlefield(
    card: CardInHand,
    battlefields: List[BattlefieldState],
    turn: int
) -> Optional[BattlefieldPlacement]:
    """Find best battlefield placement for a unit."""
    if not battlefields:
        return None
    
    # Prefer empty battlefields
    for idx, battlefield in enumerate(battlefields):
        if not battlefield.my_unit and not battlefield.opponent_unit:
            return BattlefieldPlacement(
                battlefield_index=idx,
                reason="Empty battlefield - free development",
                priority=1
            )
    
    # Then consider contested battlefields where we can win
    for idx, battlefield in enumerate(battlefields):
        # ✅ Use direct attribute access
        if not battlefield.my_unit and battlefield.opponent_unit:
            op_might = battlefield.opponent_unit.get("might", 0)  # This is still a dict
            if card.might and card.might > op_might:
                return BattlefieldPlacement(
                    battlefield_index=idx,
                    reason=f"Contest and win against {op_might} might opponent",
                    priority=2
                )
    
    return None

 
def _build_strategy_summary(
    turn: int,
    game_phase: str,
    phase: str,
    recommended_count: int,
    playable_count: int,
    battlefield_analysis: dict,
    threat_level: str,
    my_health: Optional[int],
    opponent_health: Optional[int]
) -> str:
    """Build comprehensive strategy summary."""
    parts = []
    
    # Game state
    parts.append(f"Turn {turn} ({game_phase} game, {phase} phase)")
    
    # Recommendations
    if recommended_count > 0:
        parts.append(f"{recommended_count} recommended play(s) from {playable_count} playable cards")
    else:
        parts.append(f"{playable_count} playable cards, but holding may be better")
    
    # Battlefield state (2 battlefields in 1v1)
    bf_parts = []
    if battlefield_analysis['empty_battlefields'] > 0:
        bf_parts.append(f"{battlefield_analysis['empty_battlefields']} empty")
    if battlefield_analysis['my_only_battlefields'] > 0:
        bf_parts.append(f"{battlefield_analysis['my_only_battlefields']} yours")
    if battlefield_analysis['opponent_only_battlefields'] > 0:
        bf_parts.append(f"{battlefield_analysis['opponent_only_battlefields']} opponent's")
    if battlefield_analysis['contested_battlefields'] > 0:
        bf_parts.append(f"{battlefield_analysis['contested_battlefields']} contested")
    
    if bf_parts:
        parts.append(f"Battlefields: {', '.join(bf_parts)}")
    
    # Threat assessment
    threat_messages = {
        "critical": "CRITICAL: Opponent controls both battlefields!",
        "high": "High threat: Opponent has strong board presence",
        "medium": "Moderate threat: Board is contested",
        "low": "Low threat: Favorable board state"
        }
    
    parts.append(threat_messages.get(threat_level, "Board state unclear"))

    # Health context
    if my_health and opponent_health:
        health_diff = my_health - opponent_health
        if health_diff <= -5:
            parts.append(f"Behind on life ({my_health} vs {opponent_health}) - need pressure")
        elif health_diff >= 5:
            parts.append(f"Ahead on life ({my_health} vs {opponent_health}) - maintain advantage")

    # Strategic focus
    focus_messages = {
        "early": "Focus: Develop board, contest battlefields early",
        "mid": "Focus: Tempo plays and favorable trades",
        "late": "Focus: High-impact finishers and closing"
    }
    parts.append(focus_messages[game_phase])

    return ". ".join(parts) + "."
    

def analyze_playable_cards(
    hand: List[CardInHand],
    my_energy: int,
    my_power: Dict[str, int],
    turn: int,
    phase: str,
    battlefields: List[BattlefieldState],
    my_legend: Optional[CardRecord] = None,
    opponent_legend: Optional[CardRecord] = None,
    my_legend_exhausted: bool = False,
    opponent_legend_exhausted: bool = False,
    going_first: bool = True,
    my_health: Optional[int] = None,
    opponent_health: Optional[int] = None,
) -> PlayableCardsAdvice:
    """
    Analyze playable cards for Riftbound 1v1 with proper resource and battlefield rules.
    """
    
    if not hand:
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            summary="No cards in hand to play."
        )
    
    # ✅ Validate exactly 2 battlefields
    if len(battlefields) != 2:
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            summary=f"Error: Expected 2 battlefields for 1v1, got {len(battlefields)}"
        )
    
    # Filter playable cards based on resources
    playable = _filter_playable_cards(hand, my_energy, my_power)
    
    if not playable:
        power_summary = ", ".join([f"{v} {k}" for k, v in my_power.items()]) if my_power else "0"
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            summary=f"No playable cards with {my_energy} energy and {power_summary} power."
        )
    
    # ✅ Analyze game state IN CORRECT ORDER
    game_phase = _determine_game_phase(turn)
    battlefield_analysis = _analyze_riftbound_battlefields(battlefields)  # ✅ Define first
    threat_level = _assess_threat_level(battlefield_analysis, opponent_health, my_health)  # ✅ Then use
    
    # Categorize playable cards
    playable_units = [c for c in playable if c.card_type == CardType.UNIT]
    playable_spells = [c for c in playable if c.card_type == CardType.SPELL]
    playable_gear = [c for c in playable if c.card_type == CardType.GEAR]
    
    # ✅ Calculate card values with correct signature (4 params)
    card_values = {
        card.card_id: _calculate_card_value(card, turn, battlefield_analysis, my_legend)
        for card in playable
    }
    
    # Generate recommendations
    recommendations: List[PlayableCardRecommendation] = []
    recommended_ids: List[str] = []
    priority = 1
    
    # ✅ Use the sophisticated helper functions
    # Strategy 1: Fill empty battlefields
    if battlefield_analysis['empty_battlefields'] > 0 and playable_units:
        priority = _recommend_battlefield_development(
            playable_units,
            battlefields,
            battlefield_analysis,
            card_values,
            recommendations,
            recommended_ids,
            priority,
            game_phase
        )
    
    # Strategy 2: Contest opponent-controlled battlefields
    if battlefield_analysis['opponent_only_battlefields'] > 0 and playable_units:
        priority = _recommend_contested_plays(
            playable_units,
            battlefields,
            battlefield_analysis,
            card_values,
            recommendations,
            recommended_ids,
            priority
        )
    
    # Strategy 3: Removal spells
    if battlefield_analysis['opponent_units'] > 0 and playable_spells:
        priority = _recommend_removal_spells(
            playable_spells,
            threat_level,
            card_values,
            recommendations,
            recommended_ids,
            priority
        )
    
    # Strategy 4: Gear
    if battlefield_analysis['my_units'] > 0 and playable_gear:
        priority = _recommend_gear(
            playable_gear,
            battlefield_analysis,
            card_values,
            recommendations,
            recommended_ids,
            priority
        )
    
    # Strategy 5: Utility spells
    if playable_spells:
        priority = _recommend_utility_spells(
            playable_spells,
            phase,
            battlefield_analysis,
            card_values,
            recommendations,
            recommended_ids,
            priority
        )
    
    # Add remaining playable cards as lower priority
    for card in playable:
        if card.card_id not in recommended_ids:
            reason = _get_low_priority_reason(card, game_phase, battlefield_analysis)  # ✅ Use helper
            
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
    
    # Sort by priority
    recommendations.sort(key=lambda r: r.priority)
    
    # Calculate resource efficiency
    recommended_energy = sum(c.energy_cost for c in playable if c.card_id in recommended_ids)
    efficiency_score = recommended_energy / my_energy if my_energy > 0 else 0.0
    
    efficiency_pct = (recommended_energy / my_energy * 100) if my_energy > 0 else 0
    mana_note = f"Recommended plays use {recommended_energy}/{my_energy} energy ({efficiency_pct:.0f}%)"
    
    if efficiency_score >= 0.9:
        mana_note += " - efficient resource usage"
    elif efficiency_score < 0.5:
        mana_note += " - consider additional plays or hold for better timing"
    
    # ✅ Use comprehensive summary builder
    summary = _build_strategy_summary(
        turn,
        game_phase,
        phase,
        len(recommended_ids),
        len(playable),
        battlefield_analysis,
        threat_level,
        my_health,
        opponent_health
    )
    
    # Debug info
    scoring_debug = ScoringDebugInfo(
        card_value_scores=card_values,
        threat_assessment={"level": threat_level, "details": battlefield_analysis},
        mana_efficiency_score=efficiency_score,
        battlefield_analyses=[bf.model_dump() for bf in battlefields],
        game_phase=game_phase
    )
    
    return PlayableCardsAdvice(
        playable_cards=recommendations,
        recommended_plays=recommended_ids,
        summary=summary,
        mana_efficiency_note=mana_note,
        scoring_debug=scoring_debug
    )
