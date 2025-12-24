# mulligan_advisor.py

from typing import List, Optional, Tuple
from game_state import CardInHand, CardType, Rune
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
    - Each mulliganed card is shuffled back and replaced with a new draw
    
    Strategy:
    - Prioritize early board presence (1-2 cost units)
    - Keep exactly one 3-cost unit as curve topper
    - Mulligan most 4+ cost cards unless they have synergy
    - Value cheap interaction (removal, combat tricks)
    - Consider rune curve (can you cast your cards on curve?)
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
    
    # Analyze rune availability (can we cast our cards?)
    rune_analysis = analyze_rune_curve(hand, legend_card)
    
    # Initialize state tracking
    decisions: List[MulliganCardDecision] = []
    hand_state = {
        'kept_any_3_cost_unit': False,
        'cheap_unit_count': composition['cheap_unit_count'],
        'spell_count': composition['spell_count'],
        'gear_count': composition['gear_count'],
        'high_cost_count': composition['high_cost_count'],
        'removal_count': composition['removal_count'],
        'rune_dead_cards': rune_analysis['dead_cards'],
    }
    
    # Evaluate each card
    for card in hand:
        keep, reason = evaluate_card_for_mulligan(
            card=card,
            hand_state=hand_state,
            legend_synergy_cards=legend_synergy_cards,
            rune_analysis=rune_analysis,
            going_first=going_first
        )
        
        # Update state if we kept a 3-cost unit
        if keep and card.energy_cost == 3 and card.card_type == CardType.UNIT:
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
    
    # CRITICAL: Never mulligan all 4 cards
    decisions = _ensure_keep_at_least_one(decisions, hand)
    
    # Count final mulligans
    mulligan_count = sum(1 for d in decisions if not d.keep)
    
    # Generate summary
    summary = _generate_mulligan_summary(decisions, composition, mulligan_count, rune_analysis)
    
    return MulliganAdvice(
        decisions=decisions, 
        summary=summary,
        mulligan_count=mulligan_count
    )


def evaluate_card_for_mulligan(
    card: CardInHand,
    hand_state: dict,
    legend_synergy_cards: List[str],
    rune_analysis: dict,
    going_first: bool
) -> Tuple[bool, str]:
    """
    Evaluate whether to keep or mulligan a single card.
    
    Args:
        card: The card to evaluate
        hand_state: Dictionary with hand composition info
        legend_synergy_cards: List of card IDs that synergize with legend
        rune_analysis: Dictionary with rune curve analysis
        going_first: Whether player is going first
    
    Returns:
        (keep: bool, reason: str)
    """
    cost = card.energy_cost
    ctype = card.card_type
    has_legend_synergy = card.card_id in legend_synergy_cards
    is_rune_dead = card.card_id in hand_state.get('rune_dead_cards', [])
    
    # Check for rune curve issues
    if is_rune_dead and cost >= 3:
        return False, f"Off-domain expensive card ({cost} cost): difficult to cast early."
    
    # === UNITS ===
    if ctype == CardType.UNIT:
        return _evaluate_unit(card, hand_state, has_legend_synergy, going_first, is_rune_dead)
    
    # === SPELLS & GEAR ===
    else:
        return _evaluate_non_unit(card, hand_state, has_legend_synergy, is_rune_dead)


