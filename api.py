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
from game_state import GameState, Rune, CardType, PlayerState, Legend
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


def _build_legend_from_card(card: CardRecord, exhausted: bool = False) -> Legend:
    """
    Build a Legend object from a CardRecord.
    Parses rules_text to extract abilities.
    """
    if not card:
        return None
    
    # Parse abilities from rules_text
    passive_abilities = []
    activated_abilities = []
    triggered_abilities = []
    
    if card.rules_text:
        # Split by newlines or sentences
        lines = card.rules_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            line_lower = line.lower()
            
            # Activated abilities (Tap:, Exhaust:, etc.)
            if any(keyword in line_lower for keyword in ['tap:', 'exhaust:', 'activate:']):
                activated_abilities.append(line)
            
            # Triggered abilities (When, Whenever, At)
            elif any(keyword in line_lower for keyword in ['when ', 'whenever ', 'at the ']):
                triggered_abilities.append(line)
            
            # Everything else is passive
            else:
                passive_abilities.append(line)
    
    return Legend(
        card_id=card.card_id,
        name=card.name,
        domain=card.domain,
        exhausted=exhausted,
        abilities=card.rules_text.split('\n') if card.rules_text else [],
        passive_abilities=passive_abilities,
        activated_abilities=activated_abilities,
        triggered_abilities=triggered_abilities
    )


