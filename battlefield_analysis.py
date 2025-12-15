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


def build_strategy_summary(
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
   


# ----------------------
# LEGACY FUNCTIONS
# ----------------------
def analyze_battlefield_legacy(battlefield: Battlefield, battlefield_index: int) -> dict:
    """
    Analyze a single battlefield and return its state.
    
    Returns:
    - battlefield_state: "empty", "winning", "losing", "contested", "neutral"
    - my_might: might of our unit (0 if none)
    - op_might: might of opponent unit (0 if none)
    - advantage: positive if we're winning, negative if losing
    """
    my_unit = battlefield.my_unit
    op_unit = battlefield.op_unit
    
    my_might = my_unit.current_might if my_unit and my_unit.current_might is not None else (my_unit.might if my_unit else 0)
    op_might = op_unit.current_might if op_unit and op_unit.current_might is not None else (op_unit.might if op_unit else 0)
    
    if my_unit is None and op_unit is None:
        result = {
            "battlefield_index": battlefield_index,
            "state": "empty",
            "my_might": 0,
            "op_might": 0,
            "advantage": 0,
            "description": "Empty battlefield - good for establishing presence"
        }
    elif my_unit is not None and op_unit is None:
        # We control this battlefield
        result = {
            "battlefield_index": battlefield_index,
            "state": "winning",
            "my_might": my_might,
            "op_might": 0,
            "advantage": my_might,
            "description": f"Winning battlefield with {my_might} might unit"
        }
    elif my_unit is None and op_unit is not None:
        # Opponent controls this battlefield
        result = {
            "battlefield_index": battlefield_index,
            "state": "contested",
            "my_might": 0,
            "op_might": op_might,
            "advantage": -op_might,
            "description": f"Contested battlefield - opponent has {op_might} might unit"
        }
    else:
        # Both have units - compare might
        advantage = my_might - op_might
        if advantage > 0:
            state = "winning"
            desc = f"Winning trade ({my_might} vs {op_might} might)"
        elif advantage < 0:
            state = "losing"
            desc = f"Losing trade ({my_might} vs {op_might} might)"
        else:
            state = "neutral"
            desc = f"Even trade ({my_might} vs {op_might} might)"
        
        result = {
            "battlefield_index": battlefield_index,
            "state": state,
            "my_might": my_might,
            "op_might": op_might,
            "advantage": advantage,
            "description": desc
        }
    
    log_battlefield_analysis(
        advisor_logger,
        battlefield_index,
        state=result["state"],
        my_might=result["my_might"],
        op_might=result["op_might"],
        advantage=result["advantage"]
    )
    return result


def find_best_battlefield_for_unit_legacy(
    unit: CardInHand,
    battlefield_analyses: List[dict],
    turn: int
) -> Optional[BattlefieldPlacement]:
    """
    Determine the best battlefield to place a unit based on:
    - Empty battlefields (highest priority early game)
    - Contested battlefields (if unit can win the trade)
    - Keyword-aware placement (Guard units protect, Assault units push)
    - Avoiding overfilling winning battlefields
    """
    unit_might = unit.might or 0
    early_game = turn <= 3
    keywords_lower = [k.lower() for k in unit.keywords] if unit.keywords else []
    has_guard = "guard" in keywords_lower
    has_assault = "assault" in keywords_lower
    
    # Priority 1: Empty battlefields (especially early game)
    empty_battlefields = [b for b in battlefield_analyses if b["state"] == "empty"]
    if empty_battlefields:
        # Prefer empty battlefields, especially early game
        # If unit has Guard, prefer empty battlefields (can protect later)
        # If unit has Assault, prefer empty battlefields (can push damage)
        best_empty = empty_battlefields[0]  # Take first empty battlefield
        
        keyword_note = ""
        if has_guard:
            keyword_note = " Guard unit can protect this battlefield."
        elif has_assault:
            keyword_note = " Assault unit can push damage from here."
        
        return BattlefieldPlacement(
            battlefield_index=best_empty["battlefield_index"],
            reason=f"Empty battlefield - establish board presence{' (high priority early game)' if early_game else ''}.{keyword_note}",
            priority=1
        )
    
    # Priority 2: Contested battlefields where we can win or tie
    contested_battlefields = [b for b in battlefield_analyses if b["state"] == "contested"]
    if contested_battlefields:
        # Find battlefields where our unit can win or at least trade
        winnable_contests = [
            b for b in contested_battlefields
            if unit_might >= b["op_might"]
        ]
        if winnable_contests:
            # Prefer battlefields where we can win (not just trade)
            # Guard units prefer contested battlefields where they can protect
            # Assault units prefer winning trades
            winning_contests = [b for b in winnable_contests if unit_might > b["op_might"]]
            target = winning_contests[0] if winning_contests else winnable_contests[0]
            
            keyword_note = ""
            if has_guard and unit_might >= target["op_might"]:
                keyword_note = " Guard unit can protect and contest this battlefield."
            elif has_assault and unit_might > target["op_might"]:
                keyword_note = " Assault unit can win trade and push advantage."
            
            if unit_might > target["op_might"]:
                reason = f"Contested battlefield - can win trade ({unit_might} vs {target['op_might']} might).{keyword_note}"
            else:
                reason = f"Contested battlefield - can trade evenly ({unit_might} vs {target['op_might']} might).{keyword_note}"
            
            return BattlefieldPlacement(
                battlefield_index=target["battlefield_index"],
                reason=reason,
                priority=2
            )
        # If we can't win, but it's a close trade, still consider it
        close_contests = [
            b for b in contested_battlefields
            if unit_might >= b["op_might"] - 1  # Within 1 might
        ]
        if close_contests and not early_game:  # Only in mid/late game
            target = close_contests[0]
            return BattlefieldPlacement(
                battlefield_index=target["battlefield_index"],
                reason=f"Contested battlefield - close trade ({unit_might} vs {target['op_might']} might), may need support",
                priority=3
            )
    
    # Priority 3: Losing battlefields where we can turn the tide
    losing_battlefields = [b for b in battlefield_analyses if b["state"] == "losing"]
    if losing_battlefields:
        # Find battlefields where our unit can win or at least improve the situation
        improvable = [
            b for b in losing_battlefields
            if unit_might >= b["op_might"]  # Can win or tie
        ]
        if improvable:
            target = improvable[0]
            return BattlefieldPlacement(
                battlefield_index=target["battlefield_index"],
                reason=f"Losing battlefield - can turn the tide ({unit_might} vs {target['op_might']} might)",
                priority=3
            )
    
    # Priority 4: Winning battlefields (only if no better options and we need to overcommit)
    # Generally avoid this unless it's a very strong unit
    winning_battlefields = [b for b in battlefield_analyses if b["state"] == "winning"]
    if winning_battlefields and unit_might >= 4:  # Only for strong units
        # Only recommend if we're significantly ahead and unit is strong
        target = winning_battlefields[0]
        if target["advantage"] >= 2:  # Already winning by 2+
            return BattlefieldPlacement(
                battlefield_index=target["battlefield_index"],
                reason=f"Winning battlefield - overcommitting with strong unit ({unit_might} might) to secure advantage",
                priority=4
            )
    
    # No good battlefield found
    return None