def _evaluate_unit(
    card: CardInHand, 
    hand_state: dict, 
    has_legend_synergy: bool,
    going_first: bool,
    is_rune_dead: bool
) -> Tuple[bool, str]:
    """Evaluate unit cards for mulligan."""
    from ability_parser import AbilityType
    
    # Ensure abilities are parsed
    if not card.parsed_abilities and card.rules_text:
        card.parse_abilities()
    
    cost = card.energy_cost
    might = card.might or 0
    
    # Cheap units (0-2 cost) - highest priority keeps
    if cost <= 2:
        # NEW: Check for ETB abilities (extra valuable)
        has_etb = any(
            a.ability_type == AbilityType.ENTERS_BATTLEFIELD
            for a in card.parsed_abilities
        )
        
        if has_etb:
            return True, f"Cheap unit with enters-battlefield effect: excellent early value."
        
        # Check for premium keywords
        premium_keywords = _get_premium_keywords(card.keywords)
        
        if premium_keywords:
            return True, f"Cheap unit with {', '.join(premium_keywords)}: excellent early pressure."
        
        # Efficient stats check (might >= cost is good for cheap units)
        if might >= cost + 1:
            return True, f"Efficient cheap unit ({might} might for {cost} cost): strong early play."
        
        return True, "Cheap unit (cost ≤ 2): essential for early board presence."
    
    # 3-cost units - keep first one, mulligan rest
    elif cost == 3:
        if not hand_state['kept_any_3_cost_unit']:
            # NEW: Check for static buffs (lord effects)
            has_lord_effect = any(
                a.ability_type == AbilityType.STATIC_BUFF
                for a in card.parsed_abilities
            )
            
            if has_lord_effect:
                return True, "3-cost static effect: builds around other units - keep for synergy."
            
            # Evaluate quality of the 3-drop
            if might >= 3:
                return True, "Strong 3-cost unit: solid curve topper with good stats."
            elif card.keywords and len(card.keywords) > 0:
                return True, f"3-cost unit with keywords: valuable curve play."
            else:
                # Mediocre 3-drop, but might keep if no other options
                if hand_state['cheap_unit_count'] >= 2:
                    return True, "3-cost unit: acceptable curve topper with early plays."
                else:
                    return False, "Weak 3-cost unit without early support: seeking better curve."
        else:
            return False, "Additional 3-cost unit: too heavy, need cheaper plays."
    
    # 4+ cost units - generally mulligan unless exceptional
    else:
        # Strong legend synergy can save expensive cards
        if has_legend_synergy:
            return True, f"High-cost unit ({cost}) with legend synergy: enables powerful combos."
        
        # Bomb-level stats or keywords
        if might >= cost + 2:  # Very efficient
            if hand_state['cheap_unit_count'] >= 2:
                return True, f"Premium unit ({might}/{might} for {cost}): worth keeping with early curve."
        
        # Premium keywords on expensive units
        premium_keywords = _get_premium_keywords(card.keywords)
        if premium_keywords and len(premium_keywords) >= 2:
            if hand_state['cheap_unit_count'] >= 2:
                return True, f"High-impact unit with {', '.join(premium_keywords)}: game-ending threat."
        
        # Going second with strong 4-drop and early game
        if not going_first and cost == 4 and might >= 4:
            if hand_state['cheap_unit_count'] >= 2:
                return True, "Strong 4-drop going second with early game: acceptable curve top."
        
        return False, f"High-cost unit ({cost}): too expensive for opening hand."


