# ability_parser.py - Comprehensive card ability parsing system

from typing import List, Dict, Optional, Set
from enum import Enum
from dataclasses import dataclass
import re


class AbilityType(str, Enum):
    """Types of abilities that cards can have."""
    # Triggered abilities
    ENTERS_BATTLEFIELD = "enters_battlefield"  # "When this enters the battlefield"
    LEAVES_BATTLEFIELD = "leaves_battlefield"  # "When this leaves the battlefield"
    DIES = "dies"  # "When this dies"
    ATTACKS = "attacks"  # "When this attacks"
    BLOCKS = "blocks"  # "When this blocks"
    DEALS_DAMAGE = "deals_damage"  # "When this deals damage"
    TAKES_DAMAGE = "takes_damage"  # "When this takes damage"
    START_OF_TURN = "start_of_turn"  # "At the start of your turn"
    END_OF_TURN = "end_of_turn"  # "At the end of your turn"
    
    # Activated abilities
    TAP_ABILITY = "tap_ability"  # "Tap: Do something"
    EXHAUST_ABILITY = "exhaust_ability"  # "Exhaust: Do something"
    SACRIFICE_ABILITY = "sacrifice_ability"  # "Sacrifice: Do something"
    PAY_COST_ABILITY = "pay_cost_ability"  # "Pay X: Do something"
    
    # Static/Passive abilities
    STATIC_BUFF = "static_buff"  # "Your units get +1/+1"
    STATIC_DEBUFF = "static_debuff"  # "Enemy units get -1/-1"
    COST_REDUCTION = "cost_reduction"  # "Spells cost 1 less"
    PROTECTION = "protection"  # "Your units can't be targeted"
    AURA = "aura"  # "Units you control have flying"
    
    # Keywords (already in keywords list but tracked here too)
    KEYWORD = "keyword"  # Assault, Guard, Flying, etc.
    
    # Special mechanics
    CHOOSE_EFFECT = "choose_effect"  # "Choose one: A or B"
    MODAL = "modal"  # Multiple choice effects
    COPY_SPELL = "copy_spell"  # "Copy target spell"
    DRAW_CARDS = "draw_cards"  # "Draw X cards"
    DISCARD = "discard"  # "Discard a card"
    
    # Removal effects
    DESTROY = "destroy"  # "Destroy target unit"
    EXILE = "exile"  # "Exile target card"
    BOUNCE = "bounce"  # "Return to hand"
    DAMAGE = "damage"  # "Deal X damage"
    
    # Buffing effects
    BUFF_SELF = "buff_self"  # "This gets +2/+2"
    BUFF_TARGET = "buff_target"  # "Target unit gets +1/+1"
    BUFF_ALL = "buff_all"  # "All units get +1/+1"
    
    # Resource generation
    RUNE_GENERATION = "rune_generation"  # "Add a rune"
    ENERGY_GENERATION = "energy_generation"  # "Gain energy"
    
    # Miscellaneous
    LEGEND_INTERACTION = "legend_interaction"  # References legend
    DOMAIN_MATTERS = "domain_matters"  # Cares about domain
    TRIBAL_MATTERS = "tribal_matters"  # Cares about creature types
    COUNTER = "counter"  # "Counter target spell"


class EffectTarget(str, Enum):
    """What the ability targets or affects."""
    SELF = "self"
    TARGET_UNIT = "target_unit"
    TARGET_SPELL = "target_spell"
    TARGET_PLAYER = "target_player"
    ALL_UNITS = "all_units"
    YOUR_UNITS = "your_units"
    OPPONENT_UNITS = "opponent_units"
    YOUR_LEGEND = "your_legend"
    OPPONENT_LEGEND = "opponent_legend"
    BATTLEFIELD = "battlefield"
    HAND = "hand"
    DECK = "deck"
    GRAVEYARD = "graveyard"


