# Riftbound advisor
# advisor.py

from typing import List
from game_state import GameState, CardType, Phase
from logger_config import (
    advisor_logger,
    log_game_state,
    log_advisor_decision,
    log_battlefield_analysis,
)

# Import models
from advisor_models import (
    PlayableCardRecommendation,
    PlayableCardsAdvice,
    ScoringDebugInfo,
)

# Import evaluation functions
from card_evaluation import (
    get_all_playable_cards,
    describe_card,
    calculate_card_value,
    assess_threat_level,
    should_hold_card,
    calculate_mana_efficiency_score,
)

# Import battlefield analysis
from battlefield_analysis import (
    analyze_battlefield,
    find_best_battlefield_for_unit,
)

# Import legend analysis
from legend_analysis import (
    analyze_legend_synergy,
)


def get_playable_cards_advice(state: GameState) -> PlayableCardsAdvice:
    """
    Analyze playable cards and provide structured recommendations.
    
    Considers:
    - Mana efficiency
    - Board state
    - Tempo
    - Card type synergies
    - Turn and phase context
    """
    advisor_logger.info(f"Processing playable cards advice for turn {state.turn}, phase {state.phase.value}")
    log_game_state(
        advisor_logger,
        state,
        "playable_cards",
        turn=state.turn,
        phase=state.phase.value,
        my_mana=state.me.mana_total,
        hand_size=len(state.me.hand),
        battlefield_count=len(state.battlefields)
    )
    
    if state.phase == Phase.MULLIGAN:
        return PlayableCardsAdvice(
            playable_cards=[],
            recommended_plays=[],
            summary="No playable cards advice during mulligan phase. Use /advice/mulligan instead.",
        )
    
    # ... rest of your get_playable_cards_advice implementation stays the same ...