def _evaluate_non_unit(
    card: CardInHand, 
    hand_state: dict, 
    has_legend_synergy: bool,
    is_rune_dead: bool
) -> Tuple[bool, str]:
    """Evaluate spell/gear cards for mulligan. NOW WITH ABILITY PARSING."""
    from ability_parser import AbilityType, EffectTarget, EffectTiming
    
    # Ensure abilities are parsed
    if not card.parsed_abilities and card.rules_text:
        card.parse_abilities()
    
    cost = card.energy_cost
    tags_lower = [t.lower() for t in (card.tags or [])]
    keywords_lower = [k.lower() for k in (card.keywords or [])]
    
    # === NEW: Parse ability types ===
    ability_types = {a.ability_type for a in card.parsed_abilities}
    
    # Identify card function via PARSED ABILITIES (more accurate than tags!)
    is_removal = any(
        t in ability_types 
        for t in [AbilityType.DESTROY, AbilityType.DAMAGE, AbilityType.EXILE, AbilityType.BOUNCE]
    )
    
    is_draw = AbilityType.DRAW_CARDS in ability_types
    
    is_combat_trick = any(
        a.timing == EffectTiming.INSTANT or 
        a.ability_type in {AbilityType.BUFF_TARGET, AbilityType.BUFF_SELF}
        for a in card.parsed_abilities
    ) or any(kw in keywords_lower for kw in ['ambush', 'fast'])
    
    is_board_wipe = any(
        a.ability_type == AbilityType.DESTROY and
        a.effect_target in {EffectTarget.ALL_UNITS, EffectTarget.OPPONENT_UNITS}
        for a in card.parsed_abilities
    )
    
    # NEW: Check for powerful ETB enablers (for gear)
    enables_etb = card.card_type == CardType.GEAR and any(
        a.ability_type in {AbilityType.BUFF_TARGET, AbilityType.BUFF_SELF}
        for a in card.parsed_abilities
    )
    
    # Fallback to tags if no parsed abilities (shouldn't happen, but safe)
    if not card.parsed_abilities:
        is_removal = any(tag in tags_lower for tag in ['removal', 'destroy', 'damage'])
        is_draw = 'draw' in tags_lower or 'cycle' in tags_lower
    
    # === FREE SPELLS (0 cost) ===
    if cost == 0:
        if is_removal:
            return True, "Zero-cost removal: free answer, always keep."
        elif is_draw:
            return True, "Zero-cost card draw: free card advantage, always keep."
        else:
            return True, "Zero-cost spell: free value, always keep."
    
    # === 1-COST SPELLS ===
    if cost == 1:
        if is_removal:
            # Check damage value if available
            damage_abilities = [
                a for a in card.parsed_abilities 
                if a.ability_type == AbilityType.DAMAGE
            ]
            if damage_abilities and damage_abilities[0].effect_value:
                damage = damage_abilities[0].effect_value
                return True, f"Cheap removal dealing {damage} damage: answers early threats."
            else:
                return True, "Cheap removal (cost 1): answers early threats."
        
        elif is_draw:
            draw_count = next(
                (a.effect_value for a in card.parsed_abilities 
                 if a.ability_type == AbilityType.DRAW_CARDS),
                1
            )
            if draw_count >= 2:
                return True, f"Cheap cantrip drawing {draw_count} cards: excellent card advantage."
            else:
                return True, "Cheap card draw: helps find better cards."
        
        elif is_combat_trick:
            return True, "Fast spell (cost 1): flexible combat trick for early trades."
        
        else:
            return True, "Cheap utility (cost 1): flexible early game."
    
    # === 2-COST SPELLS ===
    if cost == 2:
        if is_removal:
            # Check if it's high-quality removal
            destroy_abilities = [
                a for a in card.parsed_abilities 
                if a.ability_type == AbilityType.DESTROY
            ]
            
            if destroy_abilities:
                return True, "Cheap unconditional removal: critical interaction for any threat."
            
            # Check damage value
            damage_abilities = [
                a for a in card.parsed_abilities 
                if a.ability_type == AbilityType.DAMAGE
            ]
            
            if damage_abilities and damage_abilities[0].effect_value:
                damage = damage_abilities[0].effect_value
                if damage >= 3:
                    return True, f"Efficient removal ({damage} damage): handles most early threats."
            
            return True, "Cheap removal: critical interaction for early board."
        
        if is_draw:
            draw_count = next(
                (a.effect_value for a in card.parsed_abilities 
                 if a.ability_type == AbilityType.DRAW_CARDS),
                1
            )
            
            if hand_state['spell_count'] <= 2:
                return True, f"Card draw ({draw_count} cards): helps smooth draws and find threats."
            elif draw_count >= 2:
                return True, f"Strong card draw ({draw_count} cards): worth keeping despite spell count."
        
        if has_legend_synergy:
            return True, "2-cost spell with legend synergy: enables combos."
        
        # NEW: Gear evaluation based on parsed abilities
        if card.card_type == CardType.GEAR:
            if hand_state['cheap_unit_count'] >= 1:
                # Check buff value
                buff_abilities = [
                    a for a in card.parsed_abilities
                    if a.ability_type in {AbilityType.BUFF_TARGET, AbilityType.BUFF_SELF}
                ]
                
                if buff_abilities and buff_abilities[0].effect_value:
                    buff = buff_abilities[0].effect_value
                    return True, f"Cheap gear (+{buff} buff) with units: creates strong early threats."
                
                # Check for keyword grants
                keyword_grants = []
                for a in card.parsed_abilities:
                    if a.keywords_granted:
                        keyword_grants.extend(a.keywords_granted)
                
                if keyword_grants:
                    keywords_str = ', '.join(keyword_grants[:2])
                    return True, f"Cheap gear granting {keywords_str}: powerful with early units."
                
                return True, "Cheap gear with units: creates strong early threats."
        
        # Too spell-heavy or no board presence?
        if hand_state['spell_count'] >= 2 and hand_state['cheap_unit_count'] == 0:
            return False, "Spell in unit-light hand: need board presence first."
        
        return True, "Cheap utility: acceptable in balanced hand."
    
    # === 3+ COST SPELLS ===
    
    # Always keep if strong legend synergy
    if has_legend_synergy:
        return True, f"Expensive spell ({cost}) with legend synergy: worth keeping for combo."
    
    # NEW: Board wipes are keepable with early game
    if is_board_wipe and cost <= 4:
        if hand_state['cheap_unit_count'] >= 2:
            return True, f"Board wipe ({cost} cost) with early curve: nuclear option against wide boards."
    
    # Critical removal at 3-4 cost
    if cost <= 4 and is_removal:
        if hand_state['cheap_unit_count'] >= 2 and hand_state['removal_count'] == 0:
            # Check removal quality
            has_destroy = AbilityType.DESTROY in ability_types
            
            damage_abilities = [
                a for a in card.parsed_abilities 
                if a.ability_type == AbilityType.DAMAGE
            ]
            high_damage = any(
                a.effect_value and a.effect_value >= 4 
                for a in damage_abilities
            )
            
            if has_destroy:
                return True, f"Unconditional removal ({cost} cost) with early curve: answers any threat."
            elif high_damage:
                damage_val = next(a.effect_value for a in damage_abilities if a.effect_value)
                return True, f"High-damage removal ({damage_val} damage) with early curve: kills big threats."
            else:
                return True, f"Mid-cost removal ({cost} cost) with early curve: handles mid-game threats."
    
    # Combat tricks that can swing combat
    if cost == 3 and is_combat_trick:
        if hand_state['cheap_unit_count'] >= 2:
            # Check buff value
            buff_abilities = [
                a for a in card.parsed_abilities
                if a.ability_type in {AbilityType.BUFF_TARGET, AbilityType.BUFF_SELF}
            ]
            
            if buff_abilities and buff_abilities[0].effect_value:
                buff = buff_abilities[0].effect_value
                return True, f"Combat trick (+{buff} buff) with early units: creates favorable trades."
            
            return True, "Combat trick with early units: creates favorable trades."
    
    # NEW: Card draw at 3+ cost is keepable in specific scenarios
    if is_draw and cost <= 4:
        draw_count = next(
            (a.effect_value for a in card.parsed_abilities 
             if a.ability_type == AbilityType.DRAW_CARDS),
            1
        )
        
        if draw_count >= 3:
            if hand_state['cheap_unit_count'] >= 1:
                return True, f"Powerful card draw ({draw_count} cards): worth keeping for refill."
    
    # NEW: Protection spells
    has_protection = AbilityType.PROTECTION in ability_types
    if has_protection and cost <= 3:
        if hand_state['cheap_unit_count'] >= 2:
            return True, f"Protection spell ({cost} cost) with early units: keeps threats alive."
    
    # Too top-heavy?
    if hand_state['high_cost_count'] >= 2:
        return False, f"Expensive spell ({cost}) in top-heavy hand: need cheaper plays."
    
    # No early game support
    if hand_state['cheap_unit_count'] == 0 and cost >= 3:
        return False, f"Expensive spell without early game: seeking cheaper plays."
    
    # Expensive gear without targets
    if card.card_type == CardType.GEAR and hand_state['cheap_unit_count'] == 0:
        return False, f"Expensive gear ({cost}) without units: need targets first."
    
    return False, f"Expensive spell/gear ({cost}): too slow for opening hand."