class EffectTiming(str, Enum):
    """When the ability can be used or triggers."""
    INSTANT = "instant"  # Can be used at any time
    MAIN_PHASE = "main_phase"  # Only during main phase
    COMBAT = "combat"  # During combat/showdown
    ALWAYS = "always"  # Static effect, always on
    ON_TRIGGER = "on_trigger"  # When specific condition met


@dataclass
class ParsedAbility:
    """A structured representation of a card ability."""
    ability_type: AbilityType
    raw_text: str
    effect_target: Optional[EffectTarget] = None
    timing: EffectTiming = EffectTiming.ALWAYS
    cost: Optional[str] = None  # e.g., "Tap", "2 energy", "Sacrifice a unit"
    effect_value: Optional[int] = None  # e.g., +2/+2, deal 3 damage
    conditions: List[str] = None  # Requirements for ability to work
    keywords_granted: List[str] = None  # Keywords given by this ability
    domain_restriction: Optional[str] = None  # e.g., "Fury units only"
    
    def __post_init__(self):
        if self.conditions is None:
            self.conditions = []
        if self.keywords_granted is None:
            self.keywords_granted = []


class AbilityParser:
    """Parses rules text into structured ability data."""
    
    # Keyword patterns
    TRIGGERED_PATTERNS = {
        AbilityType.ENTERS_BATTLEFIELD: [
            r'when (?:this|.*?) enters? (?:the battlefield|play)',
            r'etb[:\s]',
            r'on entry[:\s]',
        ],
        AbilityType.LEAVES_BATTLEFIELD: [
            r'when (?:this|.*?) leaves? (?:the battlefield|play)',
            r'when (?:this|.*?) (?:is |are )?removed',
        ],
        AbilityType.DIES: [
            r'when (?:this|.*?) dies?',
            r'when (?:this|.*?) (?:is |are )?destroyed',
        ],
        AbilityType.ATTACKS: [
            r'when(?:ever)? (?:this|.*?) attacks?',
            r'on attack[:\s]',
        ],
        AbilityType.BLOCKS: [
            r'when(?:ever)? (?:this|.*?) blocks?',
            r'on block[:\s]',
        ],
        AbilityType.DEALS_DAMAGE: [
            r'when(?:ever)? (?:this|.*?) deals? damage',
        ],
        AbilityType.TAKES_DAMAGE: [
            r'when(?:ever)? (?:this|.*?) (?:is dealt|takes?) damage',
        ],
        AbilityType.START_OF_TURN: [
            r'at the (?:start|beginning) of (?:your|each) turn',
        ],
        AbilityType.END_OF_TURN: [
            r'at the end of (?:your|each) turn',
        ],
    }
    
    ACTIVATED_PATTERNS = {
        AbilityType.TAP_ABILITY: [
            r'^tap[:\s]',
            r'^\{t\}[:\s]',
        ],
        AbilityType.EXHAUST_ABILITY: [
            r'^exhaust[:\s]',
            r'^exhaust (?:this|your legend)',
        ],
        AbilityType.SACRIFICE_ABILITY: [
            r'^sacrifice',
        ],
        AbilityType.PAY_COST_ABILITY: [
            r'^pay \d+',
            r'^\d+ energy[:\s]',
        ],
    }
    
    STATIC_PATTERNS = {
        AbilityType.STATIC_BUFF: [
            r'(?:your|you control) (?:units?|creatures?) (?:get|have|gain) \+\d+',
            r'(?:other )?(?:units?|creatures?) you control (?:get|have) \+\d+',
        ],
        AbilityType.COST_REDUCTION: [
            r'(?:spells?|cards?) (?:you cast )?costs? \d+ less',
            r'reduce (?:the )?cost',
        ],
        AbilityType.PROTECTION: [
            r"can't be (?:targeted|destroyed|blocked)",
            r'has? protection',
            r'hexproof',
            r'shroud',
        ],
        AbilityType.AURA: [
            r'(?:units?|creatures?) you control have ',
        ],
    }
    
    EFFECT_PATTERNS = {
        AbilityType.DESTROY: [
            r'destroy (?:target|all|each)',
        ],
        AbilityType.DAMAGE: [
            r'deal(?:s)? \d+ damage',
        ],
        AbilityType.BOUNCE: [
            r'return (?:target|it) to (?:its owner\'s )?hand',
        ],
        AbilityType.DRAW_CARDS: [
            r'draw (?:a card|\d+ cards?)',
        ],
        AbilityType.BUFF_TARGET: [
            r'(?:target )?(?:unit|creature) gets? \+\d+',
        ],
        AbilityType.COUNTER: [
            r'counter target',
        ],
    }
    
    @classmethod
    def parse_rules_text(cls, rules_text: str) -> List[ParsedAbility]:
        """
        Parse rules text into structured abilities.
        
        Args:
            rules_text: Raw rules text from card
            
        Returns:
            List of ParsedAbility objects
        """
        if not rules_text:
            return []
        
        abilities = []
        
        # Split by newlines or periods (sentences)
        lines = re.split(r'[\n\.]+', rules_text)
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            line_lower = line.lower()
            
            # Try to parse this line as an ability
            parsed = cls._parse_ability_line(line, line_lower)
            if parsed:
                abilities.append(parsed)
        
        return abilities
    
    @classmethod
    def _parse_ability_line(cls, line: str, line_lower: str) -> Optional[ParsedAbility]:
        """Parse a single line of ability text."""
        
        # Check for triggered abilities
        for ability_type, patterns in cls.TRIGGERED_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, line_lower):
                    return cls._parse_triggered_ability(line, line_lower, ability_type)
        
        # Check for activated abilities
        for ability_type, patterns in cls.ACTIVATED_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, line_lower):
                    return cls._parse_activated_ability(line, line_lower, ability_type)
        
        # Check for static abilities
        for ability_type, patterns in cls.STATIC_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, line_lower):
                    return cls._parse_static_ability(line, line_lower, ability_type)
        
        # Check for effect patterns
        for ability_type, patterns in cls.EFFECT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, line_lower):
                    return cls._parse_effect_ability(line, line_lower, ability_type)
        
        # Check for special mechanics
        if 'choose one' in line_lower or 'choose two' in line_lower:
            return ParsedAbility(
                ability_type=AbilityType.CHOOSE_EFFECT,
                raw_text=line,
                timing=EffectTiming.MAIN_PHASE
            )
        
        if 'legend' in line_lower:
            return ParsedAbility(
                ability_type=AbilityType.LEGEND_INTERACTION,
                raw_text=line,
                timing=EffectTiming.ALWAYS
            )
        
        # Default: treat as static ability
        return ParsedAbility(
            ability_type=AbilityType.STATIC_BUFF,  # Generic static
            raw_text=line,
            timing=EffectTiming.ALWAYS
        )
    
    @classmethod
    def _parse_triggered_ability(
        cls, line: str, line_lower: str, ability_type: AbilityType
    ) -> ParsedAbility:
        """Parse triggered ability details."""
        
        # Extract effect target
        target = cls._extract_target(line_lower)
        
        # Extract numerical values (damage, buffs, etc.)
        value = cls._extract_number_value(line_lower)
        
        # Extract conditions
        conditions = cls._extract_conditions(line_lower)
        
        # Extract keywords granted
        keywords = cls._extract_keywords_granted(line_lower)
        
        return ParsedAbility(
            ability_type=ability_type,
            raw_text=line,
            effect_target=target,
            timing=EffectTiming.ON_TRIGGER,
            effect_value=value,
            conditions=conditions,
            keywords_granted=keywords
        )
    
    @classmethod
    def _parse_activated_ability(
        cls, line: str, line_lower: str, ability_type: AbilityType
    ) -> ParsedAbility:
        """Parse activated ability details."""
        
        # Extract cost (everything before the colon)
        cost_match = re.match(r'^([^:]+):', line)
        cost = cost_match.group(1).strip() if cost_match else None
        
        # Extract target
        target = cls._extract_target(line_lower)
        
        # Extract value
        value = cls._extract_number_value(line_lower)
        
        # Determine when it can be used
        timing = EffectTiming.MAIN_PHASE
        if 'instant' in line_lower or 'any time' in line_lower:
            timing = EffectTiming.INSTANT
        
        return ParsedAbility(
            ability_type=ability_type,
            raw_text=line,
            effect_target=target,
            timing=timing,
            cost=cost,
            effect_value=value
        )
    
    @classmethod
    def _parse_static_ability(
        cls, line: str, line_lower: str, ability_type: AbilityType
    ) -> ParsedAbility:
        """Parse static/passive ability details."""
        
        # Extract target
        target = cls._extract_target(line_lower)
        
        # Extract value
        value = cls._extract_number_value(line_lower)
        
        # Extract domain restriction
        domain = cls._extract_domain(line_lower)
        
        # Extract keywords granted
        keywords = cls._extract_keywords_granted(line_lower)
        
        return ParsedAbility(
            ability_type=ability_type,
            raw_text=line,
            effect_target=target,
            timing=EffectTiming.ALWAYS,
            effect_value=value,
            domain_restriction=domain,
            keywords_granted=keywords
        )
    
    @classmethod
    def _parse_effect_ability(
        cls, line: str, line_lower: str, ability_type: AbilityType
    ) -> ParsedAbility:
        """Parse spell/effect abilities."""
        
        target = cls._extract_target(line_lower)
        value = cls._extract_number_value(line_lower)
        
        # Most effects are main phase only unless they say otherwise
        timing = EffectTiming.MAIN_PHASE
        if 'instant' in line_lower or ability_type == AbilityType.COUNTER:
            timing = EffectTiming.INSTANT
        
        return ParsedAbility(
            ability_type=ability_type,
            raw_text=line,
            effect_target=target,
            timing=timing,
            effect_value=value
        )
    
    @classmethod
    def _extract_target(cls, text: str) -> Optional[EffectTarget]:
        """Extract what the ability targets."""
        
        if 'target unit' in text or 'target creature' in text:
            return EffectTarget.TARGET_UNIT
        if 'target spell' in text:
            return EffectTarget.TARGET_SPELL
        if 'target player' in text or 'target opponent' in text:
            return EffectTarget.TARGET_PLAYER
        if 'all units' in text or 'all creatures' in text or 'each unit' in text:
            return EffectTarget.ALL_UNITS
        if 'your units' in text or 'units you control' in text or 'creatures you control' in text:
            return EffectTarget.YOUR_UNITS
        if 'opponent' in text and ('units' in text or 'creatures' in text):
            return EffectTarget.OPPONENT_UNITS
        if 'your legend' in text:
            return EffectTarget.YOUR_LEGEND
        if 'opponent\'s legend' in text or 'enemy legend' in text:
            return EffectTarget.OPPONENT_LEGEND
        if 'this' in text or 'it' == text[:2]:
            return EffectTarget.SELF
        
        return None
    
    @classmethod
    def _extract_number_value(cls, text: str) -> Optional[int]:
        """Extract numerical values from ability text."""
        
        # Look for +X/+X or +X patterns
        plus_match = re.search(r'\+(\d+)', text)
        if plus_match:
            return int(plus_match.group(1))
        
        # Look for damage values
        damage_match = re.search(r'(?:deal|deals) (\d+) damage', text)
        if damage_match:
            return int(damage_match.group(1))
        
        # Look for draw values
        draw_match = re.search(r'draw (\d+)', text)
        if draw_match:
            return int(draw_match.group(1))
        
        # Look for cost reduction
        cost_match = re.search(r'cost(?:s)? (\d+) less', text)
        if cost_match:
            return int(cost_match.group(1))
        
        return None
    
    @classmethod
    def _extract_conditions(cls, text: str) -> List[str]:
        """Extract conditions required for ability."""
        conditions = []
        
        if 'if ' in text:
            # Extract text after "if"
            if_match = re.search(r'if (.+?)(?:[,.]|$)', text)
            if if_match:
                conditions.append(if_match.group(1).strip())
        
        if 'as long as' in text:
            condition_match = re.search(r'as long as (.+?)(?:[,.]|$)', text)
            if condition_match:
                conditions.append(condition_match.group(1).strip())
        
        return conditions
    
    @classmethod
    def _extract_keywords_granted(cls, text: str) -> List[str]:
        """Extract keywords granted by this ability."""
        keywords = []
        
        common_keywords = [
            'assault', 'guard', 'flying', 'overwhelm', 'lifesteal',
            'quick', 'ambush', 'double strike', 'first strike',
            'vigilance', 'trample', 'hexproof', 'protection'
        ]
        
        for keyword in common_keywords:
            if keyword in text:
                keywords.append(keyword)
        
        return keywords
    
    @classmethod
    def _extract_domain(cls, text: str) -> Optional[str]:
        """Extract domain/rune restriction."""
        domains = ['fury', 'body', 'order', 'calm', 'mind', 'chaos']
        
        for domain in domains:
            if domain in text:
                return domain
        
        return None


