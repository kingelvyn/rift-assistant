"""
Logging configuration for ML integration.
Structured JSON logging for game states, decisions, and recommendations.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Create logs directory if it doesn't exist
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# ML-specific log file (JSON lines format for easy parsing)
ML_LOG_FILE = LOGS_DIR / "ml_training_data.jsonl"


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON for ML training data."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add any extra fields passed to the logger
        if hasattr(record, "data"):
            log_data.update(record.data)
        
        return json.dumps(log_data, default=str)


def setup_logging(log_level: str = "INFO") -> None:
    """Setup logging configuration for the advisor."""
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Console handler (human-readable)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    
    # File handler (human-readable)
    file_handler = logging.FileHandler(LOGS_DIR / "advisor.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(console_formatter)
    
    # ML training data handler (JSON lines format)
    ml_handler = logging.FileHandler(ML_LOG_FILE, mode="a")
    ml_handler.setLevel(logging.INFO)
    ml_handler.setFormatter(JSONFormatter())
    
    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(ml_handler)


def log_game_state(
    logger: logging.Logger,
    state: Any,
    advisor_type: str,
    **extra_data: Any
) -> None:
    """Log game state for ML training."""
    log_data = {
        "event_type": "game_state",
        "advisor_type": advisor_type,
        "game_state": _serialize_game_state(state),
        **extra_data
    }
    logger.info("Game state logged", extra={"data": log_data})


def log_advisor_decision(
    logger: logging.Logger,
    state: Any,
    advisor_type: str,
    recommendations: Any,
    **extra_data: Any
) -> None:
    """Log advisor decisions for ML training."""
    log_data = {
        "event_type": "advisor_decision",
        "advisor_type": advisor_type,
        "game_state": _serialize_game_state(state),
        "recommendations": _serialize_recommendations(recommendations),
        **extra_data
    }
    logger.info("Advisor decision logged", extra={"data": log_data})


def log_card_playability(
    logger: logging.Logger,
    card_id: str,
    playable: bool,
    reason: str,
    **extra_data: Any
) -> None:
    """Log card playability checks."""
    log_data = {
        "event_type": "card_playability",
        "card_id": card_id,
        "playable": playable,
        "reason": reason,
        **extra_data
    }
    logger.debug("Card playability checked", extra={"data": log_data})


def log_legend_interaction(
    logger: logging.Logger,
    card_id: str,
    legend_id: Optional[str],
    interaction_type: str,
    **extra_data: Any
) -> None:
    """Log legend ability interactions."""
    log_data = {
        "event_type": "legend_interaction",
        "card_id": card_id,
        "legend_id": legend_id,
        "interaction_type": interaction_type,
        **extra_data
    }
    logger.info("Legend interaction logged", extra={"data": log_data})


def log_battlefield_analysis(
    logger: logging.Logger,
    battlefield_analyses: list,
    **extra_data: Any
) -> None:
    """Log battlefield analysis results."""
    log_data = {
        "event_type": "battlefield_analysis",
        "battlefield_states": battlefield_analyses,
        **extra_data
    }
    logger.debug("Battlefield analysis logged", extra={"data": log_data})


def _serialize_game_state(state: Any) -> Dict[str, Any]:
    """Serialize game state to dict for logging."""
    if hasattr(state, "model_dump"):
        return state.model_dump()
    elif hasattr(state, "dict"):
        return state.dict()
    elif isinstance(state, dict):
        return state
    else:
        return {"raw": str(state)}


def _serialize_recommendations(recommendations: Any) -> Dict[str, Any]:
    """Serialize recommendations to dict for logging."""
    if hasattr(recommendations, "model_dump"):
        return recommendations.model_dump()
    elif hasattr(recommendations, "dict"):
        return recommendations.dict()
    elif isinstance(recommendations, dict):
        return recommendations
    elif isinstance(recommendations, list):
        return [item.model_dump() if hasattr(item, "model_dump") else item for item in recommendations]
    else:
        return {"raw": str(recommendations)}


# Initialize logger for advisor module
advisor_logger = logging.getLogger("advisor")

