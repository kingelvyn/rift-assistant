# playable_cards_advisor.py

from typing import List, Optional, Dict, Tuple, Set
from dataclasses import dataclass
from card_evaluation import assess_threat_level
from game_state import CardInHand, CardType, Rune, Phase
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


@dataclass
class PlaySequenceStep:
    """Represents a single step in a play sequence."""
    card_id: str
    card_name: str
    step_number: int
    energy_cost: int
    cumulative_energy: int
    reason: str
    dependencies: List[str] = None  # Card IDs that should be played before this
    battlefield_target: Optional[int] = None


@dataclass
class PlaySequence:
    """A complete sequence of plays in optimal order."""
    steps: List[PlaySequenceStep]
    total_energy: int
    sequence_reasoning: str
    efficiency_score: float
    risk_level: str  # "safe", "moderate", "aggressive"


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
        
        # Check power cost (for power-based cards)
        if card.power_cost and card.power_cost > 0:
            # Check if we have specific rune requirements
            if card.power_cost_by_rune:
                can_afford = True
                for rune, cost in card.power_cost_by_rune.items():
                    rune_key = rune.value if hasattr(rune, 'value') else str(rune)
                    available = my_power.get(rune_key.lower(), 0)
                    if cost > available:
                        can_afford = False
                        break
                if not can_afford:
                    continue
            else:
                # Generic power cost - check if domain power is available
                if card.domain and card.domain != Rune.COLORLESS:
                    domain_str = card.domain.value if hasattr(card.domain, 'value') else str(card.domain)
                    available_power = my_power.get(domain_str.lower(), 0)
                    if card.power_cost > available_power:
                        continue
        
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


def _identify_card_dependencies(
    card: CardInHand,
    hand: List[CardInHand],
    battlefields: List[BattlefieldState]
) -> List[str]:
    """
    Identify which other cards should be played before this one.
    Returns list of card IDs that are dependencies.
    """
    dependencies = []
    
    # GEAR dependencies: need a unit on board first
    if card.card_type == CardType.GEAR:
        # Check if we have units on board
        has_unit_on_board = any(
            bf.my_unit is not None 
            for bf in battlefields
        )
        
        if not has_unit_on_board:
            # Look for units in hand we should play first
            unit_cards = [
                c for c in hand 
                if c.card_type == CardType.UNIT and c.card_id != card.card_id
            ]
            if unit_cards:
                # Prefer cheap units as dependencies
                cheapest = min(unit_cards, key=lambda c: c.energy_cost)
                dependencies.append(cheapest.card_id)
    
    # BUFF SPELL dependencies: need target on board
    if card.card_type == CardType.SPELL:
        tags_lower = [t.lower() for t in (card.tags or [])]
        
        if 'buff' in tags_lower or 'enchant' in tags_lower:
            # Check if we have units on board
            has_unit_on_board = any(
                bf.my_unit is not None 
                for bf in battlefields
            )
            
            if not has_unit_on_board:
                # Look for units in hand
                unit_cards = [
                    c for c in hand 
                    if c.card_type == CardType.UNIT
                ]
                if unit_cards:
                    # Prefer units with good stats or keywords
                    best_target = max(
                        unit_cards, 
                        key=lambda c: (c.might or 0) + len(c.keywords or [])
                    )
                    dependencies.append(best_target.card_id)
    
    # COMBO dependencies: check rules text for card name references
    if card.rules_text:
        rules_lower = card.rules_text.lower()
        for other_card in hand:
            if other_card.card_id == card.card_id:
                continue
            
            # If this card mentions another card by name
            if other_card.name and other_card.name.lower() in rules_lower:
                dependencies.append(other_card.card_id)
    
    return dependencies

