# game_state.py - Enhanced with parsed abilities

from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

# Import ability parser
from ability_parser import ParsedAbility, AbilityParser

# ----------------
# Rune system (6 colors)
# ----------------
class Rune (str, Enum):
    FURY = "fury"   # red
    BODY = "body"   # orange
    ORDER = "order" # yellow
    CALM = "calm"   # green
    MIND = "mind"   # blue
    CHAOS = "chaos" # purple    
    COLORLESS = "colorless" # battlefields

# ----------------
# Different phases during turn
# ----------------
class Phase(str, Enum):
    MULLIGAN = "mulligan"
    MAIN = "main"
    SHOWDOWN = "showdown"
    END = "end"
    
# ----------------
# Card Types
# ----------------
class CardType (str, Enum):
    UNIT = "unit"
    GEAR = "gear"
    SPELL = "spell"
    LEGEND = "legend"
    BATTLEFIELD = "battlefield"
    
# ----------------
# Cards in Hand
# ----------------
class CardInHand (BaseModel):
    card_id: str
    name: Optional[str] = None
    card_type: CardType
    domain: Rune # Rune identity
    energy_cost: int = 0 # Rune tap cost
    power_cost: int = 0 # Rune recycle cost
    power_cost_by_rune: Dict[Rune, int] = {}
    might: Optional[int] = None
    tags: List[str] = []
    keywords: List[str] = []
    element: Optional[Rune] = None
    rules_text: Optional[str] = None  # Card rules text for ability analysis
    keep: bool = True
    
    # Parsed abilities
    parsed_abilities: List[ParsedAbility] = Field(default_factory=list)
    
    def parse_abilities(self):
        """Parse rules text into structured abilities."""
        if self.rules_text:
            self.parsed_abilities = AbilityParser.parse_rules_text(self.rules_text)
    
    def has_ability_type(self, ability_type) -> bool:
        """Check if this card has a specific ability type."""
        from ability_parser import has_ability_type
        return has_ability_type(self.parsed_abilities, ability_type)
    
    def get_triggered_abilities(self) -> List[ParsedAbility]:
        """Get all triggered abilities."""
        from ability_parser import get_abilities_by_timing, EffectTiming
        return get_abilities_by_timing(self.parsed_abilities, EffectTiming.ON_TRIGGER)
    
    def get_activated_abilities(self) -> List[ParsedAbility]:
        """Get abilities that can be activated."""
        from ability_parser import AbilityType
        activated_types = {
            AbilityType.TAP_ABILITY,
            AbilityType.EXHAUST_ABILITY,
            AbilityType.SACRIFICE_ABILITY,
            AbilityType.PAY_COST_ABILITY
        }
        return [a for a in self.parsed_abilities if a.ability_type in activated_types]

# ----------------
# Battlefield
# ----------------
class Unit(BaseModel):
    """
    Unit on the board. Might = both attack AND health.
    """
    card_id: str
    might: int
    base_might: Optional[int] = None
    current_might: Optional[int] = None
    damage_marked: int = 0
    domain: Optional[Rune] = None
    abilities: List[str] = []
    keywords: List[str] = []
    attached_gear_ids: List[str] = []
    exhausted: bool = False
    
    # Parsed abilities
    parsed_abilities: List[ParsedAbility] = Field(default_factory=list)
    rules_text: Optional[str] = None
    
    def parse_abilities(self):
        """Parse rules text into structured abilities."""
        if self.rules_text:
            self.parsed_abilities = AbilityParser.parse_rules_text(self.rules_text)
    
    def has_enters_battlefield_ability(self) -> bool:
        """Check if unit has ETB ability."""
        from ability_parser import AbilityType
        return any(
            a.ability_type == AbilityType.ENTERS_BATTLEFIELD 
            for a in self.parsed_abilities
        )
    
    def has_death_trigger(self) -> bool:
        """Check if unit has dies ability."""
        from ability_parser import AbilityType
        return any(
            a.ability_type == AbilityType.DIES 
            for a in self.parsed_abilities
        )

