# Riftbound advisor
# advisor.py

from typing import List
from game_state import GameState, CardType, Phase
from logger_config import (
    advisor_logger,
    log_game_state,
    log_advisor_decision,
    log_battlefield_analysis,
)

# Import models
from advisor_models import (
    MulliganCardDecision,
    MulliganAdvice,
    PlayableCardRecommendation,
    PlayableCardsAdvice,
    ScoringDebugInfo,
)

# Import evaluation functions
from card_evaluation import (
    get_all_playable_cards,
    playable_cards_by_mana,
    describe_card,
    calculate_card_value,
    assess_threat_level,
    should_hold_card,
    calculate_mana_efficiency_score,
)

# Import battlefield analysis
from battlefield_analysis import (
    analyze_battlefield,
    find_best_battlefield_for_unit,
)

# Import legend analysis
from legend_analysis import (
    analyze_legend_synergy,
)


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
            names = ", ".join(describe_card(c) for c in cheap_units)
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
            names = ", ".join(describe_card(c) for c in high_cost_cards)
            parts.append(
                f"You are holding several high-cost cards ({names}). "
                "On turn 1, these are likely dead cards; consider sending some back."
            )

        if not parts:
            parts.append("Your opening hand looks reasonably balanced for curve and roles.")

        return " ".join(parts)

    # ----- MAIN / COMBAT PHASE LOGIC -----
    playable = playable_cards_by_mana(state)

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
            names = ", ".join(describe_card(c) for c in cheap_playable_units)
            advice_parts.append(
                f"Since it is early (turn {turn}), prioritize developing the board. "
                f"Consider playing: {names}."
            )
        else:
            # only 3+ cost units playable
            names = ", ".join(describe_card(c) for c in playable_units)
            advice_parts.append(
                f"You can play these units this turn: {names}. "
                "They are a bit expensive for early turns; make sure you are not over-committing "
                "if the opponent can answer them easily."
            )
    elif playable_units:
        # mid/late game units
        best_unit = playable_units[0]
        advice_parts.append(
            f"You have playable units; a solid option is {describe_card(best_unit)} to maintain or build board presence."
        )

    # Mention playable spells (especially cheap ones) as alternatives / support
    if playable_spells:
        cheap_spells = [c for c in playable_spells if c.energy_cost <= 2]
        if cheap_spells:
            names = ", ".join(describe_card(c) for c in cheap_spells)
            advice_parts.append(
                f"You also have cheap spells: {names}. "
                "Use them to protect your units, answer threats, or push favorable trades."
            )
        else:
            names = ", ".join(describe_card(c) for c in playable_spells)
            advice_parts.append(
                f"Higher-cost spells available: {names}. "
                "Consider whether you need immediate impact now or can wait for a better moment."
            )

    # Gear: usually best when you already have units worth investing in
    if playable_gear and playable_units:
        gear_names = ", ".join(describe_card(c) for c in playable_gear)
        advice_parts.append(
            f"You can also play gear: {gear_names}. "
            "Equipping strong units can snowball the board, but only if you already have "
            "good targets on the field."
        )

    # Warn about slamming big stuff too early
    if early_game:
        greedy_plays = [c for c in playable if c.energy_cost >= 4]
        if greedy_plays:
            names = ", ".join(describe_card(c) for c in greedy_plays)
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


