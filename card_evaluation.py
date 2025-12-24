# Card evaluation and scoring logic
# card_evaluation.py

from typing import List, Optional, Dict
from game_state import GameState, CardInHand, PlayerState, CardType, Battlefield
from logger_config import advisor_logger, log_card_playability
from legend_analysis import requires_legend_exhaustion, can_exhaust_legend

# Import ability parsing
from ability_parser import (
    AbilityType, EffectTarget, EffectTiming,
    has_ability_type, get_abilities_by_timing, categorize_abilities
)


def get_all_playable_cards(state: GameState) -> List[CardInHand]:
    """
    Get all cards that can actually be played using can_play().
    More accurate than playable_cards_by_mana() as it checks rune requirements.
    """
    me = state.me
    return [c for c in me.hand if can_play(c, me)]


def playable_cards_by_mana(state: GameState) -> List[CardInHand]:
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


def describe_card(card: CardInHand) -> str:
    """Get a human-readable description of a card."""
    cost = card.energy_cost
    t = card.card_type.value
    name = card.name or card.card_id
    return f"{name} ({t}, cost {cost})"


def calculate_card_value(
    card: CardInHand,
    game_phase: str = "mid",
    battlefield_context: Optional[Dict] = None
) -> float:
    """
    Calculate a value score for a card to help prioritize plays.
    NOW ENHANCED with ability parsing for much more accurate evaluation.
    
    Higher score = better value.
    
    Args:
        card: Card to evaluate
        game_phase: "early", "mid", or "late"
        battlefield_context: Dict with board state info (my_units, opponent_units, etc.)
    
    Returns:
        Value score (typically 0-20, but can be higher for exceptional cards)
    """
    score = 0.0
    
    # Ensure abilities are parsed
    if not card.parsed_abilities and card.rules_text:
        card.parse_abilities()
    
    # Default battlefield context
    if battlefield_context is None:
        battlefield_context = {
            'my_units': 0,
            'opponent_units': 0,
            'empty_battlefields': 2,
            'contested_battlefields': 0
        }
    
    # === BASE STATS VALUE ===
    if card.card_type == CardType.UNIT:
        # Base value: might per mana
        if card.might and card.energy_cost > 0:
            efficiency = card.might / card.energy_cost
            score += efficiency * 2.0
            
            # Bonus for efficient units
            if efficiency >= 1.5:
                score += 2.0  # Very efficient
            elif efficiency >= 1.0:
                score += 1.0  # Good efficiency
        elif card.might:
            score += card.might * 2.0
        
        # === KEYWORD VALUE ===
        keywords_lower = [k.lower() for k in card.keywords] if card.keywords else []
        
        keyword_values = {
            'assault': 2.0,      # Offensive pressure
            'guard': 1.5,        # Defensive utility
            'flying': 2.0,       # Hard to block
            'overwhelm': 2.5,    # Push damage through
            'lifesteal': 1.5,    # Sustain
            'quick': 2.0,        # Immediate impact
            'double strike': 3.0, # Very powerful
            'ambush': 1.5,       # Flexibility
            'weaponmaster': 1.0, # Synergy
        }
        
        for keyword in keywords_lower:
            score += keyword_values.get(keyword, 0.5)
        
        # === PARSED ABILITY VALUE (NEW!) ===
        ability_value = _calculate_unit_ability_value(
            card, game_phase, battlefield_context
        )
        score += ability_value
        
        # === COST CURVE BONUS ===
        if card.energy_cost <= 2:
            if game_phase == "early":
                score += 2.0  # Early game loves cheap units
            else:
                score += 1.0
        elif card.energy_cost == 3:
            score += 0.5
    
    elif card.card_type == CardType.SPELL:
        # === SPELL BASE VALUE ===
        # Cheap spells are flexible
        if card.energy_cost <= 2:
            score += 2.0
        elif card.energy_cost == 3:
            score += 1.0
        
        # === PARSED ABILITY VALUE (NEW!) ===
        ability_value = _calculate_spell_ability_value(
            card, game_phase, battlefield_context
        )
        score += ability_value
        
        # === FALLBACK TAG VALUE (for cards without parsed abilities) ===
        if not card.parsed_abilities:
            tags_lower = [t.lower() for t in card.tags] if card.tags else []
            if "removal" in tags_lower:
                score += 3.0
            if "damage" in tags_lower:
                score += 2.0
            if "buff" in tags_lower or "protection" in tags_lower:
                score += 1.5
    
    elif card.card_type == CardType.GEAR:
        # Gear value depends on board presence
        if battlefield_context['my_units'] > 0:
            score += 2.0 + (battlefield_context['my_units'] * 0.5)
        else:
            score += 0.5  # Low value without targets
        
        # Cheap gear is flexible
        if card.energy_cost <= 2:
            score += 1.0
        
        # === PARSED ABILITY VALUE (NEW!) ===
        ability_value = _calculate_gear_ability_value(card, battlefield_context)
        score += ability_value
    
    return max(score, 0.0)


