# api.py

import logging
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from mulligan_advisor import analyze_mulligan
from playable_cards_advisor import analyze_playable_cards
from advisor_models import (
    MulliganCardDecision,
    MulliganRequest,
    MulliganAdviceResponse,
    PlayableCardRecommendation,
    ScoringDebugInfo,
    PlayableCardsRequest,
    PlayStrategy
)
from card_utils import make_hand_from_ids
from game_state import GameState, Rune, CardType
from card_db import init_db, CardRecord, get_card, list_cards, upsert_card, count_cards
from logger_config import setup_logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Riftbound Assistant")

@app.on_event("startup")
def on_startup() -> None:
    setup_logging()
    init_db()


class PlayableCardsAdviceResponse(BaseModel):
    playable_cards: List[PlayableCardRecommendation]
    recommended_strategies: List[PlayStrategy]  
    primary_strategy: List[str]  
    summary: str
    mana_efficiency_note: Optional[str] = None
    scoring_debug: Optional[ScoringDebugInfo] = None


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


@app.post("/advice/mulligan", response_model=MulliganAdviceResponse)
def mulligan_advice_endpoint(request: MulliganRequest) -> MulliganAdviceResponse:
    """Provide mulligan advice for an opening hand."""
    try:
        logger.info(f"Processing mulligan request for {len(request.hand_ids)} cards")
        
        hand, missing_ids = make_hand_from_ids(request.hand_ids)
        
        if missing_ids:
            logger.warning(f"Missing card IDs in database: {missing_ids}")
        
        if not hand:
            logger.error("No valid cards found in hand")
            raise HTTPException(
                status_code=400, 
                detail=f"No valid cards found. Missing IDs: {missing_ids}"
            )
        
        legend_card = None
        if request.legend_id:
            legend_card = get_card(request.legend_id)
            if not legend_card:
                logger.warning(f"Legend ID '{request.legend_id}' not found in database")
        
        advice = analyze_mulligan(
            hand=hand,
            legend_card=legend_card,
            turn=request.turn,
            going_first=request.going_first
        )
        
        logger.info(f"Mulligan advice generated: keeping {sum(1 for d in advice.decisions if d.keep)}/{len(advice.decisions)} cards")
        
        return MulliganAdviceResponse(
            decisions=advice.decisions,
            summary=advice.summary,
            mulligan_count=advice.mulligan_count,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing mulligan advice: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/advice/playable", response_model=PlayableCardsAdviceResponse)
def playable_cards_advice_endpoint(request: PlayableCardsRequest) -> PlayableCardsAdviceResponse:
    """
    Analyze playable cards for Riftbound 1v1 matches.
    
    Properly handles:
    - 2 battlefields (standard 1v1 format)
    - Energy and power resource systems
    - Battlefield positioning strategy
    - Threat assessment
    """
    try:
        logger.info(
            f"Processing playable cards: turn {request.turn}, "
            f"energy {request.my_energy}, power {request.my_power}"
        )
        
        # Validate phase
        valid_phases = ["main", "combat", "showdown"]
        if request.phase.lower() not in valid_phases:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid phase. Must be one of: {', '.join(valid_phases)}"
            )
        
        # Load hand cards from database
        hand, missing_ids = make_hand_from_ids(request.hand_ids)
        
        if missing_ids:
            logger.warning(f"Missing card IDs: {missing_ids}")
        
        if not hand:
            raise HTTPException(
                status_code=400,
                detail=f"No valid cards found. Missing IDs: {missing_ids}"
            )
        
        # Load legends from database
        my_legend = get_card(request.legend_id) if request.legend_id else None
        opponent_legend = get_card(request.opponent_legend_id) if request.opponent_legend_id else None
        
        # Convert battlefield states - enrich with card data
        enriched_battlefields = []
        for bf_state in request.battlefields:
            # Build my_unit dict if unit exists
            my_unit = None
            if bf_state.my_unit_id:
                my_card = get_card(bf_state.my_unit_id)
                if my_card:
                    my_unit = {
                        "card_id": my_card.card_id,
                        "name": my_card.name,
                        "might": bf_state.my_unit_might if bf_state.my_unit_might is not None else my_card.might
                    }
                else:
                    logger.warning(f"My unit card '{bf_state.my_unit_id}' not found in database")
            
            # Build opponent_unit dict if unit exists
            opponent_unit = None
            if bf_state.opponent_unit_id:
                op_card = get_card(bf_state.opponent_unit_id)
                if op_card:
                    opponent_unit = {
                        "card_id": op_card.card_id,
                        "name": op_card.name,
                        "might": bf_state.opponent_unit_might if bf_state.opponent_unit_might is not None else op_card.might
                    }
                else:
                    logger.warning(f"Opponent unit card '{bf_state.opponent_unit_id}' not found in database")
            
            # Create enriched battlefield state with actual unit data
            from advisor_models import BattlefieldState as EnrichedBattlefieldState
            enriched_bf = EnrichedBattlefieldState(
                battlefield_id=bf_state.battlefield_id,
                my_unit=my_unit,
                opponent_unit=opponent_unit
            )
            enriched_battlefields.append(enriched_bf)
        
        # Analyze with enriched data
        advice = analyze_playable_cards(
            hand=hand,
            my_energy=request.my_energy,
            my_power=request.my_power,
            turn=request.turn,
            phase=request.phase,
            battlefields=enriched_battlefields,  # Pass enriched battlefields
            my_legend=my_legend,
            opponent_legend=opponent_legend,
            my_legend_exhausted=request.my_legend_exhausted,
            opponent_legend_exhausted=request.opponent_legend_exhausted,
            going_first=request.going_first,
            my_score=request.my_score,
            opponent_score=request.opponent_score,
        )
        
        logger.info(
            f"Generated advice: {len(advice.primary_strategy)} recommendations, "
            f"threat level: {advice.scoring_debug.threat_assessment.get('level') if advice.scoring_debug else 'unknown'}"
        )
        
        return PlayableCardsAdviceResponse(
            playable_cards=advice.playable_cards,
            recommended_strategies=advice.recommended_strategies,
            primary_strategy=advice.primary_strategy,
            summary=advice.summary,
            mana_efficiency_note=advice.mana_efficiency_note,
            scoring_debug=advice.scoring_debug,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing playable cards: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cards", response_model=List[CardResponse])
def list_cards_endpoint(
    card_type: Optional[CardType] = Query(None),
    domain: Optional[Rune] = Query(None),
    include_battlefields: bool = Query(False),
) -> List[CardResponse]:
    """List cards in the catalog with optional filters."""
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
    """Create or update a card manually."""
    record = CardRecord(**payload.model_dump())
    upsert_card(record)
    saved = get_card(record.card_id)
    assert saved is not None
    return saved


@app.get("/cards/count")
def card_count_endpoint() -> dict:
    """Returns the number of cards currently stored in cards.db."""
    total = count_cards()
    return {"card_count": total}