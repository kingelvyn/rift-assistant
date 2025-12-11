# Riftbound advisor
# advisor.py

from typing import Optional, List
from game_state import GameState, CardInHand, PlayerState, Rune, Phase, CardType, Battlefield
from pydantic import BaseModel

class MulliganCardDecision(BaseModel):
    card_id: str
    name: Optional[str]
    keep: bool
    reason: str

class MulliganAdvice(BaseModel):
    decisions: List[MulliganCardDecision]
    summary: str

class BattlefieldPlacement(BaseModel):
    """Recommendation for which battlefield to place a unit."""
    battlefield_index: int
    reason: str
    priority: int  # Lower = higher priority

class PlayableCardRecommendation(BaseModel):
    card_id: str
    name: Optional[str]
    card_type: CardType
    energy_cost: int
    priority: int  # 1 = highest priority, higher numbers = lower priority
    recommended: bool  # Should this card be played this turn?
    reason: str
    play_order: Optional[int] = None  # Suggested order if playing multiple cards
    battlefield_placement: Optional[BattlefieldPlacement] = None  # For units: which battlefield to play into

class PlayableCardsAdvice(BaseModel):
    playable_cards: List[PlayableCardRecommendation]
    recommended_plays: List[str]  # card_ids of recommended plays
    summary: str
    mana_efficiency_note: Optional[str] = None

def _playable_cards_by_mana(state: GameState) -> List:
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

def _get_all_playable_cards(state: GameState) -> List[CardInHand]:
    """
    Get all cards that can actually be played using can_play().
    More accurate than _playable_cards_by_mana() as it checks rune requirements.
    """
    me = state.me
    return [c for c in me.hand if can_play(c, me)]