def _calculate_play_priority(
    card: CardInHand,
    card_values: Dict[str, float],
    battlefield_analysis: dict,
    game_phase: str,
    threat_level: str,
    current_phase: str
) -> float:
    """
    Calculate priority score for playing a card.
    Higher score = higher priority to play.
    """
    priority = 0.0
    
    # Base value from card evaluation
    priority += card_values.get(card.card_id, 0.0)
    
    # === SITUATIONAL PRIORITY MODIFIERS ===
    
    # Empty battlefields need filling urgently
    if card.card_type == CardType.UNIT:
        if battlefield_analysis['empty_battlefields'] > 0:
            priority += 15
        
        # Guard units are high priority when opponent threatens
        if 'guard' in [k.lower() for k in (card.keywords or [])]:
            if threat_level in ['high', 'critical']:
                priority += 10
        
        # Assault units are high priority in early game
        if 'assault' in [k.lower() for k in (card.keywords or [])]:
            if game_phase == 'early':
                priority += 8
    
    # Removal spells are urgent when threatened
    if card.card_type == CardType.SPELL:
        tags_lower = [t.lower() for t in (card.tags or [])]
        
        if any(t in tags_lower for t in ['removal', 'destroy', 'damage']):
            if threat_level == 'critical':
                priority += 20
            elif threat_level == 'high':
                priority += 12
            elif battlefield_analysis['opponent_units'] > 0:
                priority += 5
        
        # Fast spells (combat tricks) should be held
        if 'fast' in [k.lower() for k in (card.keywords or [])]:
            if current_phase == Phase.MAIN:
                priority -= 10  # Hold for showdown phase
        
        # Draw spells are lower priority in main phase
        if 'draw' in tags_lower:
            if current_phase == Phase.MAIN:
                priority += 3  # Okay to play but not urgent
    
    # Gear needs units
    if card.card_type == CardType.GEAR:
        if battlefield_analysis['my_units'] > 0:
            priority += 8
            # Better gear on contested battlefields
            if battlefield_analysis['contested_battlefields'] > 0:
                priority += 5
        else:
            priority -= 10  # Very low priority without units
    
    # === EFFICIENCY MODIFIERS ===
    
    # Cheap cards are easier to sequence
    if card.energy_cost <= 2:
        priority += 3
    
    # Expensive cards in early game are risky
    if game_phase == 'early' and card.energy_cost >= 4:
        priority -= 5
    
    return priority


def _build_optimal_sequence(
    cards: List[CardInHand],
    card_values: Dict[str, float],
    battlefield_analysis: dict,
    game_phase: str,
    threat_level: str,
    current_phase: str,
    my_energy: int,
    battlefields: List[BattlefieldState]
) -> PlaySequence:
    """
    Build an optimal play sequence considering dependencies and priorities.
    """
    # Calculate priorities for all cards
    card_priorities = {}
    card_dependencies = {}
    
    for card in cards:
        priority = _calculate_play_priority(
            card, card_values, battlefield_analysis, 
            game_phase, threat_level, current_phase
        )
        card_priorities[card.card_id] = priority
        
        deps = _identify_card_dependencies(card, cards, battlefields)
        card_dependencies[card.card_id] = deps
    
    # Build sequence using topological sort (respecting dependencies)
    sequence_steps = []
    played_cards: Set[str] = set()
    cumulative_energy = 0
    step_number = 1
    
    # Sort cards by priority (highest first)
    sorted_cards = sorted(
        cards, 
        key=lambda c: card_priorities[c.card_id], 
        reverse=True
    )
    
    # Iteratively add cards that have their dependencies met
    while sorted_cards and cumulative_energy < my_energy:
        cards_added_this_iteration = False
        
        for card in sorted_cards[:]:  # Iterate over copy
            # Check if we can afford this card
            if cumulative_energy + card.energy_cost > my_energy:
                continue
            
            # Check if dependencies are satisfied
            deps = card_dependencies[card.card_id]
            if all(dep_id in played_cards for dep_id in deps):
                # Add this card to sequence
                cumulative_energy += card.energy_cost
                
                # Determine battlefield target
                battlefield_target = None
                if card.card_type == CardType.UNIT:
                    # Find best battlefield for this unit
                    battlefield_target = _select_battlefield_for_unit(
                        card, battlefields, battlefield_analysis
                    )
                
                # Generate reason
                reason = _generate_step_reason(
                    card, deps, step_number, 
                    battlefield_analysis, threat_level
                )
                
                step = PlaySequenceStep(
                    card_id=card.card_id,
                    card_name=card.name or card.card_id,
                    step_number=step_number,
                    energy_cost=card.energy_cost,
                    cumulative_energy=cumulative_energy,
                    reason=reason,
                    dependencies=deps,
                    battlefield_target=battlefield_target
                )
                
                sequence_steps.append(step)
                played_cards.add(card.card_id)
                sorted_cards.remove(card)
                step_number += 1
                cards_added_this_iteration = True
                break
        
        # If we couldn't add any cards this iteration, break
        if not cards_added_this_iteration:
            break
    
    # Calculate efficiency and risk
    efficiency_score = cumulative_energy / my_energy if my_energy > 0 else 0.0
    risk_level = _assess_sequence_risk(sequence_steps, efficiency_score, game_phase)
    
    # Generate sequence reasoning
    sequence_reasoning = _generate_sequence_reasoning(
        sequence_steps, efficiency_score, risk_level, 
        battlefield_analysis, threat_level
    )
    
    return PlaySequence(
        steps=sequence_steps,
        total_energy=cumulative_energy,
        sequence_reasoning=sequence_reasoning,
        efficiency_score=efficiency_score,
        risk_level=risk_level
    )