def _calculate_unit_ability_value(
    card: CardInHand,
    game_phase: str,
    battlefield_context: Dict
) -> float:
    """Calculate value from unit's parsed abilities."""
    value = 0.0
    
    for ability in card.parsed_abilities:
        # === ETB ABILITIES (Very valuable!) ===
        if ability.ability_type == AbilityType.ENTERS_BATTLEFIELD:
            value += 3.0  # Base ETB value
            
            # Check what the ETB does
            if ability.ability_type == AbilityType.DRAW_CARDS:
                draw_amount = ability.effect_value or 1
                value += draw_amount * 2.0  # Card advantage is huge
            
            elif ability.ability_type == AbilityType.DAMAGE:
                damage = ability.effect_value or 0
                value += damage * 0.8
                
                # Extra value if it can kill opponent units
                if battlefield_context['opponent_units'] > 0 and damage >= 2:
                    value += 2.0
            
            elif ability.ability_type == AbilityType.DESTROY:
                value += 4.0  # Unconditional removal on ETB is premium
            
            elif ability.ability_type in {AbilityType.BUFF_TARGET, AbilityType.BUFF_ALL}:
                if battlefield_context['my_units'] > 0:
                    value += 2.0
        
        # === STATIC BUFFS (Lord effects) ===
        elif ability.ability_type == AbilityType.STATIC_BUFF:
            buff_value = ability.effect_value or 1
            
            # Value scales with board presence
            if ability.effect_target == EffectTarget.YOUR_UNITS:
                value += battlefield_context['my_units'] * buff_value * 1.5
                
                # Extra value if we have empty battlefields (can develop more)
                if battlefield_context['empty_battlefields'] > 0:
                    value += 2.0  # Room to grow
            
            elif ability.effect_target == EffectTarget.ALL_UNITS:
                # Symmetric buff - less valuable
                value += battlefield_context['my_units'] * buff_value * 0.8
        
        # === ACTIVATED ABILITIES ===
        elif ability.ability_type in {AbilityType.TAP_ABILITY, AbilityType.EXHAUST_ABILITY}:
            value += 1.5  # Repeatable value
            
            # Extra value for powerful effects
            if ability.ability_type == AbilityType.DRAW_CARDS:
                value += 2.0
            elif ability.ability_type == AbilityType.DAMAGE:
                damage = ability.effect_value or 0
                value += damage * 0.5
        
        # === TRIGGERED ABILITIES ===
        elif ability.ability_type == AbilityType.ATTACKS:
            value += 1.5  # Attack triggers are valuable
            
            if game_phase == "early":
                value += 0.5  # Even better early
        
        elif ability.ability_type == AbilityType.DIES:
            value += 1.0  # Death triggers provide resilience
        
        # === PROTECTION ===
        elif ability.ability_type == AbilityType.PROTECTION:
            value += 2.0  # Hard to remove
        
        # === COST REDUCTION ===
        elif ability.ability_type == AbilityType.COST_REDUCTION:
            value += 3.0  # Very powerful effect
    
    return value


