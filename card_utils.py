# card_utils.py
# Helpers to bridge between the card database and GameState models.

import logging 

from typing import Iterable, List, Tuple
from game_state import CardInHand, CardType, Rune
from card_db import CardRecord, get_card
from advisor_models import BattlefieldState

logger = logging.getLogger(__name__)


def make_hand_from_ids(card_ids: List[str]) -> Tuple[List[CardInHand], List[str]]:
    """
    Convert list of card IDs to CardInHand objects with parsed abilities.
    
    Returns:
        (hand_cards, missing_ids)
    """
    hand = []
    missing = []
    
    for card_id in card_ids:
        card = get_card(card_id)
        if card is None:
            missing.append(card_id)
            continue
        
        # Convert to CardInHand
        card_in_hand = card_record_to_hand_card(card)
        
        # Parse abilities
        card_in_hand.parse_abilities()
        
        hand.append(card_in_hand)
    
    return hand, missing


def card_record_to_hand_card(record: CardRecord) -> CardInHand:
    """
    Convert a CardRecord to CardInHand with parsed abilities.
    """
    card = CardInHand(
        card_id=record.card_id,
        name=record.name,
        card_type=record.card_type,
        domain=record.domain,
        energy_cost=record.energy_cost,
        power_cost=record.power_cost,
        might=record.might,
        tags=record.tags or [],
        keywords=record.keywords or [],
        rules_text=record.rules_text,
        keep=True
    )
    
    # Auto-parse abilities
    card.parse_abilities()
    
    return card


def enrich_card_with_abilities(card: CardInHand) -> CardInHand:
    """
    Ensure card has parsed abilities.
    Useful for cards loaded without automatic parsing.
    """
    if not card.parsed_abilities and card.rules_text:
        card.parse_abilities()
    
    return card


def get_cards_with_ability_type(
    cards: List[CardInHand],
    ability_type
) -> List[CardInHand]:
    """
    Filter cards that have a specific ability type.
    
    Args:
        cards: List of cards to filter
        ability_type: AbilityType to search for
    
    Returns:
        Cards that have that ability type
    """
    return [
        card for card in cards
        if card.has_ability_type(ability_type)
    ]


def get_removal_spells(cards: List[CardInHand]) -> List[CardInHand]:
    """Get all removal spells from a list of cards."""
    from ability_parser import AbilityType
    
    removal_types = {
        AbilityType.DESTROY,
        AbilityType.DAMAGE,
        AbilityType.BOUNCE,
        AbilityType.EXILE
    }
    
    removal_cards = []
    for card in cards:
        if card.card_type != CardType.SPELL:
            continue
        
        # Check parsed abilities
        has_removal = any(
            a.ability_type in removal_types
            for a in card.parsed_abilities
        )
        
        # Also check tags as fallback
        has_removal_tag = any(
            tag.lower() in ['removal', 'destroy', 'damage', 'kill']
            for tag in (card.tags or [])
        )
        
        if has_removal or has_removal_tag:
            removal_cards.append(card)
    
    return removal_cards


def get_buff_spells(cards: List[CardInHand]) -> List[CardInHand]:
    """Get all buff/enhancement spells."""
    from ability_parser import AbilityType
    
    buff_types = {
        AbilityType.BUFF_TARGET,
        AbilityType.BUFF_SELF,
        AbilityType.BUFF_ALL
    }
    
    buff_cards = []
    for card in cards:
        if card.card_type not in [CardType.SPELL, CardType.GEAR]:
            continue
        
        has_buff = any(
            a.ability_type in buff_types
            for a in card.parsed_abilities
        )
        
        has_buff_tag = any(
            tag.lower() in ['buff', 'enhancement', 'boost']
            for tag in (card.tags or [])
        )
        
        if has_buff or has_buff_tag:
            buff_cards.append(card)
    
    return buff_cards


