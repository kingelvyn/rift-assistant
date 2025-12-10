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
    keep: bool = True

# ----------------
# Battlefield / Lane
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

class Lane(BaseModel):
    my_unit: Optional[Unit] = None
    op_unit: Optional[Unit] = None

class PlayerState(BaseModel):
    name: Optional[str] = None
    leader_id: Optional[str] = None
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

    lanes: List[Lane] = []
    environment_cards: List[str] = []

    timestamp: Optional[float] = None
