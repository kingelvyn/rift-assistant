# Advisor response models
# advisor_models.py

from typing import Optional, List
from pydantic import BaseModel
from game_state import CardType

class MulliganCardDecision(BaseModel):
    card_id: str
    name: Optional[str]
    keep: bool
    reason: str

class MulliganAdvice(BaseModel):
    decisions: List[MulliganCardDecision]
    summary: str

class BattlefieldPlacement(BaseModel):
    """Recommendation for which battlefield to place a unit."""
    battlefield_index: int
    reason: str
    priority: int  # Lower = higher priority

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

class ScoringDebugInfo(BaseModel):
    """Debug information about scoring calculations."""
    card_value_scores: dict[str, float]  # card_id -> value score
    threat_assessment: dict  # Threat level assessment from opponent
    mana_efficiency_score: float  # 0.0 to 1.0, how efficiently mana is used
    battlefield_analyses: List[dict]  # Detailed battlefield state analyses
    game_phase: str  # "early", "mid", or "late" game

class PlayableCardsAdvice(BaseModel):
    playable_cards: List[PlayableCardRecommendation]
    recommended_plays: List[str]  # card_ids of recommended plays
    summary: str
    mana_efficiency_note: Optional[str] = None
    scoring_debug: Optional[ScoringDebugInfo] = None  # Scoring calculations for debugging

