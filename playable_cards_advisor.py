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

# Import improved legend analysis
from legend_analysis import (
    analyze_legend_synergy,
    evaluate_legend_state,
    format_legend_synergy_summary,
    can_exhaust_legend,
    requires_legend_exhaustion,
    LegendSynergyType,
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
    dependencies: List[str] = None
    battlefield_target: Optional[int] = None
    legend_synergies: List[str] = None  # NEW: Legend synergy descriptions


@dataclass
class PlaySequence:
    """A complete sequence of plays in optimal order."""
    steps: List[PlaySequenceStep]
    total_energy: int
    sequence_reasoning: str
    efficiency_score: float
    risk_level: str
    legend_integration: Optional[str] = None  # NEW: How legend fits into sequence


def _filter_playable_cards(
    hand: List[CardInHand],
    my_energy: int,
    my_power: Dict[str, int],
    player_state
) -> List[CardInHand]:
    """Filter cards that can actually be played with available resources."""
    playable = []
    
    for card in hand:
        # Check energy cost
        if card.energy_cost > my_energy:
            continue
        
        # NEW: Check legend exhaustion requirement
        if requires_legend_exhaustion(card):
            if not can_exhaust_legend(player_state):
                continue  # Can't play this card without ready legend
        
        # Check power cost
        if card.power_cost and card.power_cost > 0:
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
    battlefields: List[BattlefieldState],
    player_state,
    card_synergies: Dict[str, List]  # NEW: Pass in synergies
) -> List[str]:
    """
    Identify which other cards should be played before this one.
    Now includes legend-based dependencies.
    """
    dependencies = []
    
    # LEGEND EXHAUSTION dependency
    if requires_legend_exhaustion(card):
        if not can_exhaust_legend(player_state):
            # Look for cards that can ready the legend
            for other_card in hand:
                if other_card.card_id == card.card_id:
                    continue
                
                other_synergies = card_synergies.get(other_card.card_id, [])
                for synergy in other_synergies:
                    if synergy.synergy_type == LegendSynergyType.READY_EFFECT:
                        dependencies.append(other_card.card_id)
                        break
    
    # GEAR dependencies: need a unit on board first
    if card.card_type == CardType.GEAR:
        has_unit_on_board = any(
            bf.my_unit is not None 
            for bf in battlefields
        )
        
        if not has_unit_on_board:
            unit_cards = [
                c for c in hand 
                if c.card_type == CardType.UNIT and c.card_id != card.card_id
            ]
            if unit_cards:
                # Prefer units with legend synergies
                synergy_units = [
                    u for u in unit_cards
                    if card_synergies.get(u.card_id) and 
                    any(s.value_modifier > 0 for s in card_synergies[u.card_id])
                ]
                
                if synergy_units:
                    cheapest = min(synergy_units, key=lambda c: c.energy_cost)
                else:
                    cheapest = min(unit_cards, key=lambda c: c.energy_cost)
                dependencies.append(cheapest.card_id)
    
    # BUFF SPELL dependencies: need target on board
    if card.card_type == CardType.SPELL:
        tags_lower = [t.lower() for t in (card.tags or [])]
        
        if 'buff' in tags_lower or 'enchant' in tags_lower:
            has_unit_on_board = any(
                bf.my_unit is not None 
                for bf in battlefields
            )
            
            if not has_unit_on_board:
                unit_cards = [c for c in hand if c.card_type == CardType.UNIT]
                if unit_cards:
                    # Prefer units with highest stats or legend synergies
                    best_target = max(
                        unit_cards, 
                        key=lambda c: (
                            (c.might or 0) + 
                            len(c.keywords or []) +
                            sum(s.value_modifier for s in card_synergies.get(c.card_id, []))
                        )
                    )
                    dependencies.append(best_target.card_id)
    
    # COMBO dependencies: explicit card name references
    if card.rules_text:
        rules_lower = card.rules_text.lower()
        for other_card in hand:
            if other_card.card_id == card.card_id:
                continue
            
            if other_card.name and other_card.name.lower() in rules_lower:
                dependencies.append(other_card.card_id)
    
    return dependencies