def _calculate_spell_ability_value(
    card: CardInHand,
    game_phase: str,
    battlefield_context: Dict
) -> float:
    """Calculate value from spell's parsed abilities."""
    value = 0.0
    
    for ability in card.parsed_abilities:
        # === REMOVAL ===
        if ability.ability_type == AbilityType.DESTROY:
            value += 4.0  # Unconditional removal is premium
            
            # Board wipes are extremely valuable
            if ability.effect_target in {EffectTarget.ALL_UNITS, EffectTarget.OPPONENT_UNITS}:
                if battlefield_context['opponent_units'] >= 2:
                    value += 6.0  # Massive value
        
        elif ability.ability_type == AbilityType.DAMAGE:
            damage = ability.effect_value or 0
            value += damage * 0.8
            
            # Value scales with targets available
            if ability.effect_target == EffectTarget.TARGET_UNIT:
                if battlefield_context['opponent_units'] > 0:
                    value += 2.0
            
            elif ability.effect_target == EffectTarget.ALL_UNITS:
                # Board damage spell
                if battlefield_context['opponent_units'] >= 2:
                    value += 3.0
        
        elif ability.ability_type == AbilityType.BOUNCE:
            value += 2.5  # Tempo play
            
            if battlefield_context['opponent_units'] > 0:
                value += 1.0
        
        # === CARD ADVANTAGE ===
        elif ability.ability_type == AbilityType.DRAW_CARDS:
            draw_amount = ability.effect_value or 1
            value += draw_amount * 2.5  # Card draw is very valuable
            
            if game_phase == "late":
                value += 1.0  # Extra value late game
        
        # === BUFFS ===
        elif ability.ability_type in {AbilityType.BUFF_TARGET, AbilityType.BUFF_SELF}:
            buff_value = ability.effect_value or 1
            
            if battlefield_context['my_units'] > 0:
                value += buff_value * 1.5
                
                # Combat tricks (instant speed buffs)
                if ability.timing == EffectTiming.INSTANT:
                    value += 2.0  # Surprise factor
            else:
                value += 0.5  # Low value without targets
        
        elif ability.ability_type == AbilityType.BUFF_ALL:
            if battlefield_context['my_units'] >= 2:
                value += 4.0  # Massive value with multiple units
        
        # === COUNTERS ===
        elif ability.ability_type == AbilityType.COUNTER:
            value += 3.0  # Interaction is valuable
            
            if ability.timing == EffectTiming.INSTANT:
                value += 1.0
        
        # === PROTECTION ===
        elif ability.ability_type == AbilityType.PROTECTION:
            if battlefield_context['my_units'] > 0:
                value += 2.5
    
    return value


def _calculate_gear_ability_value(
    card: CardInHand,
    battlefield_context: Dict
) -> float:
    """Calculate value from gear's parsed abilities."""
    value = 0.0
    
    # Gear needs targets
    if battlefield_context['my_units'] == 0:
        return 0.0
    
    for ability in card.parsed_abilities:
        # === STAT BUFFS ===
        if ability.ability_type in {AbilityType.BUFF_SELF, AbilityType.BUFF_TARGET}:
            buff_value = ability.effect_value or 1
            value += buff_value * 1.5
        
        # === KEYWORD GRANTS ===
        if ability.keywords_granted:
            for keyword in ability.keywords_granted:
                keyword_lower = keyword.lower()
                
                keyword_values = {
                    'assault': 2.0,
                    'guard': 1.5,
                    'flying': 2.0,
                    'overwhelm': 2.0,
                    'lifesteal': 1.5,
                }
                
                value += keyword_values.get(keyword_lower, 1.0)
        
        # === ACTIVATED ABILITIES ===
        if ability.ability_type in {AbilityType.TAP_ABILITY, AbilityType.EXHAUST_ABILITY}:
            value += 2.0  # Repeatable effects on gear
    
    return value


def assess_threat_level(battlefield_analyses: List[dict], opponent: PlayerState) -> dict:
    """
    Assess the threat level from opponent's board.
    NOW ENHANCED with ability awareness.
    """
    total_opponent_might = sum(b["op_might"] for b in battlefield_analyses)
    contested_count = sum(1 for b in battlefield_analyses if b["state"] == "contested")
    losing_count = sum(1 for b in battlefield_analyses if b["state"] == "losing")
    
    # Find highest threat (largest opponent unit)
    highest_threat = None
    highest_might = 0
    for b in battlefield_analyses:
        if b["op_might"] > highest_might:
            highest_might = b["op_might"]
            highest_threat = b
    
    # === NEW: Check for ability-based threats ===
    ability_threats = []
    
    # This would require opponent board units to be parsed
    # For now, use might-based assessment but flag for future enhancement
    
    threat_level = "low"
    if total_opponent_might >= 10:
        threat_level = "high"
    elif total_opponent_might >= 5:
        threat_level = "medium"
    
    return {
        "threat_level": threat_level,
        "total_opponent_might": total_opponent_might,
        "contested_battlefields": contested_count,
        "losing_battlefields": losing_count,
        "highest_threat": highest_threat,
        "needs_removal": highest_might >= 6,  # Large threats need removal
        "ability_threats": ability_threats,  # For future enhancement
    }


