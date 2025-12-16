# advisor.py (or create playable_cards_advisor.py)

from typing import List, Optional, Dict
from card_evaluation import assess_threat_level
from game_state import CardInHand, CardType, Rune
from card_db import CardRecord
from advisor_models import (
    PlayableCardsAdvice,
    PlayableCardRecommendation,
    ScoringDebugInfo,
    BattlefieldPlacement,
    BattlefieldState,
    PlayStrategy,
)

from battlefield_analysis import (
    analyze_riftbound_battlefields,
    find_best_battlefield,
    assess_battlefield_threat_level,
    build_strategy_summary,
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
 

def _generate_play_strategies(
    recommendations: List[PlayableCardRecommendation],
    my_energy: int,
    game_phase: str,
    battlefield_analysis: dict
) -> tuple[List[PlayStrategy], List[str]]:
    """
    Generate multiple viable play strategies.
    
    Returns:
        (strategies, primary_strategy_card_ids)
    """
    strategies = []
    
    # Get recommended cards sorted by priority
    recommended_cards = [
        r for r in recommendations 
        if r.recommended
    ]
    recommended_cards.sort(key=lambda r: r.priority)
    
    if not recommended_cards:
        return [], []
    
    # Strategy 1: GREEDY/TEMPO - Use as much energy as possible
    greedy_cards = []
    greedy_energy = 0
    for card in recommended_cards:
        if greedy_energy + card.energy_cost <= my_energy:
            greedy_cards.append(card.card_id)
            greedy_energy += card.energy_cost
    
    if greedy_cards:
        efficiency = (greedy_energy / my_energy * 100) if my_energy > 0 else 0
        strategies.append(PlayStrategy(
            strategy_name="Tempo Play",
            card_ids=greedy_cards,
            total_energy=greedy_energy,
            reasoning=f"Maximize energy usage ({greedy_energy}/{my_energy} energy, {efficiency:.0f}%). Best for maintaining tempo.",
            priority=1
        ))
    
    # Strategy 2: VALUE - Play only highest priority cards
    if len(recommended_cards) >= 2:
        # Take top priority cards that fit
        value_cards = []
        value_energy = 0
        
        for card in recommended_cards[:3]:  # Top 3 by priority
            if value_energy + card.energy_cost <= my_energy:
                value_cards.append(card.card_id)
                value_energy += card.energy_cost
        
        # Only add if different from greedy
        if set(value_cards) != set(greedy_cards):
            strategies.append(PlayStrategy(
                strategy_name="Value Play",
                card_ids=value_cards,
                total_energy=value_energy,
                reasoning=f"Focus on highest value cards ({value_energy}/{my_energy} energy). Better long-term positioning.",
                priority=2
            ))
    
    # Strategy 3: SINGLE BIG PLAY - Play one expensive high-impact card
    expensive_cards = [c for c in recommended_cards if c.energy_cost >= 3]
    if expensive_cards and len(greedy_cards) > 1:
        big_card = expensive_cards[0]
        if big_card.energy_cost <= my_energy:
            strategies.append(PlayStrategy(
                strategy_name="Big Play",
                card_ids=[big_card.card_id],
                total_energy=big_card.energy_cost,
                reasoning=f"Single high-impact play. Saves energy for reaction spells or future turns.",
                priority=3
            ))
    
    # Strategy 4: CONSERVATIVE - Play only cheapest cards, save energy
    if game_phase in ["early", "mid"]:
        cheap_cards = [c for c in recommended_cards if c.energy_cost <= 2]
        if cheap_cards and len(cheap_cards) < len(greedy_cards):
            conservative_cards = []
            conservative_energy = 0
            for card in cheap_cards[:2]:  # Up to 2 cheap cards
                if conservative_energy + card.energy_cost <= my_energy:
                    conservative_cards.append(card.card_id)
                    conservative_energy += card.energy_cost
            
            if conservative_cards and set(conservative_cards) != set(greedy_cards):
                strategies.append(PlayStrategy(
                    strategy_name="Conservative",
                    card_ids=conservative_cards,
                    total_energy=conservative_energy,
                    reasoning=f"Minimal commitment ({conservative_energy}/{my_energy} energy). Keeps options open for opponent's plays.",
                    priority=4
                ))
    
    # Strategy 5: BOARD CONTROL - Prioritize units over spells
    units_only = [c for c in recommended_cards if c.card_type == CardType.UNIT]
    if len(units_only) >= 2 and battlefield_analysis['empty_battlefields'] > 0:
        control_cards = []
        control_energy = 0
        for card in units_only[:2]:
            if control_energy + card.energy_cost <= my_energy:
                control_cards.append(card.card_id)
                control_energy += card.energy_cost
        
        if control_cards and set(control_cards) != set(greedy_cards):
            strategies.append(PlayStrategy(
                strategy_name="Board Control",
                card_ids=control_cards,
                total_energy=control_energy,
                reasoning=f"Focus on board presence ({control_energy}/{my_energy} energy). Establish battlefield dominance.",
                priority=2
            ))
    
    # Sort strategies by priority
    strategies.sort(key=lambda s: s.priority)
    
    # Primary strategy is the first one (highest priority)
    primary_card_ids = strategies[0].card_ids if strategies else []
    
    return strategies, primary_card_ids


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
    
    # Validate exactly 2 battlefields
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
    
    # Analyze game state IN CORRECT ORDER
    game_phase = _determine_game_phase(turn)
    battlefield_analysis = analyze_riftbound_battlefields(battlefields)  
    threat_level = assess_battlefield_threat_level(battlefield_analysis, opponent_health, my_health)  
    
    # Categorize playable cards
    playable_units = [c for c in playable if c.card_type == CardType.UNIT]
    playable_spells = [c for c in playable if c.card_type == CardType.SPELL]
    playable_gear = [c for c in playable if c.card_type == CardType.GEAR]
    
    card_values = {
        card.card_id: _calculate_card_value(card, turn, battlefield_analysis, my_legend)
        for card in playable
    }
    
    # Generate recommendations
    recommendations: List[PlayableCardRecommendation] = []
    recommended_ids: List[str] = []
    priority = 1
    
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
            reason = _get_low_priority_reason(card, game_phase, battlefield_analysis) 
            
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
    
    # ✅ Generate multiple play strategies
    strategies, primary_strategy_ids = _generate_play_strategies(
        recommendations,
        my_energy,
        game_phase,
        battlefield_analysis
    )

    # Calculate efficiency based on primary strategy
    if primary_strategy_ids:
        primary_strategy = next(s for s in strategies if s.card_ids == primary_strategy_ids)
        recommended_energy = primary_strategy.total_energy
    else:
        recommended_energy = 0

    efficiency_score = recommended_energy / my_energy if my_energy > 0 else 0.0

    efficiency_pct = (recommended_energy / my_energy * 100) if my_energy > 0 else 0
    mana_note = f"Primary strategy uses {recommended_energy}/{my_energy} energy ({efficiency_pct:.0f}%)"

    if efficiency_score >= 0.9:
        mana_note += " - efficient resource usage"
    elif efficiency_score < 0.5:
        mana_note += " - conservative play, holding resources"

    if len(strategies) > 1:
        mana_note += f". {len(strategies)} alternative strategies available."

    # Use comprehensive summary builder
    summary = build_strategy_summary(
        turn,
        game_phase,
        phase,
        len(primary_strategy_ids),
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
        recommended_strategies=strategies,  # ✅ Multiple strategies
        primary_strategy=primary_strategy_ids,  # ✅ Best strategy
        recommended_plays=primary_strategy_ids,
        summary=summary,
        mana_efficiency_note=mana_note,
        scoring_debug=scoring_debug
    )


def _adjust_recommendations_for_resources(
    recommendations: List[PlayableCardRecommendation],
    recommended_ids: List[str],
    my_energy: int
) -> tuple[List[str], int]:
    """
    Adjust recommendations to only include cards that can be played together.
    Returns (adjusted_recommended_ids, total_energy_used)
    """
    # Get all recommended cards sorted by priority
    recommended_cards = [
        r for r in recommendations 
        if r.card_id in recommended_ids and r.recommended
    ]
    recommended_cards.sort(key=lambda r: r.priority)
    
    # Greedily select cards that fit within energy budget
    adjusted_ids = []
    energy_used = 0
    
    for card in recommended_cards:
        if energy_used + card.energy_cost <= my_energy:
            adjusted_ids.append(card.card_id)
            energy_used += card.energy_cost
        else:
            # Mark this card as not recommended due to resource constraints
            card.recommended = False
            card.reason += " (Not enough energy this turn - would need {} total)".format(
                energy_used + card.energy_cost
            )
    
    return adjusted_ids, energy_used
