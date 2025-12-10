# Riftbound advisor
# advisor.py

from typing import Optional, List
from game_state import GameState, CardInHand, PlayerState, Rune, Phase, CardType
from pydantic import BaseModel

class MulliganCardDecision(BaseModel):
    card_id: str
    name: Optional[str]
    keep: bool
    reason: str

class MulliganAdvice(BaseModel):
    decisions: List[MulliganCardDecision]
    summary: str

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