def get_units_with_etb(cards: List[CardInHand]) -> List[CardInHand]:
    """Get all units with enters-the-battlefield abilities."""
    from ability_parser import AbilityType
    
    return [
        card for card in cards
        if card.card_type == CardType.UNIT and
        any(a.ability_type == AbilityType.ENTERS_BATTLEFIELD for a in card.parsed_abilities)
    ]


def get_card_ability_summary(card: CardInHand) -> str:
    """
    Get a human-readable summary of a card's abilities.
    
    Example: "2 triggered ability(ies), 1 static ability(ies)"
    """
    if not card.parsed_abilities:
        if card.rules_text:
            card.parse_abilities()
        else:
            return "No special abilities"
    
    return get_ability_summary(card.parsed_abilities)


def get_instant_speed_cards(cards: List[CardInHand]) -> List[CardInHand]:
    """Get cards that can be played at instant speed (combat tricks, counters)."""
    from ability_parser import EffectTiming, get_abilities_by_timing
    
    instant_cards = []
    
    for card in cards:
        # Check for "Fast" or "Ambush" keyword
        if card.keywords:
            fast_keywords = {'fast', 'ambush', 'instant'}
            if any(k.lower() in fast_keywords for k in card.keywords):
                instant_cards.append(card)
                continue
        
        # Check parsed abilities for instant timing
        instant_abilities = get_abilities_by_timing(
            card.parsed_abilities,
            EffectTiming.INSTANT
        )
        
        if instant_abilities:
            instant_cards.append(card)
    
    return instant_cards


def analyze_combat_tricks(cards: List[CardInHand]) -> List[Tuple[CardInHand, str]]:
    """
    Identify combat tricks and describe what they do.
    
    Returns:
        List of (card, description) tuples
    """
    from ability_parser import AbilityType, EffectTiming
    
    tricks = []
    
    for card in cards:
        # Must be instant speed
        instant_speed = (
            any(k.lower() in {'fast', 'ambush'} for k in (card.keywords or [])) or
            any(a.timing == EffectTiming.INSTANT for a in card.parsed_abilities)
        )
        
        if not instant_speed:
            continue
        
        # Look for combat-relevant abilities
        for ability in card.parsed_abilities:
            description = None
            
            if ability.ability_type in {AbilityType.BUFF_TARGET, AbilityType.BUFF_SELF}:
                value = ability.effect_value or 0
                description = f"Instant buff: +{value} might"
            
            elif ability.ability_type == AbilityType.DAMAGE:
                value = ability.effect_value or 0
                description = f"Instant removal: {value} damage"
            
            elif ability.ability_type == AbilityType.PROTECTION:
                description = "Instant protection"
            
            elif ability.ability_type == AbilityType.DESTROY:
                description = "Instant destroy"
            
            if description:
                tricks.append((card, description))
                break  # One description per card
    
    return tricks


def get_cards_that_target(
    cards: List[CardInHand],
    target_type
) -> List[CardInHand]:
    """
    Get cards that target a specific type of permanent.
    
    Args:
        cards: List of cards
        target_type: EffectTarget enum value
    
    Returns:
        Cards that can target that type
    """
    return [
        card for card in cards
        if any(a.effect_target == target_type for a in card.parsed_abilities)
    ]


