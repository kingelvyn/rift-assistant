# mulligan_advisor.py

from typing import List, Optional
from game_state import CardInHand, CardType
from card_db import CardRecord
from advisor_models import MulliganAdvice, MulliganAdviceResponse, MulliganCardDecision, MulliganRequest

def analyze_mulligan(
    hand: List[CardInHand],
    legend_card: Optional[CardRecord] = None,
    turn: int = 1,
    going_first: bool = True
) -> MulliganAdvice:
    """
    Mulligan heuristic that works directly on hand data.
    Riftbound Rules:
    - Opening hand is exactly 4 cards
    - Maximum 2 cards can be mulliganed
    Strategy:
    - Keep cheap units (cost <= 2)
    - Keep at most one 3-cost unit
    - Mulligan most 4+ cost cards
    - Mulligan expensive non-unit spells/gear
    - Never mulligan ALL cards
    """
    if not hand:
        return MulliganAdvice(
            decisions=[],
            summary="No cards in hand to evaluate.",
            mulligan_count=0
        )
    
    if len(hand) != 4:
        return MulliganAdvice(
            decisions=[],
            summary=f"Invalid hand size: expected 4 cards, got {len(hand)}.",
            mulligan_count=0
        )
    
    # Analyze hand composition
    composition = analyze_hand_composition(hand)
    
    # Identify legend synergies
    legend_synergy_cards = identify_legend_synergies(hand, legend_card)
    
    # Initialize state tracking
    decisions: List[MulliganCardDecision] = []
    kept_any_3_cost_unit = False
    
    hand_state = {
        'kept_any_3_cost_unit': False,
        'cheap_unit_count': composition['cheap_unit_count'],
        'spell_count': composition['spell_count'],
        'high_cost_count': composition['high_cost_count'],
    }
    
    # Evaluate each card
    for card in hand:
        keep, reason = evaluate_card_for_mulligan(
            card=card,
            hand_state=hand_state,
            legend_synergy_cards=legend_synergy_cards,
            going_first=going_first
        )
        
        # Update state if we kept a 3-cost unit
        if keep and card.energy_cost == 3 and card.card_type == CardType.UNIT:
            kept_any_3_cost_unit = True
            hand_state['kept_any_3_cost_unit'] = True
        
        decisions.append(
            MulliganCardDecision(
                card_id=card.card_id,
                name=card.name,
                keep=keep,
                reason=reason
            )
        )
    
    # CRITICAL: Enforce 2-card mulligan limit
    decisions = _enforce_mulligan_limit(decisions, hand, max_mulligans=2)
    
    # Count final mulligans
    mulligan_count = sum(1 for d in decisions if not d.keep)
    
    # Generate summary
    summary = _generate_mulligan_summary(decisions, composition, mulligan_count)
    
    return MulliganAdvice(
        decisions=decisions, 
        summary=summary,
        mulligan_count=mulligan_count
    )


def evaluate_card_for_mulligan(
    card: CardInHand,
    hand_state: dict,
    legend_synergy_cards: List[str],
    going_first: bool
) -> tuple[bool, str]:
    """
    Evaluate whether to keep or mulligan a single card.
    
    Args:
        card: The card to evaluate
        hand_state: Dictionary with hand composition info:
            - kept_any_3_cost_unit: bool
            - cheap_unit_count: int
            - spell_count: int
            - high_cost_count: int
        legend_synergy_cards: List of card IDs that synergize with legend
        going_first: Whether player is going first
    
    Returns:
        (keep: bool, reason: str)
    """
    cost = card.energy_cost
    ctype = card.card_type
    has_legend_synergy = card.card_id in legend_synergy_cards
    
    # === UNITS ===
    if ctype == CardType.UNIT:
        return _evaluate_unit(card, hand_state, has_legend_synergy, going_first)
    
    # === SPELLS & GEAR ===
    else:
        return _evaluate_non_unit(card, hand_state, has_legend_synergy)


def _evaluate_unit(
    card: CardInHand, 
    hand_state: dict, 
    has_legend_synergy: bool,
    going_first: bool
) -> tuple[bool, str]:
    """Evaluate unit cards for mulligan."""
    cost = card.energy_cost
    
    # Cheap units (0-2 cost) - almost always keep
    if cost <= 2:
        if card.keywords:
            important_keywords = [
                k for k in card.keywords 
                if k.lower() in ["assault", "guard", "ambush", "flying"]
            ]
            if important_keywords:
                return True, f"Cheap unit with {', '.join(important_keywords)}: excellent early pressure."
        
        return True, "Cheap unit (cost ≤ 2): essential for early board presence."
    
    # 3-cost units - keep first one, mulligan rest
    elif cost == 3:
        if not hand_state['kept_any_3_cost_unit']:
            # Evaluate quality of the 3-drop
            if card.might and card.might >= 3:
                return True, "Strong 3-cost unit: solid curve topper with good stats."
            elif card.keywords:
                return True, f"3-cost unit with keywords: good curve play."
            else:
                return True, "3-cost unit: acceptable curve topper for opening hand."
        else:
            return False, "Additional 3-cost unit: too heavy, need cheaper plays."
    
    # 4+ cost units - generally mulligan unless special
    else:
        if has_legend_synergy:
            return True, f"High-cost unit ({cost}) with legend synergy: worth the investment."
        
        # Exception: If going second and it's a strong 4-drop, might keep
        if not going_first and cost == 4 and card.might and card.might >= 4:
            if hand_state['cheap_unit_count'] >= 2:
                return True, "Strong 4-drop and going second with early game: acceptable curve top."
        
        return False, f"High-cost unit ({cost}): too expensive for opening hand."


