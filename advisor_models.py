# Advisor response models
# advisor_models.py

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from game_state import CardType


class MulliganRequest(BaseModel):
    """Simplified request for mulligan advice."""
    hand_ids: List[str] = Field(
        ..., 
        description="List of card IDs in opening hand", 
        min_length=4, 
        max_length=4  # Changed from 7 to 4
    )
    legend_id: Optional[str] = Field(None, description="Player's legend card ID")
    turn: int = Field(1, description="Turn number (should be 1 for mulligan)")
    going_first: bool = Field(True, description="Whether player is going first/second")
    
    @field_validator('hand_ids')
    @classmethod
    def validate_hand_size(cls, v):
        if len(v) != 4:
            raise ValueError('Opening hand must contain exactly 4 cards')
        return v

class MulliganCardDecision(BaseModel):
    card_id: str
    name: Optional[str]
    keep: bool
    reason: str

class MulliganAdvice(BaseModel):
    decisions: List[MulliganCardDecision]
    summary: str
    mulligan_count: int = Field(description="Number of cards to mulligan (max 2)")

class MulliganAdviceResponse(BaseModel):
    """Response model for mulligan advice endpoint."""
    decisions: List[MulliganCardDecision]
    summary: str
    mulligan_count: int

class BattlefieldPlacement(BaseModel):
    """Recommendation for which battlefield to place a unit."""
    battlefield_index: int
    reason: str
    priority: int  # Lower = higher priority

class BattlefieldState(BaseModel):
    """State of a single battlefield."""
    battlefield_id: Optional[str] = Field(None, description="Battlefield card ID if applicable")
    my_unit: Optional[dict] = Field(None, description="My unit on this battlefield")
    opponent_unit: Optional[dict] = Field(None, description="Opponent's unit on this battlefield")
    
    class Config:
        json_schema_extra = {
            "example": {
                "battlefield_id": "OGN-275",
                "my_unit": {"card_id": "OGN-034", "name": "Veteran Warrior", "might": 2},
                "opponent_unit": None
            }
        }


class ScoringDebugInfo(BaseModel):
    """Debug information about scoring calculations."""
    card_value_scores: dict[str, float]  # card_id -> value score
    threat_assessment: dict  # Threat level assessment from opponent
    mana_efficiency_score: float  # 0.0 to 1.0, how efficiently mana is used
    battlefield_analyses: List[dict]  # Detailed battlefield state analyses
    game_phase: str  # "early", "mid", or "late" game

class PlayableCardRecommendation(BaseModel):
    card_id: str
    name: Optional[str]
    card_type: CardType
    energy_cost: int
    priority: int  # 1 = highest priority, higher numbers = lower priority
    recommended: bool  # Should this card be played this turn?
    reason: str
    play_order: Optional[int] = None  # Suggested order if playing multiple cards
    battlefield_placement: Optional[BattlefieldPlacement] = None  # For units: which battlefield to play into
    legend_synergy: Optional[str] = None  # Notes about how this card interacts with legend abilities
    value_score: Optional[float] = None  # Calculated value score for this card (for debugging)

class PlayableCardsAdvice(BaseModel):
    playable_cards: List[PlayableCardRecommendation]
    recommended_plays: List[str]  # card_ids of recommended plays
    summary: str
    mana_efficiency_note: Optional[str] = None
    scoring_debug: Optional[ScoringDebugInfo] = None  # Scoring calculations for debugging

class PlayableCardsRequest(BaseModel):
    """Simplified request for playable cards advice."""
    hand_ids: List[str] = Field(..., description="List of card IDs in current hand")
    legend_id: Optional[str] = Field(None, description="Player's legend card ID")
    opponent_legend_id: Optional[str] = Field(None, description="Opponent's legend card ID")
    
    # Resource system
    my_energy: int = Field(..., ge=0, description="Available energy (generic resource)")
    my_power: dict[str, int] = Field(
        default_factory=dict,
        description="Available power by domain (e.g., {'chaos': 2, 'calm': 1})"
    )
    
    # Game state
    turn: int = Field(..., ge=1, description="Current turn number")
    phase: str = Field(..., description="Current game phase (main/combat/showdown)")
    going_first: bool = Field(True, description="Whether player went first")
    
    # Battlefield state (exactly 2 in 1v1)
    battlefields: List[BattlefieldState] = Field(
        default_factory=lambda: [BattlefieldState(), BattlefieldState()],
        min_length=2,
        max_length=2,
        description="State of both battlefields (always 2 in 1v1)"
    )
    
    # Legend states
    my_legend_exhausted: bool = Field(False, description="Is your legend exhausted?")
    opponent_legend_exhausted: bool = Field(False, description="Is opponent's legend exhausted?")
    
    # Additional context
    my_health: Optional[int] = Field(None, ge=0, description="Player's current health")
    opponent_health: Optional[int] = Field(None, ge=0, description="Opponent's current health")

    @field_validator('battlefields')
    @classmethod
    def validate_battlefield_count(cls, v):
        if len(v) != 2:
            raise ValueError('Must have exactly 2 battlefields in 1v1')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "hand_ids": ["OGN-034", "OGN-082", "OGN-142", "OGN-189"],
                "legend_id": "OGN-076",
                "opponent_legend_id": "OGN-263",
                "my_energy": 3,
                "my_power": {"chaos": 2, "calm": 1},
                "turn": 2,
                "phase": "main",
                "going_first": True,
                "battlefields": [
                    {
                        "battlefield_id": None,
                        "my_unit": {"card_id": "OGN-034", "name": "Goblin Scout", "might": 2},
                        "opponent_unit": None
                    },
                    {
                        "battlefield_id": None,
                        "my_unit": None,
                        "opponent_unit": {"card_id": "OGN-197", "name": "Teemo", "might": 1}
                    }
                ],
                "my_legend_exhausted": False,
                "opponent_legend_exhausted": True,
                "my_health": 20,
                "opponent_health": 18
            }
        }