def analyze_hand_composition(hand: List[CardInHand]) -> dict:
    """
    Analyze the composition of the hand for mulligan decisions.
    NOW ENHANCED with ability parsing for accurate card categorization.
    
    Returns dictionary with detailed hand metrics.
    """
    from ability_parser import AbilityType, EffectTiming
    
    # Ensure all cards have parsed abilities
    for card in hand:
        if not card.parsed_abilities and card.rules_text:
            card.parse_abilities()
    
    unit_count = sum(1 for c in hand if c.card_type == CardType.UNIT)
    cheap_unit_count = sum(
        1 for c in hand 
        if c.card_type == CardType.UNIT and c.energy_cost <= 2
    )
    spell_count = sum(1 for c in hand if c.card_type == CardType.SPELL)
    gear_count = sum(1 for c in hand if c.card_type == CardType.GEAR)
    high_cost_count = sum(1 for c in hand if c.energy_cost >= 4)
    
    # === NEW: Count removal via PARSED ABILITIES (more accurate!) ===
    removal_types = {
        AbilityType.DESTROY,
        AbilityType.DAMAGE,
        AbilityType.EXILE,
        AbilityType.BOUNCE
    }
    
    removal_count = sum(
        1 for c in hand 
        if c.card_type in [CardType.SPELL, CardType.GEAR] and
        any(a.ability_type in removal_types for a in c.parsed_abilities)
    )
    
    # === NEW: Count card draw ===
    draw_count = sum(
        1 for c in hand
        if any(a.ability_type == AbilityType.DRAW_CARDS for a in c.parsed_abilities)
    )
    
    # === NEW: Count combat tricks (instant-speed interaction) ===
    combat_trick_count = sum(
        1 for c in hand
        if any(
            a.timing == EffectTiming.INSTANT or
            (a.ability_type in {AbilityType.BUFF_TARGET, AbilityType.BUFF_SELF} and
             any(k.lower() in ['fast', 'ambush'] for k in (c.keywords or [])))
            for a in c.parsed_abilities
        )
    )
    
    # === NEW: Count ETB units ===
    etb_unit_count = sum(
        1 for c in hand
        if c.card_type == CardType.UNIT and
        any(a.ability_type == AbilityType.ENTERS_BATTLEFIELD for a in c.parsed_abilities)
    )
    
    # === NEW: Count lord effects (static buffs) ===
    lord_count = sum(
        1 for c in hand
        if any(a.ability_type == AbilityType.STATIC_BUFF for a in c.parsed_abilities)
    )
    
    total_cost = sum(c.energy_cost for c in hand)
    avg_cost = total_cost / len(hand) if hand else 0
    
    # Curve distribution
    cost_distribution = {i: 0 for i in range(6)}
    for c in hand:
        cost = min(c.energy_cost, 5)
        cost_distribution[cost] += 1
    
    # Curve quality assessment
    has_1_drop = cost_distribution[1] >= 1
    has_2_drop = cost_distribution[2] >= 1
    has_3_drop = cost_distribution[3] >= 1
    has_curve = (has_1_drop or has_2_drop) and has_3_drop
    
    return {
        'unit_count': unit_count,
        'cheap_unit_count': cheap_unit_count,
        'spell_count': spell_count,
        'gear_count': gear_count,
        'high_cost_count': high_cost_count,
        'removal_count': removal_count,
        'draw_count': draw_count,  # NEW
        'combat_trick_count': combat_trick_count,  # NEW
        'etb_unit_count': etb_unit_count,  # NEW
        'lord_count': lord_count,  # NEW
        'avg_cost': avg_cost,
        'has_curve': has_curve,
        'cost_distribution': cost_distribution,
        'has_1_drop': has_1_drop,
        'has_2_drop': has_2_drop,
        'has_3_drop': has_3_drop,
    }