def _calculate_play_priority(
    card: CardInHand,
    card_values: Dict[str, float],
    battlefield_analysis: dict,
    game_phase: str,
    threat_level: str,
    current_phase: str,
    legend_modifier: float  # NEW: Legend synergy value
) -> float:
    """
    Calculate priority score for playing a card.
    Now includes legend synergy bonuses.
    """
    priority = 0.0
    
    # Base value from card evaluation (already includes legend modifier)
    priority += card_values.get(card.card_id, 0.0)
    
    # Additional legend-specific priority boosts
    priority += legend_modifier * 2  # Amplify legend synergy impact on priority
    
    # === SITUATIONAL PRIORITY MODIFIERS ===
    
    # Empty battlefields need filling urgently
    if card.card_type == CardType.UNIT:
        if battlefield_analysis['empty_battlefields'] > 0:
            priority += 15
        
        if 'guard' in [k.lower() for k in (card.keywords or [])]:
            if threat_level in ['high', 'critical']:
                priority += 10
        
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
        
        # Fast spells should be held for showdown
        if 'fast' in [k.lower() for k in (card.keywords or [])]:
            if current_phase == Phase.MAIN:
                priority -= 10
        
        if 'draw' in tags_lower:
            if current_phase == Phase.MAIN:
                priority += 3
    
    # Gear needs units
    if card.card_type == CardType.GEAR:
        if battlefield_analysis['my_units'] > 0:
            priority += 8
            if battlefield_analysis['contested_battlefields'] > 0:
                priority += 5
        else:
            priority -= 10
    
    # === EFFICIENCY MODIFIERS ===
    
    if card.energy_cost <= 2:
        priority += 3
    
    if game_phase == 'early' and card.energy_cost >= 4:
        priority -= 5
    
    return priority


def _build_optimal_sequence(
    cards: List[CardInHand],
    card_values: Dict[str, float],
    card_synergies: Dict[str, List],  # NEW: Card legend synergies
    battlefield_analysis: dict,
    game_phase: str,
    threat_level: str,
    current_phase: str,
    my_energy: int,
    battlefields: List[BattlefieldState],
    player_state,
    opponent_state
) -> PlaySequence:
    """
    Build an optimal play sequence considering dependencies and legend synergies.
    """
    # Calculate priorities for all cards
    card_priorities = {}
    card_dependencies = {}
    
    for card in cards:
        # Get legend modifier for this card
        synergies = card_synergies.get(card.card_id, [])
        legend_modifier = sum(s.value_modifier for s in synergies)
        
        priority = _calculate_play_priority(
            card, card_values, battlefield_analysis, 
            game_phase, threat_level, current_phase,
            legend_modifier
        )
        card_priorities[card.card_id] = priority
        
        deps = _identify_card_dependencies(
            card, cards, battlefields, player_state, card_synergies
        )
        card_dependencies[card.card_id] = deps
    
    # Build sequence using topological sort
    sequence_steps = []
    played_cards: Set[str] = set()
    cumulative_energy = 0
    step_number = 1
    
    sorted_cards = sorted(
        cards, 
        key=lambda c: card_priorities[c.card_id], 
        reverse=True
    )
    
    # Track if we've used legend exhaustion
    legend_exhausted_in_sequence = player_state.legend and player_state.legend.exhausted
    
    while sorted_cards and cumulative_energy < my_energy:
        cards_added_this_iteration = False
        
        for card in sorted_cards[:]:
            # Check energy
            if cumulative_energy + card.energy_cost > my_energy:
                continue
            
            # Check legend exhaustion requirement
            if requires_legend_exhaustion(card):
                if legend_exhausted_in_sequence:
                    continue  # Can't play, legend already exhausted
            
            # Check dependencies
            deps = card_dependencies[card.card_id]
            if all(dep_id in played_cards for dep_id in deps):
                cumulative_energy += card.energy_cost
                
                # Mark legend as exhausted if this card uses it
                if requires_legend_exhaustion(card):
                    legend_exhausted_in_sequence = True
                
                # Determine battlefield target
                battlefield_target = None
                if card.card_type == CardType.UNIT:
                    battlefield_target = _select_battlefield_for_unit(
                        card, battlefields, battlefield_analysis
                    )
                
                # Get legend synergies for this card
                synergies = card_synergies.get(card.card_id, [])
                synergy_descriptions = [s.description for s in synergies if s.value_modifier > 0]
                
                # Generate reason
                reason = _generate_step_reason(
                    card, deps, step_number, 
                    battlefield_analysis, threat_level,
                    synergies  # NEW: Pass synergies
                )
                
                step = PlaySequenceStep(
                    card_id=card.card_id,
                    card_name=card.name or card.card_id,
                    step_number=step_number,
                    energy_cost=card.energy_cost,
                    cumulative_energy=cumulative_energy,
                    reason=reason,
                    dependencies=deps,
                    battlefield_target=battlefield_target,
                    legend_synergies=synergy_descriptions  # NEW
                )
                
                sequence_steps.append(step)
                played_cards.add(card.card_id)
                sorted_cards.remove(card)
                step_number += 1
                cards_added_this_iteration = True
                break
        
        if not cards_added_this_iteration:
            break
    
    # Calculate efficiency and risk
    efficiency_score = cumulative_energy / my_energy if my_energy > 0 else 0.0
    risk_level = _assess_sequence_risk(sequence_steps, efficiency_score, game_phase)
    
    # Generate legend integration note
    legend_integration = _assess_legend_integration(
        sequence_steps, card_synergies, player_state
    )
    
    # Generate sequence reasoning
    sequence_reasoning = _generate_sequence_reasoning(
        sequence_steps, efficiency_score, risk_level, 
        battlefield_analysis, threat_level,
        legend_integration  # NEW
    )
    
    return PlaySequence(
        steps=sequence_steps,
        total_energy=cumulative_energy,
        sequence_reasoning=sequence_reasoning,
        efficiency_score=efficiency_score,
        risk_level=risk_level,
        legend_integration=legend_integration  # NEW
    )