def categorize_abilities(
    parsed_abilities: List[ParsedAbility]
) -> Dict[str, List[ParsedAbility]]:
    """
    Categorize parsed abilities by type for easy access.
    
    Returns:
        Dict with keys: 'triggered', 'activated', 'static', 'effects'
    """
    categorized = {
        'triggered': [],
        'activated': [],
        'static': [],
        'effects': [],
        'keywords': []
    }
    
    triggered_types = {
        AbilityType.ENTERS_BATTLEFIELD, AbilityType.LEAVES_BATTLEFIELD,
        AbilityType.DIES, AbilityType.ATTACKS, AbilityType.BLOCKS,
        AbilityType.DEALS_DAMAGE, AbilityType.TAKES_DAMAGE,
        AbilityType.START_OF_TURN, AbilityType.END_OF_TURN
    }
    
    activated_types = {
        AbilityType.TAP_ABILITY, AbilityType.EXHAUST_ABILITY,
        AbilityType.SACRIFICE_ABILITY, AbilityType.PAY_COST_ABILITY
    }
    
    static_types = {
        AbilityType.STATIC_BUFF, AbilityType.STATIC_DEBUFF,
        AbilityType.COST_REDUCTION, AbilityType.PROTECTION,
        AbilityType.AURA
    }
    
    for ability in parsed_abilities:
        if ability.ability_type in triggered_types:
            categorized['triggered'].append(ability)
        elif ability.ability_type in activated_types:
            categorized['activated'].append(ability)
        elif ability.ability_type in static_types:
            categorized['static'].append(ability)
        elif ability.ability_type == AbilityType.KEYWORD:
            categorized['keywords'].append(ability)
        else:
            categorized['effects'].append(ability)
    
    return categorized


def get_ability_summary(parsed_abilities: List[ParsedAbility]) -> str:
    """Generate human-readable summary of abilities."""
    if not parsed_abilities:
        return "No special abilities"
    
    categorized = categorize_abilities(parsed_abilities)
    
    parts = []
    
    if categorized['triggered']:
        count = len(categorized['triggered'])
        parts.append(f"{count} triggered ability(ies)")
    
    if categorized['activated']:
        count = len(categorized['activated'])
        parts.append(f"{count} activated ability(ies)")
    
    if categorized['static']:
        count = len(categorized['static'])
        parts.append(f"{count} static ability(ies)")
    
    if categorized['effects']:
        count = len(categorized['effects'])
        parts.append(f"{count} effect(s)")
    
    return ", ".join(parts) if parts else "Various abilities"


def has_ability_type(
    parsed_abilities: List[ParsedAbility],
    ability_type: AbilityType
) -> bool:
    """Check if card has a specific ability type."""
    return any(a.ability_type == ability_type for a in parsed_abilities)


def get_abilities_by_timing(
    parsed_abilities: List[ParsedAbility],
    timing: EffectTiming
) -> List[ParsedAbility]:
    """Get all abilities that match a specific timing."""
    return [a for a in parsed_abilities if a.timing == timing]