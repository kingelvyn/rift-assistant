# Battlefield analysis and unit placement logic
# battlefield_analysis.py

from typing import Optional, List
from game_state import Battlefield, CardInHand
from advisor_models import BattlefieldPlacement
from logger_config import advisor_logger, log_battlefield_analysis

def analyze_battlefield(battlefield: Battlefield, battlefield_index: int) -> dict:
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


def find_best_battlefield_for_unit(
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

