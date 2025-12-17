# Battlefield analysis and unit placement logic
# battlefield_analysis.py

from typing import Optional, List, Dict
from game_state import Battlefield, CardInHand
from advisor_models import BattlefieldPlacement, BattlefieldState
from logger_config import advisor_logger, log_battlefield_analysis


# ----------------------
# NEW FUNCTIONS
# ----------------------
def analyze_riftbound_battlefields(battlefields: List[BattlefieldState]) -> dict:
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
        has_my_unit = bf.my_unit_id is not None
        has_op_unit = bf.opponent_unit_id is not None
        
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


def find_best_battlefield(
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
        if not battlefield.my_unit and battlefield.opponent_unit:
            op_might = battlefield.opponent_unit.get("might", 0)  # This is still a dict
            if card.might and card.might > op_might:
                return BattlefieldPlacement(
                    battlefield_index=idx,
                    reason=f"Contest and win against {op_might} might opponent",
                    priority=2
                )
    
    return None


# ----------------------
# HELPER FUNCTIONS
# ----------------------
def assess_battlefield_threat_level(
    battlefield_analysis: dict,
    opponent_score: Optional[int],
    my_score: Optional[int]
) -> str:
    """Assess overall threat level from opponent."""
    # High threat if:
    # - Opponent controls both battlefields
    # - Opponent has significantly more might
    # - We're low on points and opponent has units
    
    if battlefield_analysis['opponent_only_battlefields'] == 2:
        return "critical"  # Opponent controls both battlefields
    
    might_diff = battlefield_analysis['opponent_total_might'] - battlefield_analysis['my_total_might']
    
    if might_diff >= 4:
        return "high"  # Opponent has much more board presence
    
    if my_score and my_score <= 4 and battlefield_analysis['opponent_units'] > 0:
        return "high"  # Low score, opponent units threatening
    
    if battlefield_analysis['losing_battlefields'] >= 1:
        return "medium"  # Losing at least one battlefield
    
    return "low"


def build_strategy_summary(
    turn: int,
    game_phase: str,
    phase: str,
    recommended_count: int,
    playable_count: int,
    battlefield_analysis: dict,
    threat_level: str,
    my_score: Optional[int],
    opponent_score: Optional[int]
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

    # Score context
    if my_score and opponent_score:
        score_diff = my_score - opponent_score
        if score_diff <= -3:
            parts.append(f"Behind on points ({my_score} vs {opponent_score}) - need pressure")
        elif score_diff >= 3:
            parts.append(f"Ahead on life ({my_score} vs {opponent_score}) - maintain advantage")

    # Strategic focus
    focus_messages = {
        "early": "Focus: Develop board, contest battlefields early",
        "mid": "Focus: Tempo plays and favorable trades",
        "late": "Focus: High-impact finishers and closing"
    }
    parts.append(focus_messages[game_phase])

    return ". ".join(parts) + "."
