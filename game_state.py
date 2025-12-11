# game_state.py - Variables of the game state

from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel

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

class Battlefield(BaseModel):
    """
    A battlefield where units can be placed.
    Riftbound has 2 battlefields in a 1v1 scenario.
    """
    my_unit: Optional[Unit] = None
    op_unit: Optional[Unit] = None

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

class PlayerState(BaseModel):
    name: Optional[str] = None
    leader_id: Optional[str] = None  # Deprecated: use legend instead
    legend: Optional[Legend] = None  # The player's Legend
    mana_total: Optional[int] = None
    mana_by_rune:Dict[Rune, int] = {}
    deck_size: Optional[int] = None
    hand: List[CardInHand] = []
    hand_size: Optional[int] = None

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