def get_mulligan_advice(state: GameState) -> MulliganAdvice:
    """Very simple mulligan heuristic with logging."""
    advisor_logger.info(f"Processing mulligan advice for turn {state.turn}")
    log_game_state(advisor_logger, state, "mulligan", turn=state.turn, phase=state.phase.value)
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

    # Improved mulligan heuristics
    kept_any_3_cost_unit = False
    
    # Count hand composition for better decisions
    unit_count = sum(1 for c in hand if c.card_type == CardType.UNIT)
    cheap_unit_count = sum(1 for c in hand if c.card_type == CardType.UNIT and c.energy_cost <= 2)
    spell_count = sum(1 for c in hand if c.card_type == CardType.SPELL)
    high_cost_count = sum(1 for c in hand if c.energy_cost >= 4)
    
    # Check for legend-specific cards
    legend_id = state.me.legend.card_id if state.me.legend else None
    legend_synergy_cards = []
    if legend_id:
        for card in hand:
            if card.rules_text and legend_id.lower() in card.rules_text.lower():
                legend_synergy_cards.append(card.card_id)

    for card in hand:
        cost = card.energy_cost
        ctype = card.card_type

        keep = True
        reason = "Default keep."

        if ctype == CardType.UNIT:
            if cost <= 2:
                keep = True
                # Prioritize units with good keywords
                if card.keywords:
                    important_keywords = [k for k in card.keywords if k.lower() in ["assault", "guard"]]
                    if important_keywords:
                        reason = f"Cheap unit (cost ≤ 2) with {', '.join(important_keywords)}: excellent early game."
                    else:
                        reason = "Cheap unit (cost ≤ 2): good to have early board presence."
                else:
                    reason = "Cheap unit (cost ≤ 2): good to have early board presence."
            elif cost == 3:
                if not kept_any_3_cost_unit:
                    keep = True
                    kept_any_3_cost_unit = True
                    # Prefer 3-cost units with good stats/keywords
                    if card.might and card.might >= 3:
                        reason = "Strong 3-cost unit: good curve top with solid stats."
                    else:
                        reason = "Single 3-cost unit: acceptable curve top for opening hand."
                else:
                    keep = False
                    reason = "Additional 3-cost unit: likely too heavy for opening hand."
            else:
                keep = False
                # Exception: keep if it's a legend synergy card
                if card.card_id in legend_synergy_cards:
                    keep = True
                    reason = "High-cost unit but has legend synergy: worth keeping."
                else:
                    reason = "High-cost unit in opening hand: better to mulligan for cheaper plays."
        else:
            # spells/gear
            if cost == 0:
                keep = True
                reason = "Zero-cost non-unit: flexible and free; safe to keep."
            elif cost == 1:
                keep = True
                # Prioritize removal and utility
                tags_lower = [t.lower() for t in (card.tags or [])]
                if "removal" in tags_lower:
                    reason = "Cheap removal (cost 1): excellent early game answer."
                else:
                    reason = "Cheap utility (cost 1): often useful early."
            elif cost <= 2:
                tags_lower = [t.lower() for t in (card.tags or [])]
                if "removal" in tags_lower:
                    keep = True
                    reason = "Cheap removal spell: can answer early threats."
                elif card.card_id in legend_synergy_cards:
                    keep = True
                    reason = "Cheap spell with legend synergy: worth keeping."
                else:
                    # Consider hand balance
                    if spell_count >= 3 and cheap_unit_count == 0:
                        keep = False
                        reason = "Too many spells, need units for board presence."
                    else:
                        keep = True
                        reason = "Cheap utility spell: acceptable in balanced hand."
            else:
                # Expensive spells/gear
                if card.card_id in legend_synergy_cards:
                    keep = True
                    reason = "Expensive but has legend synergy: consider keeping."
                elif high_cost_count >= 2 and cheap_unit_count == 0:
                    keep = False
                    reason = "Too many expensive cards, need cheaper plays."
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
    advisor_logger.info(f"Processing playable cards advice for turn {state.turn}, phase {state.phase.value}")
    log_game_state(
        advisor_logger,
        state,
        "playable_cards",
        turn=state.turn,
        phase=state.phase.value,
        my_mana=state.me.mana_total,
        hand_size=len(state.me.hand),
        battlefield_count=len(state.battlefields)
    )
    
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
    playable = get_all_playable_cards(state)
    
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
        analyze_battlefield(battlefield, idx) for idx, battlefield in enumerate(state.battlefields)
    ] if state.battlefields else []
    
    log_battlefield_analysis(
        advisor_logger,
        battlefield_analyses,
        turn=state.turn,
        battlefield_count=len(state.battlefields)
    )
    
    # Count battlefield states
    empty_count = sum(1 for b in battlefield_analyses if b["state"] == "empty")
    contested_count = sum(1 for b in battlefield_analyses if b["state"] == "contested")
    winning_count = sum(1 for b in battlefield_analyses if b["state"] == "winning")
    losing_count = sum(1 for b in battlefield_analyses if b["state"] == "losing")
    
    # Assess threat level from opponent
    threat_assessment = assess_threat_level(battlefield_analyses, opponent)
    
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
    
    # Calculate value scores for all playable cards
    card_values = {card.card_id: calculate_card_value(card) for card in playable}
    
    # Priority scoring: lower number = higher priority
    priority_counter = 1
    
    # Early game: prioritize cheap units for board development
    # Sort by value score to get best units first
    if early_game:
        cheap_units = [c for c in playable_units if c.energy_cost <= 2]
        if cheap_units and battlefield_analyses:
            # Sort by value score (better units first)
            cheap_units.sort(key=lambda c: card_values.get(c.card_id, 0), reverse=True)
            
            # Find best battlefield placements for each cheap unit
            for card in cheap_units:
                if len([r for r in recommendations if r.card_id == card.card_id]) >= 1:
                    continue  # Already recommended
                
                battlefield_placement = find_best_battlefield_for_unit(card, battlefield_analyses, turn)
                
                if battlefield_placement and battlefield_placement.priority <= 2:  # Only empty or winnable contested battlefields
                    # Add keyword context to reason
                    keyword_note = ""
                    if card.keywords:
                        important_keywords = [k for k in card.keywords if k.lower() in ["assault", "guard", "support"]]
                        if important_keywords:
                            keyword_note = f" ({', '.join(important_keywords)})"
                    
                    reason = f"Early game board development: {battlefield_placement.reason}{keyword_note}"
                    legend_synergy = analyze_legend_synergy(card, me, opponent)
                    value_score = card_values.get(card.card_id, 0.0)
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
                            legend_synergy=legend_synergy,
                            value_score=value_score,
                        )
                    )
                    recommended_card_ids.append(card.card_id)
                    priority_counter += 1
                    # Update battlefield analysis to reflect this placement (for next unit)
                    if battlefield_placement.battlefield_index < len(battlefield_analyses):
                        # Mark this battlefield as having a unit (simulate)
                        battlefield_analyses[battlefield_placement.battlefield_index]["state"] = "winning"
                        battlefield_analyses[battlefield_placement.battlefield_index]["my_might"] = card.might or 0
    
    # Mid/late game units: prioritize based on value score, keywords, and battlefield placement
    if not early_game and playable_units:
        # Sort by value score (considers might per mana, keywords, etc.)
        sorted_units = sorted(
            playable_units,
            key=lambda c: (
                card_values.get(c.card_id, 0),
                c.might or 0,
                -c.energy_cost
            ),
            reverse=True
        )
        for card in sorted_units[:3]:  # Top 3 units
            if card.card_id not in recommended_card_ids:
                # Find best battlefield for this unit
                battlefield_placement = find_best_battlefield_for_unit(card, battlefield_analyses, turn)
                
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
                
                legend_synergy = analyze_legend_synergy(card, me, opponent)
                value_score = card_values.get(card.card_id, 0.0)
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
                        legend_synergy=legend_synergy,
                        value_score=value_score,
                    )
                )
                if recommended:
                    recommended_card_ids.append(card.card_id)
                priority_counter += 1
    
    # Removal spells: high priority if opponent has threats
    # Prioritize removal more if threat level is high
    if opponent_units > 0 and playable_spells:
        removal_spells = [
            c for c in playable_spells
            if "removal" in [t.lower() for t in (c.tags or [])] or "damage" in [t.lower() for t in (c.tags or [])]
        ]
        if removal_spells:
            # Sort by value score (considering threat level) and cost
            # High threat = prioritize removal even if more expensive
            if threat_assessment["threat_level"] == "high":
                removal_spells.sort(key=lambda c: (-card_values.get(c.card_id, 0), c.energy_cost))
            else:
                removal_spells.sort(key=lambda c: (c.energy_cost, -card_values.get(c.card_id, 0)))
            
            best_removal = removal_spells[0]
            if best_removal.card_id not in recommended_card_ids:
                # Check if we should hold this removal
                should_hold = should_hold_card(best_removal, state, threat_assessment)
                
                if not should_hold:
                    threat_desc = f"High threat level" if threat_assessment["threat_level"] == "high" else f"{opponent_units} unit(s)"
                    legend_synergy = analyze_legend_synergy(best_removal, me, opponent)
                    value_score = card_values.get(best_removal.card_id, 0.0)
                    recommendations.append(
                        PlayableCardRecommendation(
                            card_id=best_removal.card_id,
                            name=best_removal.name,
                            card_type=best_removal.card_type,
                            energy_cost=best_removal.energy_cost,
                            priority=priority_counter,
                            recommended=True,
                            reason=f"Removal spell to answer opponent's {threat_desc} on board.",
                            legend_synergy=legend_synergy,
                            value_score=value_score,
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
            legend_synergy = analyze_legend_synergy(best_gear, me, opponent)
            value_score = card_values.get(best_gear.card_id, 0.0)
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=best_gear.card_id,
                    name=best_gear.name,
                    card_type=best_gear.card_type,
                    energy_cost=best_gear.energy_cost,
                    priority=priority_counter,
                    recommended=True,
                    reason=f"Gear to equip on existing unit(s) for value and board advantage.",
                    legend_synergy=legend_synergy,
                    value_score=value_score,
                )
            )
            recommended_card_ids.append(best_gear.card_id)
            priority_counter += 1
    
    # Buff/protection spells: useful if we have units
    if my_units_on_board > 0 and playable_spells:
        buff_spells = [
            c for c in playable_spells
            if c.card_id not in recommended_card_ids
            and ("buff" in [t.lower() for t in (c.tags or [])] or "protection" in [t.lower() for t in (c.tags or [])])
        ]
        if buff_spells:
            buff_spells.sort(key=lambda c: c.energy_cost)
            best_buff = buff_spells[0]
            legend_synergy = analyze_legend_synergy(best_buff, me, opponent)
            value_score = card_values.get(best_buff.card_id, 0.0)
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=best_buff.card_id,
                    name=best_buff.name,
                    card_type=best_buff.card_type,
                    energy_cost=best_buff.energy_cost,
                    priority=priority_counter,
                    recommended=True,
                    reason=f"Buff/protection spell to enhance or protect your units.",
                    legend_synergy=legend_synergy,
                    value_score=value_score,
                )
            )
            recommended_card_ids.append(best_buff.card_id)
            priority_counter += 1
    
    # Add remaining playable cards as lower priority options
    # Check if they should be held or are just lower value
    for card in playable:
        if card.card_id not in recommended_card_ids:
            should_hold = should_hold_card(card, state, threat_assessment)
            
            if should_hold:
                reason = f"Consider holding this card (cost {card.energy_cost}) for a better opportunity."
                if card.card_type == CardType.SPELL and card.keywords and "reaction" in [k.lower() for k in card.keywords]:
                    reason = "Reaction spell - hold for opponent's turn or critical moment."
            else:
                reason = "Playable but lower priority. Consider if it fits your game plan."
                if card.energy_cost >= 4 and early_game:
                    reason = "Expensive for early game; may be better to save for later."
                elif card.card_type == CardType.SPELL and not card.tags:
                    reason = "Utility spell; play when needed for specific situation."
                elif card.card_type == CardType.UNIT:
                    value_score = card_values.get(card.card_id, 0)
                    if value_score < 2.0:
                        reason = f"Lower value unit (value score: {value_score:.1f}). Consider better options first."
            
            legend_synergy = analyze_legend_synergy(card, me, opponent)
            value_score = card_values.get(card.card_id, 0.0)
            recommendations.append(
                PlayableCardRecommendation(
                    card_id=card.card_id,
                    name=card.name,
                    card_type=card.card_type,
                    energy_cost=card.energy_cost,
                    priority=priority_counter,
                    recommended=False,
                    reason=reason,
                    legend_synergy=legend_synergy,
                    value_score=value_score,
                )
            )
            priority_counter += 1
    
    # Sort recommendations by priority
    recommendations.sort(key=lambda r: r.priority)
    
    # Calculate mana efficiency with improved scoring
    recommended_cards_list = [c for c in playable if c.card_id in recommended_card_ids]
    recommended_mana_cost = sum(c.energy_cost for c in recommended_cards_list)
    mana_efficiency_score = calculate_mana_efficiency_score(recommended_cards_list, available_mana)
    
    mana_efficiency_note = None
    if available_mana > 0:
        efficiency_pct = (recommended_mana_cost / available_mana) * 100
        if mana_efficiency_score < 0.5:
            mana_efficiency_note = f"Recommended plays use {recommended_mana_cost}/{available_mana} mana ({efficiency_pct:.0f}%). Consider additional plays or holding cards for better opportunities."
        elif mana_efficiency_score >= 0.9:
            mana_efficiency_note = f"Recommended plays use {recommended_mana_cost}/{available_mana} mana ({efficiency_pct:.0f}%) - efficient use of resources."
        else:
            mana_efficiency_note = f"Recommended plays use {recommended_mana_cost}/{available_mana} mana ({efficiency_pct:.0f}%)."
    
    # Build summary with battlefield and legend awareness
    summary_parts = []
    if recommended_card_ids:
        summary_parts.append(f"Found {len(recommended_card_ids)} recommended play(s) out of {len(playable)} playable cards.")
    else:
        summary_parts.append(f"Found {len(playable)} playable cards, but none are strongly recommended this turn.")
    
    # Add legend state summary
    if me.legend:
        legend_state = "exhausted" if me.legend.exhausted else "ready"
        summary_parts.append(f"Your legend ({me.legend.name or me.legend.card_id}) is {legend_state}.")
    
    if opponent.legend:
        op_legend_state = "exhausted" if opponent.legend.exhausted else "ready"
        summary_parts.append(f"Opponent's legend ({opponent.legend.name or opponent.legend.card_id}) is {op_legend_state}.")
        # Note opponent legend abilities that might affect us
        if opponent.legend.triggered_abilities:
            summary_parts.append(f"Watch for opponent legend triggered abilities.")
    
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
    
    # Determine game phase for debug info
    game_phase = "early" if early_game else ("mid" if mid_game else "late")
    
    # Build scoring debug info
    scoring_debug = ScoringDebugInfo(
        card_value_scores=card_values,
        threat_assessment=threat_assessment,
        mana_efficiency_score=mana_efficiency_score,
        battlefield_analyses=battlefield_analyses,
        game_phase=game_phase,
    )
    
    advice = PlayableCardsAdvice(
        playable_cards=recommendations,
        recommended_plays=recommended_card_ids,
        summary=summary,
        mana_efficiency_note=mana_efficiency_note,
        scoring_debug=scoring_debug,
    )
    
    log_advisor_decision(
        advisor_logger,
        state,
        "playable_cards",
        advice,
        turn=state.turn,
        phase=state.phase.value,
        playable_count=len(playable),
        recommended_count=len(recommended_card_ids),
        my_mana=me.mana_total,
        opponent_mana=opponent.mana_total,
        my_legend=me.legend.card_id if me.legend else None,
        opponent_legend=opponent.legend.card_id if opponent.legend else None,
        battlefield_states={
            "empty": empty_count,
            "contested": contested_count,
            "winning": winning_count,
            "losing": losing_count
        }
    )
    
    return advice