def _select_battlefield_for_unit(
    unit: CardInHand,
    battlefields: List[BattlefieldState],
    battlefield_analysis: dict
) -> Optional[int]:
    """Select the best battlefield index to play a unit."""
    
    unit_might = unit.might or 0
    best_battlefield = None
    best_score = -999
    
    for idx, bf in enumerate(battlefields):
        # Can't play if we already have a unit there
        if bf.my_unit is not None:
            continue
        
        score = 0
        
        # Empty battlefield is always an option
        if bf.opponent_unit is None:
            score = 10
        else:
            # Contested battlefield
            op_might = bf.opponent_unit.get('might', 0)
            
            if unit_might > op_might:
                score = 20  # We win this battlefield
            elif unit_might == op_might:
                score = 15  # We contest it
            else:
                score = 5   # We're behind, but at least contesting
        
        # Prefer guard units on threatened lanes
        if 'guard' in [k.lower() for k in (unit.keywords or [])]:
            if bf.opponent_unit is not None:
                score += 5
        
        # Prefer assault units on empty lanes
        if 'assault' in [k.lower() for k in (unit.keywords or [])]:
            if bf.opponent_unit is None:
                score += 3
        
        if score > best_score:
            best_score = score
            best_battlefield = idx
    
    return best_battlefield


def _generate_step_reason(
    card: CardInHand,
    dependencies: List[str],
    step_number: int,
    battlefield_analysis: dict,
    threat_level: str
) -> str:
    """Generate human-readable reason for this play step."""
    
    if dependencies:
        return f"Step {step_number}: Play after dependencies met"
    
    if card.card_type == CardType.UNIT:
        if battlefield_analysis['empty_battlefields'] > 0:
            return f"Step {step_number}: Develop board presence"
        elif battlefield_analysis['opponent_only_battlefields'] > 0:
            return f"Step {step_number}: Contest opponent's battlefield"
        else:
            return f"Step {step_number}: Strengthen battlefield position"
    
    if card.card_type == CardType.SPELL:
        tags_lower = [t.lower() for t in (card.tags or [])]
        if any(t in tags_lower for t in ['removal', 'destroy']):
            return f"Step {step_number}: Remove opponent threat ({threat_level} priority)"
        elif 'buff' in tags_lower:
            return f"Step {step_number}: Enhance existing unit"
        elif 'draw' in tags_lower:
            return f"Step {step_number}: Refill resources"
        else:
            return f"Step {step_number}: Cast utility spell"
    
    if card.card_type == CardType.GEAR:
        return f"Step {step_number}: Equip gear to strengthen unit"
    
    return f"Step {step_number}: Play card"