def should_hold_card(
    card: CardInHand,
    state: GameState,
    threat_assessment: dict
) -> bool:
    """
    Determine if a card should be held for a better opportunity.
    NOW ENHANCED with ability awareness.
    
    Returns True if card should be held, False if should play now.
    """
    # Ensure abilities are parsed
    if not card.parsed_abilities and card.rules_text:
        card.parse_abilities()
    
    # Always play cheap cards (cost 0-1) if playable
    if card.energy_cost <= 1:
        return False
    
    # === NEW: Check for instant-speed abilities ===
    instant_abilities = get_abilities_by_timing(card.parsed_abilities, EffectTiming.INSTANT)
    
    if instant_abilities:
        # Hold instant-speed interaction unless high threat
        if threat_assessment["threat_level"] in ["high", "critical"]:
            return False  # Use now
        else:
            return True  # Hold for better opportunity
    
    # === NEW: Check for combat tricks ===
    if card.card_type == CardType.SPELL:
        has_fast = any(k.lower() in ['fast', 'ambush'] for k in (card.keywords or []))
        has_instant_buff = any(
            a.ability_type in {AbilityType.BUFF_TARGET, AbilityType.BUFF_SELF} and
            a.timing == EffectTiming.INSTANT
            for a in card.parsed_abilities
        )
        
        if (has_fast or has_instant_buff) and threat_assessment["threat_level"] == "low":
            return True  # Hold combat tricks
    
    # Hold expensive cards early game unless critical
    if state.turn <= 3 and card.energy_cost >= 4:
        # Exception: critical removal against high threat
        has_removal = any(
            a.ability_type in {AbilityType.DESTROY, AbilityType.DAMAGE, AbilityType.EXILE}
            for a in card.parsed_abilities
        )
        
        if has_removal and threat_assessment["needs_removal"]:
            return False  # Use removal now
        
        # Exception: high-value ETB effects
        has_valuable_etb = any(
            a.ability_type == AbilityType.ENTERS_BATTLEFIELD
            for a in card.parsed_abilities
        )
        
        if has_valuable_etb:
            return False  # ETB value is worth it
        
        return True  # Hold otherwise
    
    # Hold expensive units if we're ahead on board
    if card.card_type == CardType.UNIT and card.energy_cost >= 5:
        from battlefield_analysis import analyze_riftbound_battlefields
        
        # Simple board comparison
        battlefield_analysis = analyze_riftbound_battlefields(state.battlefields)
        
        if battlefield_analysis['my_total_might'] > threat_assessment["total_opponent_might"]:
            return True  # We're ahead, can afford to hold
    
    return False


def calculate_mana_efficiency_score(
    cards: List[CardInHand],
    available_mana: int
) -> float:
    """
    Calculate how efficiently we're using mana.
    Returns a score 0-1 where 1 is perfect efficiency.
    """
    if available_mana == 0:
        return 0.0
    
    total_cost = sum(c.energy_cost for c in cards)
    efficiency = min(total_cost / available_mana, 1.0)
    
    # Bonus for using most/all mana
    if efficiency >= 0.9:
        return 1.0
    elif efficiency >= 0.7:
        return efficiency + 0.1
    else:
        return efficiency