def analyze_rune_curve(hand: List[CardInHand], legend_card: Optional[CardRecord]) -> dict:
    """
    Analyze whether the hand has good rune curve.
    
    In Riftbound, you need matching domain/rune cards to generate runes.
    A card is "dead" if you can't reliably cast it on curve.
    
    Returns:
        - dead_cards: List of card IDs that are off-domain and expensive
        - rune_sources: Count of cards that generate each rune type
        - castable_on_curve: Whether hand has good rune distribution
    """
    legend_domain = legend_card.domain if legend_card else None
    
    # Count rune sources by domain
    rune_sources = {}
    for card in hand:
        domain = card.domain
        if domain not in rune_sources:
            rune_sources[domain] = 0
        rune_sources[domain] += 1
    
    # Add legend's domain
    if legend_domain:
        if legend_domain not in rune_sources:
            rune_sources[legend_domain] = 0
        rune_sources[legend_domain] += 1
    
    # Identify cards that are hard to cast (off-domain + expensive)
    dead_cards = []
    for card in hand:
        if card.energy_cost >= 3:
            # Check if we have rune sources for this card
            card_rune_sources = rune_sources.get(card.domain, 0)
            
            # If this card is our only source of its domain, it might be dead
            if card_rune_sources <= 1:
                dead_cards.append(card.card_id)
    
    # Assess overall castability
    total_rune_sources = sum(rune_sources.values())
    unique_domains = len(rune_sources)
    
    castable_on_curve = (
        total_rune_sources >= 3 and  # Enough rune generation
        (unique_domains <= 2 or total_rune_sources >= 4)  # Not too spread out
    )
    
    return {
        'dead_cards': dead_cards,
        'rune_sources': rune_sources,
        'castable_on_curve': castable_on_curve,
        'unique_domains': unique_domains,
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
    legend_name_lower = legend_card.name.lower() if legend_card.name else ""
    legend_domain_lower = legend_card.domain.lower() if legend_card.domain else ""
    
    for card in hand:
        has_synergy = False
        
        # Check if card mentions legend by name in rules text
        if card.rules_text and legend_name_lower:
            if legend_name_lower in card.rules_text.lower():
                has_synergy = True
        
        # Check domain synergy (cards that care about specific domains)
        if legend_domain_lower and card.rules_text:
            # Look for domain-specific text like "Choose a Fury card"
            if legend_domain_lower in card.rules_text.lower():
                has_synergy = True
        
        # Check tag-based synergy (tribal synergies)
        if legend_card.tags and card.tags:
            legend_tags = {t.lower() for t in legend_card.tags}
            card_tags = {t.lower() for t in card.tags}
            # If both share a tribal tag, there's potential synergy
            if legend_tags & card_tags:
                has_synergy = True
        
        # Check keyword synergies
        if legend_card.keywords and card.rules_text:
            for keyword in legend_card.keywords:
                if keyword.lower() in card.rules_text.lower():
                    has_synergy = True
                    break
        
        if has_synergy:
            synergy_cards.append(card.card_id)
    
    return synergy_cards


def _get_premium_keywords(keywords: List[str]) -> List[str]:
    """Extract premium keywords that significantly impact mulligan value."""
    if not keywords:
        return []
    
    premium = ['assault', 'guard', 'ambush', 'flying', 'lifesteal', 'double strike']
    return [k for k in keywords if k.lower() in premium]


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
    
    # If we're within the limit, no adjustment needed
    if len(to_mulligan) <= max_mulligans:
        return decisions
    
    # More than max_mulligans cards need mulliganing
    # Prioritize which cards to mulligan based on priority score
    mulligan_priority = []
    for decision in to_mulligan:
        card = next((c for c in hand if c.card_id == decision.card_id), None)
        if not card:
            continue
        
        # Higher score = higher priority to mulligan (worse card)
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
            f"Originally suggested mulligan, but kept due to 2-card limit. "
            f"Less critical to replace than other mulliganed cards."
        )
    
    return decisions