def _assess_sequence_risk(
    steps: List[PlaySequenceStep],
    efficiency: float,
    game_phase: str
) -> str:
    """Assess the risk level of this play sequence."""
    
    if efficiency >= 0.9:
        # Using almost all resources
        if game_phase == 'early':
            return "moderate"  # It's okay to go all-in early
        else:
            return "aggressive"  # Risky to have no resources left
    
    if efficiency >= 0.7:
        return "moderate"
    
    if efficiency < 0.5:
        return "safe"  # Very conservative
    
    return "safe"


def _generate_sequence_reasoning(
    steps: List[PlaySequenceStep],
    efficiency: float,
    risk_level: str,
    battlefield_analysis: dict,
    threat_level: str
) -> str:
    """Generate reasoning explanation for the sequence."""
    
    parts = []
    
    # Efficiency description
    if efficiency >= 0.9:
        parts.append(f"Uses {efficiency*100:.0f}% of available energy")
    elif efficiency >= 0.7:
        parts.append(f"Efficient {efficiency*100:.0f}% energy usage")
    else:
        parts.append(f"Conservative {efficiency*100:.0f}% energy usage")
    
    # Sequence structure
    if len(steps) == 1:
        parts.append("single high-impact play")
    elif len(steps) == 2:
        parts.append("two-step sequence")
    else:
        parts.append(f"{len(steps)}-card sequence")
    
    # Dependency-aware
    has_deps = any(step.dependencies for step in steps)
    if has_deps:
        parts.append("respects card dependencies")
    
    # Threat response
    if threat_level in ['high', 'critical']:
        parts.append(f"addresses {threat_level} threat level")
    
    # Board development
    unit_steps = sum(1 for s in steps if s.battlefield_target is not None)
    if unit_steps > 0:
        parts.append(f"develops {unit_steps} battlefield(s)")
    
    # Risk assessment
    if risk_level == "aggressive":
        parts.append("⚠️ commits all resources")
    elif risk_level == "safe":
        parts.append("✓ keeps options open")
    
    return " - ".join(parts) + "."


def _generate_alternative_sequences(
    cards: List[CardInHand],
    card_values: Dict[str, float],
    battlefield_analysis: dict,
    game_phase: str,
    threat_level: str,
    current_phase: str,
    my_energy: int,
    battlefields: List[BattlefieldState],
    primary_sequence: PlaySequence
) -> List[PlaySequence]:
    """Generate alternative play sequences with different strategies."""
    
    alternatives = []
    
    # Alternative 1: Most conservative (minimum commitment)
    cheap_cards = [c for c in cards if c.energy_cost <= 2]
    if cheap_cards:
        conservative_seq = _build_optimal_sequence(
            cheap_cards[:1],  # Just one cheap card
            card_values,
            battlefield_analysis,
            game_phase,
            threat_level,
            current_phase,
            my_energy,
            battlefields
        )
        if conservative_seq.steps and conservative_seq.total_energy != primary_sequence.total_energy:
            alternatives.append(conservative_seq)
    
    # Alternative 2: Board control focus (units only)
    unit_cards = [c for c in cards if c.card_type == CardType.UNIT]
    if len(unit_cards) >= 2:
        units_seq = _build_optimal_sequence(
            unit_cards,
            card_values,
            battlefield_analysis,
            game_phase,
            threat_level,
            current_phase,
            my_energy,
            battlefields
        )
        if units_seq.steps and units_seq.total_energy != primary_sequence.total_energy:
            alternatives.append(units_seq)
    
    # Alternative 3: Single big play (most expensive card)
    expensive_cards = sorted(cards, key=lambda c: c.energy_cost, reverse=True)
    if expensive_cards and expensive_cards[0].energy_cost >= 3:
        big_play_seq = _build_optimal_sequence(
            [expensive_cards[0]],
            card_values,
            battlefield_analysis,
            game_phase,
            threat_level,
            current_phase,
            my_energy,
            battlefields
        )
        if big_play_seq.steps and big_play_seq.total_energy != primary_sequence.total_energy:
            alternatives.append(big_play_seq)
    
    return alternatives