def _evaluate_non_unit(
    card: CardInHand, 
    hand_state: dict, 
    has_legend_synergy: bool
) -> tuple[bool, str]:
    """Evaluate spell/gear cards for mulligan."""
    cost = card.energy_cost
    tags_lower = [t.lower() for t in (card.tags or [])]
    
    # Free spells - always keep
    if cost == 0:
        return True, "Zero-cost spell: free value, always keep."
    
    # 1-cost spells - usually keep
    if cost == 1:
        if "removal" in tags_lower or "destroy" in tags_lower:
            return True, "Cheap removal (cost 1): answers early threats."
        elif "draw" in tags_lower:
            return True, "Cheap card draw: helps find better cards."
        else:
            return True, "Cheap utility (cost 1): flexible early game."
    
    # 2-cost spells - conditional
    if cost == 2:
        if "removal" in tags_lower or "destroy" in tags_lower:
            return True, "Cheap removal spell: answers early threats."
        
        if has_legend_synergy:
            return True, "2-cost spell with legend synergy: enables combos."
        
        # Too spell-heavy hand?
        if hand_state['spell_count'] >= 3 and hand_state['cheap_unit_count'] == 0:
            return False, "Too many spells: need units for board presence."
        
        return True, "Cheap utility spell: acceptable in balanced hand."
    
    # 3+ cost spells - usually mulligan
    if has_legend_synergy:
        return True, f"Expensive spell ({cost}) with legend synergy: worth keeping for combo."
    
    # Critical removal might be worth keeping
    if cost == 3 and ("removal" in tags_lower or "destroy" in tags_lower):
        if hand_state['cheap_unit_count'] >= 2:
            return True, "Mid-cost removal with early game: can answer mid-game threats."
    
    # Too top-heavy?
    if hand_state['high_cost_count'] >= 2 and hand_state['cheap_unit_count'] == 0:
        return False, f"Expensive spell ({cost}) in top-heavy hand: need cheaper plays."
    
    return False, f"Expensive spell/gear ({cost}): too slow for opening hand."

def analyze_hand_composition(hand: List[CardInHand]) -> dict:
    """
    Analyze the composition of the hand for mulligan decisions.
    
    Returns dictionary with:
        - unit_count: Total units
        - cheap_unit_count: Units costing ≤2
        - spell_count: Total spells
        - gear_count: Total gear
        - high_cost_count: Cards costing ≥4
        - avg_cost: Average energy cost
        - has_curve: Whether hand has good mana curve
    """
    unit_count = sum(1 for c in hand if c.card_type == CardType.UNIT)
    cheap_unit_count = sum(
        1 for c in hand 
        if c.card_type == CardType.UNIT and c.energy_cost <= 2
    )
    spell_count = sum(1 for c in hand if c.card_type == CardType.SPELL)
    gear_count = sum(1 for c in hand if c.card_type == CardType.GEAR)
    high_cost_count = sum(1 for c in hand if c.energy_cost >= 4)
    
    total_cost = sum(c.energy_cost for c in hand)
    avg_cost = total_cost / len(hand) if hand else 0
    
    # Simple curve check: do we have plays for turns 1-3?
    cost_distribution = {i: 0 for i in range(5)}
    for c in hand:
        cost = min(c.energy_cost, 4)  # Cap at 4+ for simplicity
        cost_distribution[cost] += 1
    
    has_curve = (
        cost_distribution[1] + cost_distribution[2] >= 2 and
        cost_distribution[3] >= 1
    )
    
    return {
        'unit_count': unit_count,
        'cheap_unit_count': cheap_unit_count,
        'spell_count': spell_count,
        'gear_count': gear_count,
        'high_cost_count': high_cost_count,
        'avg_cost': avg_cost,
        'has_curve': has_curve,
        'cost_distribution': cost_distribution,
    }