def _ensure_keep_at_least_one(
    decisions: List[MulliganCardDecision],
    hand: List[CardInHand]
) -> List[MulliganCardDecision]:
    """
    Ensure at least one card is kept (never mulligan all 4).
    If all 4 are marked for mulligan, keep the best one.
    """
    to_keep = [d for d in decisions if d.keep]
    
    # If we're keeping at least one card, we're good
    if len(to_keep) > 0:
        return decisions
    
    # All 4 marked for mulligan - keep the best one
    # Calculate "keep priority" (inverse of mulligan priority)
    keep_priority = []
    for decision in decisions:
        card = next((c for c in hand if c.card_id == decision.card_id), None)
        if not card:
            continue
        
        priority = -_calculate_mulligan_priority(card)  # Invert for keeping
        keep_priority.append((priority, decision, card))
    
    # Sort by priority (highest = best card to keep)
    keep_priority.sort(key=lambda x: x[0], reverse=True)
    
    # Keep the best card
    best_priority, best_decision, best_card = keep_priority[0]
    best_decision.keep = True
    best_decision.reason = (
        f"Keeping {best_card.name} as best option. "
        f"(Cannot mulligan all 4 cards per game rules)."
    )
    
    return decisions


def _calculate_mulligan_priority(card: CardInHand) -> float:
    """
    Calculate mulligan priority score for a card.
    Higher score = higher priority to mulligan (worse card to keep).
    
    Factors:
    - Cost (higher cost = higher priority to mulligan)
    - Card type (expensive spells > expensive units)
    - Stats efficiency
    - Keywords
    """
    score = 0.0
    
    # Base cost priority (exponential scaling for high costs)
    if card.energy_cost <= 3:
        score += card.energy_cost * 10
    else:
        score += card.energy_cost * 15  # Heavily penalize 4+ cost
    
    # Type modifiers
    if card.card_type == CardType.SPELL:
        score += 5  # Slightly prioritize mulliganing expensive spells
    elif card.card_type == CardType.GEAR:
        score += 3
    
    # Unit-specific evaluation
    if card.card_type == CardType.UNIT and card.might is not None:
        # Poor stats for cost
        if card.might < card.energy_cost:
            score += 10  # Very bad stats
        elif card.might == card.energy_cost:
            score += 3   # Below-rate stats
        # Good stats reduce priority
        elif card.might >= card.energy_cost + 2:
            score -= 5   # Premium stats
    
    # Premium keywords reduce mulligan priority
    premium_keywords = _get_premium_keywords(card.keywords or [])
    score -= len(premium_keywords) * 5
    
    # Cards without any keywords are less valuable
    if not card.keywords or len(card.keywords) == 0:
        score += 3
    
    return score