def _assess_legend_integration(
    steps: List[PlaySequenceStep],
    card_synergies: Dict[str, List],
    player_state
) -> Optional[str]:
    """Assess how well legend is integrated into the sequence."""
    
    if not player_state.legend:
        return None
    
    legend = player_state.legend
    
    # Count cards with legend synergies
    synergistic_cards = sum(
        1 for step in steps 
        if step.legend_synergies and len(step.legend_synergies) > 0
    )
    
    if synergistic_cards == 0:
        return None
    
    # Check if we're using legend exhaustion
    uses_exhaustion = any(
        any(s.synergy_type == LegendSynergyType.EXHAUSTION_COST 
            for s in card_synergies.get(step.card_id, []))
        for step in steps
    )
    
    parts = []
    
    if synergistic_cards == 1:
        parts.append(f"1 card synergizes with {legend.name or 'legend'}")
    else:
        parts.append(f"{synergistic_cards} cards synergize with {legend.name or 'legend'}")
    
    if uses_exhaustion:
        parts.append("includes legend exhaustion")
    
    if legend.exhausted:
        parts.append("(legend currently exhausted)")
    elif not legend.exhausted and legend.activated_abilities:
        parts.append(f"({len(legend.activated_abilities)} legend ability available)")
    
    return " - ".join(parts)


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
        if bf.my_unit is not None:
            continue
        
        score = 0
        
        if bf.opponent_unit is None:
            score = 10
        else:
            op_might = bf.opponent_unit.get('might', 0)
            
            if unit_might > op_might:
                score = 20
            elif unit_might == op_might:
                score = 15
            else:
                score = 5
        
        if 'guard' in [k.lower() for k in (unit.keywords or [])]:
            if bf.opponent_unit is not None:
                score += 5
        
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
    threat_level: str,
    synergies: List = None  # NEW
) -> str:
    """Generate human-readable reason for this play step."""
    
    base_reason = ""
    
    if dependencies:
        base_reason = f"Step {step_number}: Play after dependencies met"
    elif card.card_type == CardType.UNIT:
        if battlefield_analysis['empty_battlefields'] > 0:
            base_reason = f"Step {step_number}: Develop board presence"
        elif battlefield_analysis['opponent_only_battlefields'] > 0:
            base_reason = f"Step {step_number}: Contest opponent's battlefield"
        else:
            base_reason = f"Step {step_number}: Strengthen battlefield position"
    elif card.card_type == CardType.SPELL:
        tags_lower = [t.lower() for t in (card.tags or [])]
        if any(t in tags_lower for t in ['removal', 'destroy']):
            base_reason = f"Step {step_number}: Remove opponent threat ({threat_level} priority)"
        elif 'buff' in tags_lower:
            base_reason = f"Step {step_number}: Enhance existing unit"
        elif 'draw' in tags_lower:
            base_reason = f"Step {step_number}: Refill resources"
        else:
            base_reason = f"Step {step_number}: Cast utility spell"
    elif card.card_type == CardType.GEAR:
        base_reason = f"Step {step_number}: Equip gear to strengthen unit"
    else:
        base_reason = f"Step {step_number}: Play card"
    
    # Add legend synergy note if present
    if synergies and len(synergies) > 0:
        # Find the most important synergy
        key_synergy = max(synergies, key=lambda s: s.value_modifier)
        if key_synergy.value_modifier > 1.0:
            base_reason += f" + {key_synergy.description}"
    
    return base_reason