def _convert_sequence_to_strategy(
    sequence: PlaySequence,
    strategy_name: str,
    priority: int
) -> PlayStrategy:
    """Convert a PlaySequence to a PlayStrategy."""
    
    card_ids = [step.card_id for step in sequence.steps]
    
    return PlayStrategy(
        strategy_name=strategy_name,
        card_ids=card_ids,
        total_energy=sequence.total_energy,
        reasoning=sequence.sequence_reasoning,
        priority=priority
    )


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
        # Might per energy is key metric (but with diminishing returns)
        efficiency = card.might / max(card.energy_cost, 1)
        value += efficiency * 10
        
        # Bonus for absolute might
        value += card.might * 0.5
    
    # Keyword bonuses
    if card.keywords:
        keyword_values = {
            "assault": 4,      # Extra damage pressure
            "guard": 3,        # Protects other units
            "flying": 3,       # Hard to block
            "ambush": 2,       # Surprise factor
            "overwhelm": 4,    # Damage through
            "lifesteal": 2,    # Sustain
            "quick": 3,        # Can attack immediately
            "double strike": 5, # Very powerful
        }
        for keyword in card.keywords:
            value += keyword_values.get(keyword.lower(), 1)
    
    # Context bonuses
    game_phase = _determine_game_phase(turn)
    
    if game_phase == "early":
        if card.energy_cost <= 2:
            value += 5  # Early game highly values cheap cards
        elif card.energy_cost >= 4:
            value -= 3  # Expensive cards are harder to use
    
    if game_phase == "late":
        if card.card_type == CardType.UNIT and (card.might or 0) >= 5:
            value += 4  # Late game values bombs
    
    # Removal is valuable when opponent has units
    if card.card_type == CardType.SPELL:
        tags_lower = [t.lower() for t in (card.tags or [])]
        
        if any(t in tags_lower for t in ['removal', 'destroy', 'damage']):
            value += battlefield_analysis['opponent_units'] * 3
            
            # Critical against high might units
            if battlefield_analysis.get('highest_opponent_might', 0) >= 4:
                value += 3
        
        # Draw spells
        if 'draw' in tags_lower:
            value += 2
            # More valuable in late game
            if game_phase == "late":
                value += 2
    
    # Gear is valuable when we have units
    if card.card_type == CardType.GEAR:
        value += battlefield_analysis['my_units'] * 2
        
        # More valuable in contested battlefields
        if battlefield_analysis['contested_battlefields'] > 0:
            value += 3
    
    return max(value, 0.0)


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
    my_score: Optional[int] = None,
    opponent_score: Optional[int] = None,
) -> PlayableCardsAdvice:
    """
    Analyze playable cards for Riftbound 1v1 with optimal sequencing.
    """
    
    if not hand:
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            recommended_strategies=[],
            primary_strategy=[],
            summary="No cards in hand to play.",
            mana_efficiency_note=None,
            scoring_debug=None,
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
            recommended_strategies=[],
            primary_strategy=[],
            summary=f"No playable cards with {my_energy} energy and {power_summary} power.",
            mana_efficiency_note=None,
            scoring_debug=None,
        )
    
    # Analyze game state
    game_phase = _determine_game_phase(turn)
    battlefield_analysis = analyze_riftbound_battlefields(battlefields)
    
    # Add highest might tracking
    battlefield_analysis['highest_opponent_might'] = max(
        (bf.opponent_unit.get('might', 0) 
         for bf in battlefields 
         if bf.opponent_unit), 
        default=0
    )
    
    threat_level = assess_battlefield_threat_level(
        battlefield_analysis, opponent_score, my_score
    )
    
    # Calculate card values
    card_values = {
        card.card_id: _calculate_card_value(card, turn, battlefield_analysis, my_legend)
        for card in playable
    }
    
    # Build optimal play sequence
    primary_sequence = _build_optimal_sequence(
        playable,
        card_values,
        battlefield_analysis,
        game_phase,
        threat_level,
        phase,
        my_energy,
        battlefields
    )
    
    # Generate alternative sequences
    alternative_sequences = _generate_alternative_sequences(
        playable,
        card_values,
        battlefield_analysis,
        game_phase,
        threat_level,
        phase,
        my_energy,
        battlefields,
        primary_sequence
    )
    
    # Convert sequences to strategies
    strategies = []
    
    # Primary strategy (optimal sequence)
    strategies.append(_convert_sequence_to_strategy(
        primary_sequence,
        "Optimal Sequence",
        priority=1
    ))
    
    # Alternative strategies
    for idx, alt_seq in enumerate(alternative_sequences):
        strategy_names = [
            "Conservative Play",
            "Board Control Focus",
            "Single Big Play"
        ]
        strategy_name = strategy_names[idx] if idx < len(strategy_names) else f"Alternative {idx+1}"
        
        strategies.append(_convert_sequence_to_strategy(
            alt_seq,
            strategy_name,
            priority=idx + 2
        ))
    
    # Build recommendations list with sequence information
    recommendations = []
    
    for step in primary_sequence.steps:
        card = next(c for c in playable if c.card_id == step.card_id)
        
        battlefield_placement = None
        if step.battlefield_target is not None:
            battlefield_placement = BattlefieldPlacement(
                battlefield_index=step.battlefield_target,
                reason=f"Best battlefield for this unit",
                priority=1
            )
        
        recommendations.append(
            PlayableCardRecommendation(
                card_id=card.card_id,
                name=card.name,
                card_type=card.card_type,
                energy_cost=card.energy_cost,
                priority=step.step_number,
                recommended=True,
                reason=step.reason,
                battlefield_placement=battlefield_placement,
                value_score=card_values.get(card.card_id, 0.0)
            )
        )
    
    # Add non-sequenced cards as lower priority
    sequenced_ids = {step.card_id for step in primary_sequence.steps}
    for card in playable:
        if card.card_id not in sequenced_ids:
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=card.card_id,
                    name=card.name,
                    card_type=card.card_type,
                    energy_cost=card.energy_cost,
                    priority=len(primary_sequence.steps) + 10,
                    recommended=False,
                    reason="Not included in optimal sequence - lower value or doesn't fit energy curve",
                    value_score=card_values.get(card.card_id, 0.0)
                )
            )
    
    # Primary strategy card IDs
    primary_strategy_ids = [step.card_id for step in primary_sequence.steps]
    
    # Efficiency note
    efficiency_pct = primary_sequence.efficiency_score * 100
    mana_note = f"Optimal sequence uses {primary_sequence.total_energy}/{my_energy} energy ({efficiency_pct:.0f}%)"
    
    if primary_sequence.efficiency_score >= 0.9:
        mana_note += " - maximum efficiency"
    elif primary_sequence.efficiency_score >= 0.7:
        mana_note += " - balanced efficiency"
    else:
        mana_note += " - conservative, holds resources"
    
    if len(strategies) > 1:
        mana_note += f". {len(strategies)} strategies available."
    
    # Summary
    summary = build_strategy_summary(
        turn,
        game_phase,
        phase,
        len(primary_strategy_ids),
        len(playable),
        battlefield_analysis,
        threat_level,
        my_score,
        opponent_score,
    )
    
    # Add sequence info to summary
    if len(primary_sequence.steps) > 1:
        summary += f" Sequence: {len(primary_sequence.steps)} steps."
    
    # Debug info
    scoring_debug = ScoringDebugInfo(
        card_value_scores=card_values,
        threat_assessment={
            "level": threat_level, 
            "details": battlefield_analysis
        },
        mana_efficiency_score=primary_sequence.efficiency_score,
        battlefield_analyses=[bf.model_dump() for bf in battlefields],
        game_phase=game_phase
    )
    
    return PlayableCardsAdvice(
        playable_cards=recommendations,
        recommended_strategies=strategies,
        primary_strategy=primary_strategy_ids,
        recommended_plays=primary_strategy_ids,
        summary=summary,
        mana_efficiency_note=mana_note,
        scoring_debug=scoring_debug,
    )


# older logic functs

def _recommend_battlefield_development_legacy(
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


def _recommend_contested_plays_legacy(
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


def _recommend_removal_spells_legacy(
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


def _recommend_gear_legacy(
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


def _recommend_utility_spells_legacy(
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


def _get_low_priority_reason_legacy(
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
 

def _generate_play_strategies_legacy(
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


def _adjust_recommendations_for_resources_legacy(
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