class Battlefield(BaseModel):
    """
    A battlefield where units can be placed.
    Riftbound has 2 battlefields in a 1v1 scenario.
    """
    my_unit: Optional[Unit] = None
    op_unit: Optional[Unit] = None
    
    # Battlefield abilities (some battlefields have effects)
    battlefield_id: Optional[str] = None
    battlefield_name: Optional[str] = None
    battlefield_rules: Optional[str] = None
    parsed_abilities: List[ParsedAbility] = Field(default_factory=list)
    
    def parse_battlefield_abilities(self):
        """Parse battlefield rules text."""
        if self.battlefield_rules:
            self.parsed_abilities = AbilityParser.parse_rules_text(self.battlefield_rules)

class Legend(BaseModel):
    """
    Legend represents the player's chosen Legend character.
    Legends have abilities and can be exhausted/ready.
    """
    card_id: str
    name: Optional[str] = None
    domain: Rune
    exhausted: bool = False
    abilities: List[str] = []  # List of ability descriptions
    passive_abilities: List[str] = []  # Passive abilities that are always active
    activated_abilities: List[str] = []  # Activated abilities (tap, etc.)
    triggered_abilities: List[str] = []  # Triggered abilities
    
    # Parsed abilities with full structure
    parsed_abilities: List[ParsedAbility] = Field(default_factory=list)
    rules_text: Optional[str] = None
    tags: List[str] = []  # For tribal synergies
    
    def parse_abilities(self):
        """Parse legend's rules text into structured abilities."""
        if self.rules_text:
            self.parsed_abilities = AbilityParser.parse_rules_text(self.rules_text)
            self._categorize_abilities()
    
    def _categorize_abilities(self):
        """Categorize parsed abilities into passive/activated/triggered lists."""
        from ability_parser import AbilityType, categorize_abilities
        
        categorized = categorize_abilities(self.parsed_abilities)
        
        # Convert parsed abilities back to string lists for backward compatibility
        self.triggered_abilities = [a.raw_text for a in categorized['triggered']]
        self.activated_abilities = [a.raw_text for a in categorized['activated']]
        self.passive_abilities = [a.raw_text for a in categorized['static']]
    
    def get_usable_abilities(self) -> List[ParsedAbility]:
        """Get abilities that can be used right now (not exhausted)."""
        if self.exhausted:
            return []
        
        from ability_parser import AbilityType
        activated_types = {
            AbilityType.TAP_ABILITY,
            AbilityType.EXHAUST_ABILITY,
            AbilityType.SACRIFICE_ABILITY,
            AbilityType.PAY_COST_ABILITY
        }
        
        return [a for a in self.parsed_abilities if a.ability_type in activated_types]

class PlayerState(BaseModel):
    name: Optional[str] = None
    leader_id: Optional[str] = None  # Deprecated: use legend instead
    legend: Optional[Legend] = None  # The player's Legend
    mana_total: Optional[int] = None
    mana_by_rune: Dict[Rune, int] = {}
    deck_size: Optional[int] = None
    hand: List[CardInHand] = []
    hand_size: Optional[int] = None
    
    def parse_all_abilities(self):
        """Parse abilities for all cards and legend."""
        # Parse legend abilities
        if self.legend:
            self.legend.parse_abilities()
        
        # Parse hand card abilities
        for card in self.hand:
            card.parse_abilities()

class GameState(BaseModel):
    source: str = "arena"
    turn: int = 1
    phase: Phase = Phase.MULLIGAN
    active_player: str = "me"

    me: PlayerState
    opponent: PlayerState

    battlefields: List[Battlefield] = []
    environment_cards: List[str] = []

    timestamp: Optional[float] = None
    
    def parse_all_abilities(self):
        """Parse abilities for entire game state."""
        # Parse player abilities
        self.me.parse_all_abilities()
        self.opponent.parse_all_abilities()
        
        # Parse battlefield abilities
        for battlefield in self.battlefields:
            battlefield.parse_battlefield_abilities()
            
            if battlefield.my_unit:
                battlefield.my_unit.parse_abilities()
            
            if battlefield.op_unit:
                battlefield.op_unit.parse_abilities()