def _build_player_state_from_request(
    request: PlayableCardsRequest,
    hand,
    legend_card: Optional[CardRecord],
    is_opponent: bool = False
) -> PlayerState:
    """Build a complete PlayerState with legend for analysis."""
    
    # Build legend if available
    legend = None
    if legend_card:
        exhausted = request.opponent_legend_exhausted if is_opponent else request.my_legend_exhausted
        legend = _build_legend_from_card(legend_card, exhausted)
    
    # For opponent, we don't have full hand data
    player_hand = [] if is_opponent else hand
    
    return PlayerState(
        name="Opponent" if is_opponent else "Player",
        legend=legend,
        mana_by_rune=request.my_power if not is_opponent else {},
        hand=player_hand,
        hand_size=len(player_hand) if not is_opponent else None
    )


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
    
    Now with full legend integration:
    - Legend synergy detection
    - Exhaustion tracking
    - Opponent legend counter-play
    - Legend-aware sequencing
    """
    try:
        logger.info(
            f"Processing playable cards: turn {request.turn}, "
            f"energy {request.my_energy}, power {request.my_power}, "
            f"legend: {request.legend_id or 'none'}"
        )
        
        # Validate phase
        valid_phases = ["main", "combat", "showdown", "end"]
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
        my_legend_card = get_card(request.legend_id) if request.legend_id else None
        opponent_legend_card = get_card(request.opponent_legend_id) if request.opponent_legend_id else None
        
        if request.legend_id and not my_legend_card:
            logger.warning(f"My legend '{request.legend_id}' not found in database")
        
        if request.opponent_legend_id and not opponent_legend_card:
            logger.warning(f"Opponent legend '{request.opponent_legend_id}' not found in database")
        
        # Build complete player states with legends
        player_state = _build_player_state_from_request(
            request, hand, my_legend_card, is_opponent=False
        )
        
        opponent_state = _build_player_state_from_request(
            request, [], opponent_legend_card, is_opponent=True
        )
        
        # Log legend states
        if player_state.legend:
            logger.info(
                f"Player legend: {player_state.legend.name}, "
                f"exhausted: {player_state.legend.exhausted}, "
                f"abilities: {len(player_state.legend.activated_abilities)} activated, "
                f"{len(player_state.legend.passive_abilities)} passive"
            )
        
        if opponent_state.legend:
            logger.info(
                f"Opponent legend: {opponent_state.legend.name}, "
                f"exhausted: {opponent_state.legend.exhausted}"
            )
        
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
        
        # Analyze with enriched data AND full player states
        advice = analyze_playable_cards(
            hand=hand,
            my_energy=request.my_energy,
            my_power=request.my_power,
            turn=request.turn,
            phase=request.phase,
            battlefields=enriched_battlefields,
            my_legend=my_legend_card,  # Keep for backward compatibility
            opponent_legend=opponent_legend_card,  # Keep for backward compatibility
            my_legend_exhausted=request.my_legend_exhausted,
            opponent_legend_exhausted=request.opponent_legend_exhausted,
            going_first=request.going_first,
            my_score=request.my_score,
            opponent_score=request.opponent_score,
            player_state=player_state,  # NEW: Full player state with legend
            opponent_state=opponent_state,  # NEW: Full opponent state with legend
        )
        
        # Enhanced logging with legend info
        threat_level = advice.scoring_debug.threat_assessment.get('level') if advice.scoring_debug else 'unknown'
        legend_info = ""
        if advice.scoring_debug and 'legend_state' in advice.scoring_debug.threat_assessment:
            legend_state = advice.scoring_debug.threat_assessment['legend_state']
            legend_info = f", legend: {legend_state.get('my_legend', 'none')} ({'exhausted' if legend_state.get('exhausted') else 'ready'})"
        
        logger.info(
            f"Generated advice: {len(advice.primary_strategy)} recommendations, "
            f"threat level: {threat_level}{legend_info}"
        )
        
        # Log if any cards have legend synergies
        synergistic_cards = sum(
            1 for rec in advice.playable_cards 
            if rec.recommended and 'Legend' in (rec.reason or '')
        )
        
        if synergistic_cards > 0:
            logger.info(f"{synergistic_cards} cards have legend synergies")
        
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


@app.get("/legends", response_model=List[CardResponse])
def list_legends_endpoint() -> List[CardResponse]:
    """List all legend cards in the database."""
    # Assuming legends have a specific tag or card type
    # Adjust this based on how you store legends
    all_cards = list_cards()
    
    # Filter for legends (assuming they have "legend" in tags or a specific pattern)
    legends = [
        card for card in all_cards
        if card.tags and any('legend' in tag.lower() for tag in card.tags)
    ]
    
    logger.info(f"Found {len(legends)} legend cards")
    return legends


@app.get("/legends/{legend_id}/synergies", response_model=Dict)
def get_legend_synergies_endpoint(
    legend_id: str,
    hand_ids: List[str] = Query([])
) -> Dict:
    """
    Analyze synergies between a legend and specific cards.
    Useful for deck building or understanding legend interactions.
    """
    from legend_analysis import analyze_legend_synergy, evaluate_legend_state
    
    legend_card = get_card(legend_id)
    if not legend_card:
        raise HTTPException(status_code=404, detail="Legend not found")
    
    # Build legend object
    legend = _build_legend_from_card(legend_card, exhausted=False)
    
    # Build minimal player state
    player_state = PlayerState(
        name="Player",
        legend=legend,
        hand=[]
    )
    
    # Evaluate legend state
    legend_eval = evaluate_legend_state(player_state)
    
    # If hand_ids provided, analyze synergies
    synergy_analysis = {}
    if hand_ids:
        hand, missing = make_hand_from_ids(hand_ids)
        
        for card in hand:
            synergies, total_modifier = analyze_legend_synergy(
                card, player_state, None, None
            )
            
            synergy_analysis[card.card_id] = {
                "card_name": card.name,
                "total_modifier": total_modifier,
                "synergies": [
                    {
                        "type": s.synergy_type.value,
                        "description": s.description,
                        "value": s.value_modifier,
                        "timing": s.timing
                    }
                    for s in synergies
                ]
            }
    
    return {
        "legend": {
            "card_id": legend_card.card_id,
            "name": legend_card.name,
            "domain": legend_card.domain,
            "can_activate": legend_eval.can_activate,
            "value_score": legend_eval.value_score,
            "activated_abilities": legend_eval.activated_abilities,
            "passive_abilities": legend_eval.passive_abilities,
            "triggered_abilities": legend_eval.triggered_abilities
        },
        "card_synergies": synergy_analysis
    }
    """Returns the number of cards currently stored in cards.db."""
    total = count_cards()
    return {"card_count": total}