def can_play(card: CardInHand, player: PlayerState) -> bool:
    """Check if a card can be played given the player's current resources."""
    # Check total mana
    if player.mana_total is None:
        log_card_playability(
            advisor_logger,
            card.card_id,
            False,
            "No mana available",
            card_name=card.name,
            energy_cost=card.energy_cost
        )
        return False
    
    # Check energy cost (rune tap cost)
    if card.energy_cost > 0:
        if player.mana_total < card.energy_cost:
            log_card_playability(
                advisor_logger,
                card.card_id,
                False,
                f"Insufficient mana: need {card.energy_cost}, have {player.mana_total}",
                card_name=card.name,
                energy_cost=card.energy_cost,
                available_mana=player.mana_total
            )
            return False
    
    # Check power cost (rune recycle cost)
    if card.power_cost > 0:
        if player.mana_total < card.power_cost:
            log_card_playability(
                advisor_logger,
                card.card_id,
                False,
                f"Insufficient mana for power cost: need {card.power_cost}, have {player.mana_total}",
                card_name=card.name,
                power_cost=card.power_cost,
                available_mana=player.mana_total
            )
            return False
    
    # Check power cost by rune
    if hasattr(card, 'power_cost_by_rune') and card.power_cost_by_rune:
        for rune, cost in card.power_cost_by_rune.items():
            available = player.mana_by_rune.get(rune, 0)
            if available < cost:
                log_card_playability(
                    advisor_logger,
                    card.card_id,
                    False,
                    f"Insufficient {rune} rune: need {cost}, have {available}",
                    card_name=card.name,
                    required_rune=rune,
                    required_cost=cost,
                    available_rune=available
                )
                return False
    
    # Check if card requires legend exhaustion and if legend is available
    if requires_legend_exhaustion(card):
        if not can_exhaust_legend(player):
            log_card_playability(
                advisor_logger,
                card.card_id,
                False,
                "Requires legend exhaustion but legend is not available or exhausted",
                available_mana=player.mana_total,
                legend_status="exhausted" if player.legend and player.legend.exhausted else "unavailable"
            )
            return False
    
    log_card_playability(
        advisor_logger,
        card.card_id,
        True,
        "Card is playable",
        card_name=card.name,
        energy_cost=card.energy_cost,
        available_mana=player.mana_total
    )
    return True


def estimate_card_threat_level(card: CardInHand, for_opponent: bool = False) -> int:
    """
    Estimate how threatening a card is (0-10 scale).
    NOW ENHANCED with ability parsing.
    
    Args:
        card: Card to evaluate
        for_opponent: If True, evaluate threat TO opponent; if False, evaluate threat FROM opponent
    
    Returns:
        Threat score 0-10
    """
    # Ensure abilities are parsed
    if not card.parsed_abilities and card.rules_text:
        card.parse_abilities()
    
    threat = 0
    
    # Base threat from stats
    if card.card_type == CardType.UNIT and card.might:
        threat += min(card.might, 5)  # Cap at 5 from stats
    
    # === ABILITY-BASED THREAT (NEW!) ===
    for ability in card.parsed_abilities:
        # Removal is high threat
        if ability.ability_type in {AbilityType.DESTROY, AbilityType.DAMAGE, AbilityType.EXILE}:
            threat += 3
            
            if ability.effect_value and ability.effect_value >= 4:
                threat += 1  # High damage removal
        
        # Board wipes
        if ability.ability_type == AbilityType.DESTROY:
            if ability.effect_target in {EffectTarget.ALL_UNITS, EffectTarget.OPPONENT_UNITS}:
                threat += 4  # Board wipes are very threatening
        
        # ETB abilities add threat
        if ability.ability_type == AbilityType.ENTERS_BATTLEFIELD:
            threat += 2
        
        # Cost reduction / card advantage
        if ability.ability_type in {AbilityType.COST_REDUCTION, AbilityType.DRAW_CARDS}:
            threat += 2
        
        # Static buffs (lord effects)
        if ability.ability_type == AbilityType.STATIC_BUFF:
            threat += 2
        
        # Activated abilities that generate value
        if ability.ability_type in {AbilityType.TAP_ABILITY, AbilityType.EXHAUST_ABILITY}:
            if ability.ability_type == AbilityType.DRAW_CARDS:
                threat += 2
            else:
                threat += 1
    
    # Keywords add threat
    if card.keywords:
        threatening_keywords = {'assault', 'overwhelm', 'double strike', 'flying'}
        keyword_threat = sum(
            1 for k in card.keywords
            if k.lower() in threatening_keywords
        )
        threat += keyword_threat
    
    return min(threat, 10)  # Cap at 10

