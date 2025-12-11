from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from advisor import (
    get_simple_advice,
    get_mulligan_advice,
    get_playable_cards_advice,
)
from advisor_models import (
    MulliganAdvice,
    MulliganCardDecision,
    PlayableCardsAdvice,
    PlayableCardRecommendation,
    ScoringDebugInfo,
)
from game_state import GameState, Rune, CardType
from card_db import init_db, CardRecord, get_card, list_cards, upsert_card, count_cards
from logger_config import setup_logging

app = FastAPI (title="Riftbound Assistant")

@app.on_event("startup")
def on_startup() -> None:
    setup_logging()
    init_db()

class AdviceResponse(BaseModel):
    advice: str

class MulliganAdviceResponse(BaseModel):
    decisions: List[MulliganCardDecision]
    summary: str

class PlayableCardsAdviceResponse(BaseModel):
    playable_cards: List[PlayableCardRecommendation]
    recommended_plays: List[str]
    summary: str
    mana_efficiency_note: Optional[str] = None
    scoring_debug: Optional[ScoringDebugInfo] = None  # Scoring calculations for debugging

class CardResponse(CardRecord):
    pass

class CardUpsertRequest(BaseModel):
    card_id: str
    name: str
    card_type: CardType
    domain: Rune
    energy_cost: int = 0
    power_cost: int = 0
    might: Optional[int] = None
    tags: List[str] = []
    keywords: List[str] = []
    rules_text: Optional[str] = None
    set_name: Optional[str] = None

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.post("/advice", response_model=AdviceResponse)
def advice_endpoint(state: GameState) -> AdviceResponse:
    text = get_simple_advice(state)
    return AdviceResponse(advice=text)

@app.post("/advice/mulligan", response_model=MulliganAdviceResponse)
def mulligan_advice_endpoint(state: GameState) -> MulliganAdviceResponse:
    """
    Given a GameState in mulligan phase, return which cards to keep vs. mulligan.

    Expects:
    - state.phase == "mulligan"
    - state.me.hand populated with CardInHand objects
    """
    advice = get_mulligan_advice(state)
    return MulliganAdviceResponse(
        decisions=advice.decisions,
        summary=advice.summary,
    )

@app.post("/advice/playable", response_model=PlayableCardsAdviceResponse)
def playable_cards_advice_endpoint(state: GameState) -> PlayableCardsAdviceResponse:
    """
    Analyze playable cards and provide structured recommendations.
    
    Returns prioritized list of playable cards with:
    - Priority ranking
    - Recommended plays
    - Reasoning for each card
    - Mana efficiency notes
    
    Works best during MAIN or SHOWDOWN phases.
    """
    advice = get_playable_cards_advice(state)
    return PlayableCardsAdviceResponse(
        playable_cards=advice.playable_cards,
        recommended_plays=advice.recommended_plays,
        summary=advice.summary,
        mana_efficiency_note=advice.mana_efficiency_note,
        scoring_debug=advice.scoring_debug,
    )


@app.get("/cards", response_model=List[CardResponse])
def list_cards_endpoint(
    card_type: Optional[CardType] = Query(None),
    domain: Optional[Rune] = Query(None),
    include_battlefields: bool = Query(
        False,
        description="If false, battlefield cards are excluded from results unless explicitly requested."
    ),
) -> List[CardResponse]:
    """
    List cards in the catalog.

    Optional filters:
    - card_type: unit / gear / spell / battlefield
    - domain: fury / body / order / calm / mind / chaos / colorless
    - include_battlefields: if False, battlefield cards are filtered out
    """
    return list_cards(
        card_type=card_type,
        domain=domain,
        exclude_battlefields=not include_battlefields and card_type is None,
    )


@app.get("/cards/{card_id}", response_model=CardResponse)
def get_card_endpoint(card_id: str) -> CardResponse:
    card = get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card

@app.post("/cards", response_model=CardResponse)
def upsert_card_endpoint(payload: CardUpsertRequest) -> CardResponse:
    """
    Create or update a card manually.
    This is handy until you build a scraper.
    """
    record = CardRecord(**payload.model_dump())
    upsert_card(record)
    # Return the latest version from DB
    saved = get_card(record.card_id)
    assert saved is not None
    return saved

@app.get("/cards/count")
def card_count_endpoint() -> dict:
    """
    Returns the number of cards currently stored in cards.db.
    """
    total = count_cards()
    return {"card_count": total}