def _generate_mulligan_summary(
    decisions: List[MulliganCardDecision],
    composition: dict,
    mulligan_count: int,
    rune_analysis: dict
) -> str:
    """Generate a human-readable summary of mulligan decisions. NOW ENHANCED."""
    summary_parts = []
    
    # Main decision summary
    if mulligan_count == 0:
        summary_parts.append("Keep all 4 cards")
    elif mulligan_count == 1:
        summary_parts.append("Mulligan 1 card")
    else:
        summary_parts.append(f"Mulligan {mulligan_count} cards (maximum allowed)")
    
    # Curve assessment
    avg_cost = composition['avg_cost']
    if composition['has_1_drop'] or composition['has_2_drop']:
        if avg_cost <= 2.0:
            summary_parts.append("aggressive early curve")
        elif avg_cost <= 2.5:
            summary_parts.append("good curve")
        else:
            summary_parts.append("acceptable curve")
    else:
        summary_parts.append("seeking early plays")
    
    # === NEW: Special card type callouts ===
    special_features = []
    
    if composition.get('etb_unit_count', 0) > 0:
        special_features.append(f"{composition['etb_unit_count']} ETB effect(s)")
    
    if composition.get('lord_count', 0) > 0:
        special_features.append(f"{composition['lord_count']} lord effect(s)")
    
    if composition.get('removal_count', 0) > 0:
        special_features.append(f"{composition['removal_count']} removal")
    
    if composition.get('combat_trick_count', 0) > 0:
        special_features.append(f"{composition['combat_trick_count']} combat trick(s)")
    
    if composition.get('draw_count', 0) > 0:
        special_features.append(f"{composition['draw_count']} card draw")
    
    if special_features:
        summary_parts.append(f"includes {', '.join(special_features)}")
    
    # Rune curve warning
    if not rune_analysis['castable_on_curve']:
        summary_parts.append("watch rune availability")
    
    # Hand type classification
    if composition['cheap_unit_count'] >= 3:
        summary_parts.append("aggressive tempo hand")
    elif composition.get('lord_count', 0) >= 1 and composition['cheap_unit_count'] >= 1:
        summary_parts.append("synergy-focused hand")
    elif composition.get('removal_count', 0) >= 2:
        summary_parts.append("interactive control hand")
    elif composition['spell_count'] >= 2 and composition['cheap_unit_count'] <= 1:
        summary_parts.append("spell-heavy hand")
    elif composition.get('etb_unit_count', 0) >= 2:
        summary_parts.append("value-oriented hand")
    
    return " - ".join(summary_parts) + "."