def estimate_card_threat_level(card: CardInHand, for_opponent: bool = False) -> int:
    """
    Estimate how threatening a card is (0-10 scale).
    
    Args:
        card: Card to evaluate
        for_opponent: If True, evaluate threat TO opponent; if False, evaluate threat FROM opponent
    
    Returns:
        Threat score 0-10
    """
    from ability_parser import AbilityType
    
    threat = 0
    
    # Base threat from stats
    if card.card_type == CardType.UNIT and card.might:
        threat += min(card.might, 5)  # Cap at 5 from stats
    
    # Ability-based threat
    for ability in card.parsed_abilities:
        # Removal is high threat
        if ability.ability_type in {AbilityType.DESTROY, AbilityType.DAMAGE, AbilityType.EXILE}:
            threat += 3
            if ability.effect_value and ability.effect_value >= 4:
                threat += 1  # High damage removal
        
        # Board wipes
        if ability.ability_type == AbilityType.DESTROY and ability.effect_target:
            from ability_parser import EffectTarget
            if ability.effect_target in {EffectTarget.ALL_UNITS, EffectTarget.OPPONENT_UNITS}:
                threat += 4  # Board wipes are very threatening
        
        # ETB abilities add threat
        if ability.ability_type == AbilityType.ENTERS_BATTLEFIELD:
            threat += 2
        
        # Cost reduction / card advantage
        if ability.ability_type in {AbilityType.COST_REDUCTION, AbilityType.DRAW_CARDS}:
            threat += 2
        
        # Static buffs
        if ability.ability_type == AbilityType.STATIC_BUFF:
            threat += 2
    
    # Keywords add threat
    if card.keywords:
        threatening_keywords = {'assault', 'overwhelm', 'double strike', 'flying'}
        keyword_threat = sum(
            1 for k in card.keywords
            if k.lower() in threatening_keywords
        )
        threat += keyword_threat
    
    return min(threat, 10)  # Cap at 10


def print_card_details(card: CardInHand, include_abilities: bool = True):
    """
    Print detailed card information including parsed abilities.
    Useful for debugging.
    """
    print(f"\n=== {card.name} ({card.card_id}) ===")
    print(f"Type: {card.card_type.value}")
    print(f"Domain: {card.domain.value}")
    print(f"Cost: {card.energy_cost} energy")
    
    if card.might:
        print(f"Might: {card.might}")
    
    if card.keywords:
        print(f"Keywords: {', '.join(card.keywords)}")
    
    if card.tags:
        print(f"Tags: {', '.join(card.tags)}")
    
    if card.rules_text:
        print(f"\nRules Text:")
        print(f"  {card.rules_text}")
    
    if include_abilities and card.parsed_abilities:
        print(f"\nParsed Abilities ({len(card.parsed_abilities)}):")
        for i, ability in enumerate(card.parsed_abilities, 1):
            print(f"  {i}. {ability.ability_type.value}")
            print(f"     Text: {ability.raw_text}")
            if ability.effect_target:
                print(f"     Target: {ability.effect_target.value}")
            if ability.timing:
                print(f"     Timing: {ability.timing.value}")
            if ability.effect_value:
                print(f"     Value: {ability.effect_value}")
            if ability.cost:
                print(f"     Cost: {ability.cost}")
    
    print()


def load_battlefield_state(battlefield_state: BattlefieldState) -> BattlefieldState:
    """
    Enrich battlefield state with full card data from database.
    
    Takes a BattlefieldState with just IDs and might values,
    returns a BattlefieldState with full unit dictionaries.
    """
    my_unit = None
    opponent_unit = None
    
    # Load my unit if present
    if battlefield_state.my_unit_id:
        my_card = get_card(battlefield_state.my_unit_id)
        if my_card:
            my_unit = {
                "card_id": my_card.card_id,
                "name": my_card.name,
                "might": battlefield_state.my_unit_might if battlefield_state.my_unit_might is not None else my_card.might
            }
    
    # Load opponent unit if present
    if battlefield_state.opponent_unit_id:
        op_card = get_card(battlefield_state.opponent_unit_id)
        if op_card:
            opponent_unit = {
                "card_id": op_card.card_id,
                "name": op_card.name,
                "might": battlefield_state.opponent_unit_might if battlefield_state.opponent_unit_might is not None else op_card.might
            }
    
    # Return a new BattlefieldState with enriched data
    return BattlefieldState(
        battlefield_id=battlefield_state.battlefield_id,
        my_unit_id=battlefield_state.my_unit_id,
        my_unit_might=battlefield_state.my_unit_might,
        opponent_unit_id=battlefield_state.opponent_unit_id,
        opponent_unit_might=battlefield_state.opponent_unit_might,
        # These are used internally by the analyzer
        my_unit=my_unit,
        opponent_unit=opponent_unit
    )