def _analyze_battlefield(battlefield: Battlefield, battlefield_index: int) -> dict:
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
        return {
            "battlefield_index": battlefield_index,
            "state": "empty",
            "my_might": 0,
            "op_might": 0,
            "advantage": 0,
            "description": "Empty battlefield - good for establishing presence"
        }
    elif my_unit is not None and op_unit is None:
        # We control this battlefield
        return {
            "battlefield_index": battlefield_index,
            "state": "winning",
            "my_might": my_might,
            "op_might": 0,
            "advantage": my_might,
            "description": f"Winning battlefield with {my_might} might unit"
        }
    elif my_unit is None and op_unit is not None:
        # Opponent controls this battlefield
        return {
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
        
        return {
            "battlefield_index": battlefield_index,
            "state": state,
            "my_might": my_might,
            "op_might": op_might,
            "advantage": advantage,
            "description": desc
        }


def _find_best_battlefield_for_unit(
    unit: CardInHand,
    battlefield_analyses: List[dict],
    turn: int
) -> Optional[BattlefieldPlacement]:
    """
    Determine the best battlefield to place a unit based on:
    - Empty battlefields (highest priority early game)
    - Contested battlefields (if unit can win the trade)
    - Avoiding overfilling winning battlefields
    """
    unit_might = unit.might or 0
    early_game = turn <= 3
    
    # Priority 1: Empty battlefields (especially early game)
    empty_battlefields = [b for b in battlefield_analyses if b["state"] == "empty"]
    if empty_battlefields:
        # Prefer empty battlefields, especially early game
        best_empty = empty_battlefields[0]  # Take first empty battlefield
        return BattlefieldPlacement(
            battlefield_index=best_empty["battlefield_index"],
            reason=f"Empty battlefield - establish board presence{' (high priority early game)' if early_game else ''}",
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
            winning_contests = [b for b in winnable_contests if unit_might > b["op_might"]]
            target = winning_contests[0] if winning_contests else winnable_contests[0]
            
            if unit_might > target["op_might"]:
                reason = f"Contested battlefield - can win trade ({unit_might} vs {target['op_might']} might)"
            else:
                reason = f"Contested battlefield - can trade evenly ({unit_might} vs {target['op_might']} might)"
            
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


def _describe_card(card) -> str:
    cost = card.energy_cost
    t = card.card_type.value
    name = card.name or card.card_id
    return f"{name} ({t}, cost {cost})"


def get_simple_advice(state: GameState) -> str:
    """
    High-level advice depending on phase:

    - Mulligan:
      * Prefer cheap units (cost ≤ 2)
      * Avoid hands that are all 3+ cost or mostly spells
    - Main / Combat:
      * Identify cards you can actually play right now
      * Prefer low-cost units early
      * Warn against slamming high-cost cards too early
    """
    me = state.me
    turn = state.turn
    phase = state.phase

    hand = me.hand
    if not hand:
        return "Your hand is empty, so there is nothing to play. Focus on your next draw."

    # ----- MULLIGAN LOGIC (summary level, detailed logic lives in /advisor/mulligan) -----
    if phase == Phase.MULLIGAN:
        units = [c for c in hand if c.card_type == CardType.UNIT]
        cheap_units = [c for c in units if c.energy_cost <= 2]
        high_cost_cards = [c for c in hand if c.energy_cost >= 4]

        parts: List[str] = []

        if not units:
            parts.append(
                "You have no units in your opening hand. "
                "Consider mulliganing 1–2 non-essential spells/gears to look for early units."
            )
        elif cheap_units:
            names = ", ".join(_describe_card(c) for c in cheap_units)
            parts.append(
                f"You have early units: {names}. "
                "These give you a solid early board; it is usually good to keep them."
            )
        else:
            parts.append(
                "Your units are all 3+ cost. "
                "You may want to mulligan at least one expensive card to smooth your curve."
            )

        if len(high_cost_cards) >= 2:
            names = ", ".join(_describe_card(c) for c in high_cost_cards)
            parts.append(
                f"You are holding several high-cost cards ({names}). "
                "On turn 1, these are likely dead cards; consider sending some back."
            )

        if not parts:
            parts.append("Your opening hand looks reasonably balanced for curve and roles.")

        return " ".join(parts)

    # ----- MAIN / COMBAT PHASE LOGIC -----
    playable = _playable_cards_by_mana(state)

    if not playable:
        return (
            f"You have {me.mana_total or 0} mana available but no cards you can play right now. "
            "Consider holding up interaction or planning for a stronger future turn."
        )

    # Early game definition: first 3 turns
    early_game = turn <= 3

    playable_units = [c for c in playable if c.card_type == CardType.UNIT]
    playable_spells = [c for c in playable if c.card_type == CardType.SPELL]
    playable_gear = [c for c in playable if c.card_type == CardType.GEAR]

    advice_parts: List[str] = []

    # Prefer cheap units early
    if early_game and playable_units:
        cheap_playable_units = [c for c in playable_units if c.energy_cost <= 2]
        if cheap_playable_units:
            names = ", ".join(_describe_card(c) for c in cheap_playable_units)
            advice_parts.append(
                f"Since it is early (turn {turn}), prioritize developing the board. "
                f"Consider playing: {names}."
            )
        else:
            # only 3+ cost units playable
            names = ", ".join(_describe_card(c) for c in playable_units)
            advice_parts.append(
                f"You can play these units this turn: {names}. "
                "They are a bit expensive for early turns; make sure you are not over-committing "
                "if the opponent can answer them easily."
            )
    elif playable_units:
        # mid/late game units
        best_unit = playable_units[0]
        advice_parts.append(
            f"You have playable units; a solid option is {_describe_card(best_unit)} to maintain or build board presence."
        )

    # Mention playable spells (especially cheap ones) as alternatives / support
    if playable_spells:
        cheap_spells = [c for c in playable_spells if c.energy_cost <= 2]
        if cheap_spells:
            names = ", ".join(_describe_card(c) for c in cheap_spells)
            advice_parts.append(
                f"You also have cheap spells: {names}. "
                "Use them to protect your units, answer threats, or push favorable trades."
            )
        else:
            names = ", ".join(_describe_card(c) for c in playable_spells)
            advice_parts.append(
                f"Higher-cost spells available: {names}. "
                "Consider whether you need immediate impact now or can wait for a better moment."
            )

    # Gear: usually best when you already have units worth investing in
    if playable_gear and playable_units:
        gear_names = ", ".join(_describe_card(c) for c in playable_gear)
        advice_parts.append(
            f"You can also play gear: {gear_names}. "
            "Equipping strong units can snowball the board, but only if you already have "
            "good targets on the field."
        )

    # Warn about slamming big stuff too early
    if early_game:
        greedy_plays = [c for c in playable if c.energy_cost >= 4]
        if greedy_plays:
            names = ", ".join(_describe_card(c) for c in greedy_plays)
            advice_parts.append(
                f"Be cautious about playing expensive cards this early ({names}); "
                "they may leave you without flexible responses if the opponent swings the tempo."
            )

    if not advice_parts:
        advice_parts.append(
            "Your hand and mana suggest a flexible turn. Choose plays that either "
            "improve your board or efficiently answer the opponent's threats."
        )

    return " ".join(advice_parts)


def can_play(card: CardInHand, player: PlayerState) -> bool:
    """Check if a card can be played given the player's current resources."""
    # Check total mana
    if player.mana_total is None:
        return False
    
    # Check energy cost (rune tap cost)
    if card.energy_cost > 0:
        # Need to check if player has the required rune tapped
        # For now, simple check: need at least energy_cost total mana
        if player.mana_total < card.energy_cost:
            return False
    
    # Check power cost (rune recycle cost)
    if card.power_cost > 0:
        # Need to check if player has the required runes available
        # For now, simplified check
        if player.mana_total < card.power_cost:
            return False
    
    # Check power cost by rune
    if card.power_cost_by_rune:
        for rune, cost in card.power_cost_by_rune.items():
            available = player.mana_by_rune.get(rune, 0)
            if available < cost:
                return False
    
    return True


def get_mulligan_advice(state: GameState) -> MulliganAdvice:
    """
    Very simple mulligan heuristic:
    - Keep cheap units (cost <= 2)
    - Keep at most one 3-cost unit
    - Mulligan most 4+ cost cards
    - Mulligan expensive non-unit spells/gear
    - Never mulligan ALL cards: always keep at least the cheapest one
    """
    if state.phase != Phase.MULLIGAN:
        # Not strictly necessary, but helps sanity
        summary = "Phase is not mulligan; no mulligan advice applied."
        return MulliganAdvice(decisions=[], summary=summary)

    hand = state.me.hand
    decisions: List[MulliganCardDecision] = []

    # basic rules
    kept_any_3_cost_unit = False

    for card in hand:
        cost = card.energy_cost
        ctype = card.card_type

        keep = True
        reason = "Default keep."

        if ctype == CardType.UNIT:
            if cost <= 2:
                keep = True
                reason = "Cheap unit (cost ≤ 2): good to have early board presence."
            elif cost == 3:
                if not kept_any_3_cost_unit:
                    keep = True
                    kept_any_3_cost_unit = True
                    reason = "Single 3-cost unit: acceptable curve top for opening hand."
                else:
                    keep = False
                    reason = "Additional 3-cost unit: likely too heavy for opening hand."
            else:
                keep = False
                reason = "High-cost unit in opening hand: better to mulligan for cheaper plays."
        else:
            # spells/gear
            if cost == 0:
                keep = True
                reason = "Zero-cost non-unit: flexible and free; safe to keep."
            elif cost == 1:
                keep = True
                reason = "Cheap utility (cost 1): often useful early."
            elif cost <= 2 and "removal" in [t.lower() for t in card.tags]:
                keep = True
                reason = "Cheap removal spell: can answer early threats."
            else:
                keep = False
                reason = "Expensive or situational non-unit: better to mulligan early."

        decisions.append(
            MulliganCardDecision(
                card_id=card.card_id,
                name=card.name,
                keep=keep,
                reason=reason,
            )
        )

    # Safety: never mulligan *all* cards
    if all(not d.keep for d in decisions) and decisions:
        # keep the cheapest card
        cheapest = min(
            decisions,
            key=lambda d: next(
                (c.energy_cost for c in hand if c.card_id == d.card_id),
                99,
            ),
        )
        cheapest.keep = True
        cheapest.reason += " Adjusted: keeping at least one card instead of full mulligan."

    kept = [d for d in decisions if d.keep]
    tossed = [d for d in decisions if not d.keep]

    summary_parts = []
    if kept:
        summary_parts.append(f"Keeping {len(kept)} card(s) focused on cheap early plays.")
    if tossed:
        summary_parts.append(f"Mulliganing {len(tossed)} card(s) that are too expensive or situational.")
    if not summary_parts:
        summary_parts.append("No mulligan changes suggested.")

    summary = " ".join(summary_parts)

    return MulliganAdvice(decisions=decisions, summary=summary)


def get_playable_cards_advice(state: GameState) -> PlayableCardsAdvice:
    """
    Analyze playable cards and provide structured recommendations.
    
    Considers:
    - Mana efficiency (spending all/most mana)
    - Board state (do we have units to equip gear on?)
    - Tempo (early game vs late game priorities)
    - Card type synergies (units before gear, removal when needed)
    - Turn and phase context
    """
    if state.phase == Phase.MULLIGAN:
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            summary="No playable cards advice during mulligan phase. Use /advice/mulligan instead.",
        )
    
    me = state.me
    opponent = state.opponent
    turn = state.turn
    phase = state.phase
    
    # Get all actually playable cards
    playable = _get_all_playable_cards(state)
    
    if not playable:
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            summary=f"No playable cards with current mana ({me.mana_total or 0}). Consider passing or planning for future turns.",
        )
    
    # Analyze board state and battlefields
    my_units_on_board = sum(1 for battlefield in state.battlefields if battlefield.my_unit is not None)
    opponent_units = sum(1 for battlefield in state.battlefields if battlefield.op_unit is not None)
    empty_battlefields = sum(1 for battlefield in state.battlefields if battlefield.my_unit is None)
    
    # Analyze each battlefield for placement decisions
    battlefield_analyses = [
        _analyze_battlefield(battlefield, idx) for idx, battlefield in enumerate(state.battlefields)
    ] if state.battlefields else []
    
    # Count battlefield states
    empty_count = sum(1 for b in battlefield_analyses if b["state"] == "empty")
    contested_count = sum(1 for b in battlefield_analyses if b["state"] == "contested")
    winning_count = sum(1 for b in battlefield_analyses if b["state"] == "winning")
    losing_count = sum(1 for b in battlefield_analyses if b["state"] == "losing")
    
    # Early game heuristic
    early_game = turn <= 3
    mid_game = 4 <= turn <= 6
    late_game = turn > 6
    
    # Available mana
    available_mana = me.mana_total or 0
    
    recommendations: List[PlayableCardRecommendation] = []
    recommended_card_ids: List[str] = []
    
    # Categorize playable cards
    playable_units = [c for c in playable if c.card_type == CardType.UNIT]
    playable_spells = [c for c in playable if c.card_type == CardType.SPELL]
    playable_gear = [c for c in playable if c.card_type == CardType.GEAR]
    
    # Priority scoring: lower number = higher priority
    priority_counter = 1
    
    # Early game: prioritize cheap units for board development
    if early_game:
        cheap_units = [c for c in playable_units if c.energy_cost <= 2]
        if cheap_units and battlefield_analyses:
            # Find best battlefield placements for each cheap unit
            for card in cheap_units:
                if len([r for r in recommendations if r.card_id == card.card_id]) >= 1:
                    continue  # Already recommended
                
                battlefield_placement = _find_best_battlefield_for_unit(card, battlefield_analyses, turn)
                
                if battlefield_placement and battlefield_placement.priority <= 2:  # Only empty or winnable contested battlefields
                    reason = f"Early game board development: {battlefield_placement.reason}"
                    recommendations.append(
                        PlayableCardRecommendation(
                            card_id=card.card_id,
                            name=card.name,
                            card_type=card.card_type,
                            energy_cost=card.energy_cost,
                            priority=priority_counter,
                            recommended=True,
                            reason=reason,
                            battlefield_placement=battlefield_placement,
                        )
                    )
                    recommended_card_ids.append(card.card_id)
                    priority_counter += 1
                    # Update battlefield analysis to reflect this placement (for next unit)
                    if battlefield_placement.battlefield_index < len(battlefield_analyses):
                        # Mark this battlefield as having a unit (simulate)
                        battlefield_analyses[battlefield_placement.battlefield_index]["state"] = "winning"
                        battlefield_analyses[battlefield_placement.battlefield_index]["my_might"] = card.might or 0
    
    # Mid/late game units: prioritize based on might, keywords, and battlefield placement
    if not early_game and playable_units:
        # Sort by might (if available) or cost efficiency
        sorted_units = sorted(
            playable_units,
            key=lambda c: (c.might or 0, -c.energy_cost),
            reverse=True
        )
        for card in sorted_units[:3]:  # Top 3 units
            if card.card_id not in recommended_card_ids:
                # Find best battlefield for this unit
                battlefield_placement = _find_best_battlefield_for_unit(card, battlefield_analyses, turn)
                
                might_str = f" ({card.might} might)" if card.might else ""
                keywords_str = f" [{', '.join(card.keywords)}]" if card.keywords else ""
                
                if battlefield_placement:
                    if battlefield_placement.priority <= 2:  # Good placement (empty or winnable)
                        reason = f"Strong unit{might_str}{keywords_str}. {battlefield_placement.reason}"
                        recommended = True
                    else:  # Suboptimal placement (losing battlefield or overcommitting)
                        reason = f"Strong unit{might_str}{keywords_str}. {battlefield_placement.reason} (lower priority)"
                        recommended = False
                else:
                    # No good battlefield found - might be overcommitting
                    reason = f"Strong unit{might_str}{keywords_str}, but no optimal battlefield placement available."
                    recommended = False
                
                recommendations.append(
                    PlayableCardRecommendation(
                        card_id=card.card_id,
                        name=card.name,
                        card_type=card.card_type,
                        energy_cost=card.energy_cost,
                        priority=priority_counter,
                        recommended=recommended,
                        reason=reason,
                        battlefield_placement=battlefield_placement,
                    )
                )
                if recommended:
                    recommended_card_ids.append(card.card_id)
                priority_counter += 1
    
    # Removal spells: high priority if opponent has threats
    if opponent_units > 0 and playable_spells:
        removal_spells = [
            c for c in playable_spells
            if "removal" in [t.lower() for t in c.tags] or "damage" in [t.lower() for t in c.tags]
        ]
        if removal_spells:
            # Prioritize cheap removal
            removal_spells.sort(key=lambda c: c.energy_cost)
            best_removal = removal_spells[0]
            if best_removal.card_id not in recommended_card_ids:
                recommendations.append(
                    PlayableCardRecommendation(
                        card_id=best_removal.card_id,
                        name=best_removal.name,
                        card_type=best_removal.card_type,
                        energy_cost=best_removal.energy_cost,
                        priority=priority_counter,
                        recommended=True,
                        reason=f"Removal spell to answer opponent's {opponent_units} unit(s) on board.",
                    )
                )
                recommended_card_ids.append(best_removal.card_id)
                priority_counter += 1
    
    # Gear: only recommend if we have units on board
    if my_units_on_board > 0 and playable_gear:
        # Prioritize cheap gear
        playable_gear.sort(key=lambda c: c.energy_cost)
        best_gear = playable_gear[0]
        if best_gear.card_id not in recommended_card_ids:
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=best_gear.card_id,
                    name=best_gear.name,
                    card_type=best_gear.card_type,
                    energy_cost=best_gear.energy_cost,
                    priority=priority_counter,
                    recommended=True,
                    reason=f"Gear to equip on existing unit(s) for value and board advantage.",
                )
            )
            recommended_card_ids.append(best_gear.card_id)
            priority_counter += 1
    
    # Buff/protection spells: useful if we have units
    if my_units_on_board > 0 and playable_spells:
        buff_spells = [
            c for c in playable_spells
            if c.card_id not in recommended_card_ids
            and ("buff" in [t.lower() for t in c.tags] or "protection" in [t.lower() for t in c.tags])
        ]
        if buff_spells:
            buff_spells.sort(key=lambda c: c.energy_cost)
            best_buff = buff_spells[0]
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=best_buff.card_id,
                    name=best_buff.name,
                    card_type=best_buff.card_type,
                    energy_cost=best_buff.energy_cost,
                    priority=priority_counter,
                    recommended=True,
                    reason=f"Buff/protection spell to enhance or protect your units.",
                )
            )
            recommended_card_ids.append(best_buff.card_id)
            priority_counter += 1
    
    # Add remaining playable cards as lower priority options
    for card in playable:
        if card.card_id not in recommended_card_ids:
            reason = "Playable but lower priority. Consider if it fits your game plan."
            if card.energy_cost >= 4 and early_game:
                reason = "Expensive for early game; may be better to save for later."
            elif card.card_type == CardType.SPELL and not card.tags:
                reason = "Utility spell; play when needed for specific situation."
            
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=card.card_id,
                    name=card.name,
                    card_type=card.card_type,
                    energy_cost=card.energy_cost,
                    priority=priority_counter,
                    recommended=False,
                    reason=reason,
                )
            )
            priority_counter += 1
    
    # Sort recommendations by priority
    recommendations.sort(key=lambda r: r.priority)
    
    # Calculate mana efficiency
    recommended_mana_cost = sum(
        c.energy_cost for c in playable
        if c.card_id in recommended_card_ids
    )
    mana_efficiency_note = None
    if available_mana > 0:
        efficiency = (recommended_mana_cost / available_mana) * 100
        if efficiency < 50:
            mana_efficiency_note = f"Recommended plays use {recommended_mana_cost}/{available_mana} mana ({efficiency:.0f}%). Consider additional plays if needed."
        elif efficiency > 90:
            mana_efficiency_note = f"Recommended plays use {recommended_mana_cost}/{available_mana} mana ({efficiency:.0f}%) - efficient use of resources."
    
    # Build summary with battlefield awareness
    summary_parts = []
    if recommended_card_ids:
        summary_parts.append(f"Found {len(recommended_card_ids)} recommended play(s) out of {len(playable)} playable cards.")
    else:
        summary_parts.append(f"Found {len(playable)} playable cards, but none are strongly recommended this turn.")
    
    # Add battlefield state summary
    if battlefield_analyses:
        battlefield_summary_parts = []
        if empty_count > 0:
            battlefield_summary_parts.append(f"{empty_count} empty battlefield(s)")
        if contested_count > 0:
            battlefield_summary_parts.append(f"{contested_count} contested battlefield(s)")
        if winning_count > 0:
            battlefield_summary_parts.append(f"{winning_count} winning battlefield(s)")
        if losing_count > 0:
            battlefield_summary_parts.append(f"{losing_count} losing battlefield(s)")
        
        if battlefield_summary_parts:
            summary_parts.append(f"Board state: {', '.join(battlefield_summary_parts)}.")
    
    if early_game:
        summary_parts.append("Early game: prioritize board development in empty battlefields.")
    elif mid_game:
        summary_parts.append("Mid game: balance tempo and value, contest key battlefields.")
    else:
        summary_parts.append("Late game: focus on high-impact plays and securing advantages.")
    
    summary = " ".join(summary_parts)
    
    return PlayableCardsAdvice(
        playable_cards=recommendations,
        recommended_plays=recommended_card_ids,
        summary=summary,
        mana_efficiency_note=mana_efficiency_note,
    )