def identify_legend_synergies(
    hand: List[CardInHand], 
    legend_card: Optional[CardRecord]
) -> List[str]:
    """
    Identify which cards in hand synergize with the player's legend.
    
    Returns list of card IDs that have synergy.
    """
    if not legend_card:
        return []
    
    synergy_cards = []
    legend_name_lower = legend_card.name.lower()
    legend_domain = legend_card.domain.lower() if legend_card.domain else ""
    
    for card in hand:
        has_synergy = False
        
        # Check if card mentions legend by name
        if card.rules_text and legend_name_lower in card.rules_text.lower():
            has_synergy = True
        
        # Check domain synergy (e.g., "Choose a Shadow card...")
        if legend_domain and card.rules_text:
            if legend_domain in card.rules_text.lower():
                has_synergy = True
        
        # Check tag-based synergy
        if legend_card.tags and card.tags:
            legend_tags = {t.lower() for t in legend_card.tags}
            card_tags = {t.lower() for t in card.tags}
            # If card cares about legend's tribes/tags
            if legend_tags & card_tags:  # Set intersection
                has_synergy = True
        
        if has_synergy:
            synergy_cards.append(card.card_id)
    
    return synergy_cards  


def _enforce_mulligan_limit(
    decisions: List[MulliganCardDecision],
    hand: List[CardInHand],
    max_mulligans: int = 2
) -> List[MulliganCardDecision]:
    """
    Enforce Riftbound's maximum mulligan limit (2 cards).
    
    If more than 2 cards are marked for mulligan, keep only the worst 2
    and adjust the rest to "keep" with updated reasons.
    """
    to_mulligan = [d for d in decisions if not d.keep]
    to_keep = [d for d in decisions if d.keep]
    
    # If we're within the limit, no adjustment needed
    if len(to_mulligan) <= max_mulligans:
        # Special case: never mulligan all 4 cards
        if len(to_mulligan) == 4:
            # Keep the cheapest card
            cheapest = min(
                decisions,
                key=lambda d: next(
                    (c.energy_cost for c in hand if c.card_id == d.card_id), 99
                )
            )
            cheapest.keep = True
            cheapest.reason = "Keeping cheapest card (cannot mulligan entire hand)."
            return decisions
        return decisions
    
    # More than max_mulligans cards need mulliganing
    # Prioritize which cards to mulligan based on "mulligan priority score"
    mulligan_priority = []
    for decision in to_mulligan:
        card = next((c for c in hand if c.card_id == decision.card_id), None)
        if not card:
            continue
        
        # Higher score = higher priority to mulligan
        priority = _calculate_mulligan_priority(card)
        mulligan_priority.append((priority, decision, card))
    
    # Sort by priority (highest first = worst cards)
    mulligan_priority.sort(key=lambda x: x[0], reverse=True)
    
    # Keep only top `max_mulligans` for mulliganing
    final_mulligans = mulligan_priority[:max_mulligans]
    forced_keeps = mulligan_priority[max_mulligans:]
    
    # Update decisions: forced keeps need updated reasons
    for _, decision, card in forced_keeps:
        decision.keep = True
        decision.reason = (
            f"Originally suggested mulligan, but kept due to 2-card mulligan limit. "
            f"({card.name} is expensive but less critical to replace than others)."
        )
    
    return decisions


def _calculate_mulligan_priority(card: CardInHand) -> float:
    """
    Calculate mulligan priority score for a card.
    Higher score = higher priority to mulligan (worse card to keep).
    
    Factors:
    - Cost (higher cost = higher priority)
    - Card type (expensive spells > expensive units)
    - Stats (low might units = higher priority)
    """
    score = 0.0
    
    # Base cost priority
    score += card.energy_cost * 10
    
    # Type modifiers
    if card.card_type == CardType.SPELL:
        score += 5  # Slightly prioritize mulliganing expensive spells
    elif card.card_type == CardType.GEAR:
        score += 3
    
    # Unit-specific: low might units are worse
    if card.card_type == CardType.UNIT:
        if card.might is not None and card.might < card.energy_cost:
            score += 5  # Poor stats for cost
    
    # Cards without keywords are less valuable
    if not card.keywords or len(card.keywords) == 0:
        score += 2
    
    return score


def _generate_mulligan_summary(
    decisions: List[MulliganCardDecision],
    composition: dict,
    mulligan_count: int
) -> str:
    """Generate a human-readable summary of mulligan decisions."""
    kept = [d for d in decisions if d.keep]
    tossed = [d for d in decisions if not d.keep]
    
    summary_parts = []
    
    # Main decision summary
    if mulligan_count == 0:
        summary_parts.append("Keep all 4 cards")
    elif mulligan_count == 1:
        summary_parts.append(f"Mulligan 1 card, keeping 3")
    else:
        summary_parts.append(f"Mulligan {mulligan_count} cards (maximum allowed)")
    
    # Curve assessment
    avg_cost = composition['avg_cost']
    if avg_cost <= 2.0:
        summary_parts.append("aggressive early curve")
    elif avg_cost <= 2.5:
        summary_parts.append("balanced curve")
    elif avg_cost <= 3.0:
        summary_parts.append("slightly top-heavy")
    else:
        summary_parts.append("seeking cheaper plays")
    
    return " - ".join(summary_parts) + "."