def _assess_sequence_risk(
    steps: List[PlaySequenceStep],
    efficiency: float,
    game_phase: str
) -> str:
    """Assess the risk level of this play sequence."""
    
    if efficiency >= 0.9:
        if game_phase == 'early':
            return "moderate"
        else:
            return "aggressive"
    
    if efficiency >= 0.7:
        return "moderate"
    
    if efficiency < 0.5:
        return "safe"
    
    return "safe"


def _generate_sequence_reasoning(
    steps: List[PlaySequenceStep],
    efficiency: float,
    risk_level: str,
    battlefield_analysis: dict,
    threat_level: str,
    legend_integration: Optional[str] = None  # NEW
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
    
    # Legend integration
    if legend_integration:
        parts.append(legend_integration)
    
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
    card_synergies: Dict[str, List],  # NEW
    battlefield_analysis: dict,
    game_phase: str,
    threat_level: str,
    current_phase: str,
    my_energy: int,
    battlefields: List[BattlefieldState],
    player_state,
    opponent_state,
    primary_sequence: PlaySequence
) -> List[PlaySequence]:
    """Generate alternative play sequences with different strategies."""
    
    alternatives = []
    
    # Alternative 1: Conservative
    cheap_cards = [c for c in cards if c.energy_cost <= 2]
    if cheap_cards:
        conservative_seq = _build_optimal_sequence(
            cheap_cards[:1],
            card_values,
            card_synergies,
            battlefield_analysis,
            game_phase,
            threat_level,
            current_phase,
            my_energy,
            battlefields,
            player_state,
            opponent_state
        )
        if conservative_seq.steps and conservative_seq.total_energy != primary_sequence.total_energy:
            alternatives.append(conservative_seq)
    
    # Alternative 2: Legend synergy focus
    synergy_cards = [
        c for c in cards
        if card_synergies.get(c.card_id) and 
        any(s.value_modifier > 1.0 for s in card_synergies[c.card_id])
    ]
    if len(synergy_cards) >= 1:
        synergy_seq = _build_optimal_sequence(
            synergy_cards,
            card_values,
            card_synergies,
            battlefield_analysis,
            game_phase,
            threat_level,
            current_phase,
            my_energy,
            battlefields,
            player_state,
            opponent_state
        )
        if synergy_seq.steps and synergy_seq.total_energy != primary_sequence.total_energy:
            alternatives.append(synergy_seq)
    
    # Alternative 3: Board control focus
    unit_cards = [c for c in cards if c.card_type == CardType.UNIT]
    if len(unit_cards) >= 2:
        units_seq = _build_optimal_sequence(
            unit_cards,
            card_values,
            card_synergies,
            battlefield_analysis,
            game_phase,
            threat_level,
            current_phase,
            my_energy,
            battlefields,
            player_state,
            opponent_state
        )
        if units_seq.steps and units_seq.total_energy != primary_sequence.total_energy:
            alternatives.append(units_seq)
    
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
    player_state,
    opponent_state,
    battlefields: List[BattlefieldState]
) -> Tuple[float, List]:
    """
    Calculate value score for a card in context.
    Now returns (value, legend_synergies).
    """
    value = 0.0
    
    # Base value from stats
    if card.card_type == CardType.UNIT and card.might:
        efficiency = card.might / max(card.energy_cost, 1)
        value += efficiency * 10
        value += card.might * 0.5
    
    # Keyword bonuses
    if card.keywords:
        keyword_values = {
            "assault": 4,
            "guard": 3,
            "flying": 3,
            "ambush": 2,
            "overwhelm": 4,
            "lifesteal": 2,
            "quick": 3,
            "double strike": 5,
        }
        for keyword in card.keywords:
            value += keyword_values.get(keyword.lower(), 1)
    
    # Context bonuses
    game_phase = _determine_game_phase(turn)
    
    if game_phase == "early":
        if card.energy_cost <= 2:
            value += 5
        elif card.energy_cost >= 4:
            value -= 3
    
    if game_phase == "late":
        if card.card_type == CardType.UNIT and (card.might or 0) >= 5:
            value += 4
    
    # Removal value
    if card.card_type == CardType.SPELL:
        tags_lower = [t.lower() for t in (card.tags or [])]
        
        if any(t in tags_lower for t in ['removal', 'destroy', 'damage']):
            value += battlefield_analysis['opponent_units'] * 3
            
            if battlefield_analysis.get('highest_opponent_might', 0) >= 4:
                value += 3
        
        if 'draw' in tags_lower:
            value += 2
            if game_phase == "late":
                value += 2
    
    # Gear value
    if card.card_type == CardType.GEAR:
        value += battlefield_analysis['my_units'] * 2
        
        if battlefield_analysis['contested_battlefields'] > 0:
            value += 3
    
    # === NEW: Legend synergy integration ===
    synergies, legend_modifier = analyze_legend_synergy(
        card, 
        player_state, 
        opponent_state,
        battlefields
    )
    
    # Add legend modifier to value
    value += legend_modifier * 5  # Amplify legend impact
    
    return max(value, 0.0), synergies


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
    player_state = None,  # NEW: Full player state for legend analysis
    opponent_state = None,  # NEW: Full opponent state
) -> PlayableCardsAdvice:
    """
    Analyze playable cards for Riftbound 1v1 with legend integration.
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
    
    if len(battlefields) != 2:
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            summary=f"Error: Expected 2 battlefields for 1v1, got {len(battlefields)}"
        )
    
    # Filter playable cards (now checks legend exhaustion)
    playable = _filter_playable_cards(hand, my_energy, my_power, player_state)
    
    if not playable:
        power_summary = ", ".join([f"{v} {k}" for k, v in my_power.items()]) if my_power else "0"
        
        # Check if cards blocked by legend exhaustion
        legend_blocked = [
            c for c in hand
            if requires_legend_exhaustion(c) and not can_exhaust_legend(player_state)
        ]
        
        summary_msg = f"No playable cards with {my_energy} energy and {power_summary} power."
        if legend_blocked:
            summary_msg += f" {len(legend_blocked)} card(s) require legend exhaustion."
        
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            recommended_strategies=[],
            primary_strategy=[],
            summary=summary_msg,
            mana_efficiency_note=None,
            scoring_debug=None,
        )
    
    # Analyze game state
    game_phase = _determine_game_phase(turn)
    battlefield_analysis = analyze_riftbound_battlefields(battlefields)
    
    battlefield_analysis['highest_opponent_might'] = max(
        (bf.opponent_unit.get('might', 0) 
         for bf in battlefields 
         if bf.opponent_unit), 
        default=0
    )
    
    threat_level = assess_battlefield_threat_level(
        battlefield_analysis, opponent_score, my_score
    )
    
    # === NEW: Evaluate legend state ===
    legend_evaluation = evaluate_legend_state(player_state)
    
    # Calculate card values WITH legend synergies
    card_values = {}
    card_synergies = {}
    
    for card in playable:
        value, synergies = _calculate_card_value(
            card, turn, battlefield_analysis, 
            player_state, opponent_state, battlefields
        )
        card_values[card.card_id] = value
        card_synergies[card.card_id] = synergies
    
    # Build optimal play sequence (now legend-aware)
    primary_sequence = _build_optimal_sequence(
        playable,
        card_values,
        card_synergies,
        battlefield_analysis,
        game_phase,
        threat_level,
        phase,
        my_energy,
        battlefields,
        player_state,
        opponent_state
    )
    
    # Generate alternative sequences
    alternative_sequences = _generate_alternative_sequences(
        playable,
        card_values,
        card_synergies,
        battlefield_analysis,
        game_phase,
        threat_level,
        phase,
        my_energy,
        battlefields,
        player_state,
        opponent_state,
        primary_sequence
    )
    
    # Convert sequences to strategies
    strategies = []
    
    # Primary strategy
    strategies.append(_convert_sequence_to_strategy(
        primary_sequence,
        "Optimal Sequence",
        priority=1
    ))
    
    # Alternative strategies
    strategy_names = [
        "Conservative Play",
        "Legend Synergy Focus",
        "Board Control Focus"
    ]
    
    for idx, alt_seq in enumerate(alternative_sequences):
        strategy_name = strategy_names[idx] if idx < len(strategy_names) else f"Alternative {idx+1}"
        
        strategies.append(_convert_sequence_to_strategy(
            alt_seq,
            strategy_name,
            priority=idx + 2
        ))
    
    # Build recommendations list with legend synergy information
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
        
        # Enhanced reason with legend synergies
        full_reason = step.reason
        if step.legend_synergies and len(step.legend_synergies) > 0:
            synergy_note = " | Legend synergies: " + ", ".join(step.legend_synergies[:2])
            if len(step.legend_synergies) > 2:
                synergy_note += f" (+{len(step.legend_synergies) - 2} more)"
            full_reason += synergy_note
        
        recommendations.append(
            PlayableCardRecommendation(
                card_id=card.card_id,
                name=card.name,
                card_type=card.card_type,
                energy_cost=card.energy_cost,
                priority=step.step_number,
                recommended=True,
                reason=full_reason,
                battlefield_placement=battlefield_placement,
                value_score=card_values.get(card.card_id, 0.0)
            )
        )
    
    # Add non-sequenced cards as lower priority
    sequenced_ids = {step.card_id for step in primary_sequence.steps}
    for card in playable:
        if card.card_id not in sequenced_ids:
            # Get synergies for context
            synergies = card_synergies.get(card.card_id, [])
            negative_synergies = [s for s in synergies if s.value_modifier < 0]
            
            reason = "Not included in optimal sequence - lower value or doesn't fit energy curve"
            
            # If blocked by negative synergies, explain why
            if negative_synergies:
                blocking = negative_synergies[0]
                reason = f"Not recommended: {blocking.description}"
            
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=card.card_id,
                    name=card.name,
                    card_type=card.card_type,
                    energy_cost=card.energy_cost,
                    priority=len(primary_sequence.steps) + 10,
                    recommended=False,
                    reason=reason,
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
    
    # Add legend integration note
    if primary_sequence.legend_integration:
        mana_note += f". {primary_sequence.legend_integration}"
    
    if len(strategies) > 1:
        mana_note += f" | {len(strategies)} strategies available."
    
    # Summary with legend context
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
    
    # Add sequence info
    if len(primary_sequence.steps) > 1:
        summary += f" Sequence: {len(primary_sequence.steps)} steps."
    
    # Add legend state info if relevant
    if legend_evaluation.recommended_action:
        summary += f" {legend_evaluation.recommended_action}."
    
    # Debug info (now includes legend data)
    scoring_debug = ScoringDebugInfo(
        card_value_scores=card_values,
        threat_assessment={
            "level": threat_level, 
            "details": battlefield_analysis,
            "legend_state": {
                "my_legend": legend_evaluation.legend_name,
                "exhausted": legend_evaluation.exhausted,
                "can_activate": legend_evaluation.can_activate,
                "value_score": legend_evaluation.value_score
            }
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