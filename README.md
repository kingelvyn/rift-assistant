# Riftbound Assistant

A Python-based assistant for the Riftbound card game by Riot Games. This project provides game state analysis and strategic advice to help players improve their gameplay. This is not meant to provide the most optimal play at all times (yet), but to offer AI suggestive advice. More useful for beginners / people learning to play (new players or new decks). Also intended to give advice for 1v1 scenarios, not for 2v2 or free for all.

## Features

- **Game State Analysis**: Reads and processes game state information
- **Strategic Advice**: Provides suggestions and recommendations based on current game state
- **Battlefield-Aware Recommendations**: Analyzes battlefield states and recommends optimal unit placement
- **Legend Ability Integration**: Considers both your and opponent's legend abilities in recommendations
- **Local Card Database**: Complete card catalog stored in SQLite database
- **RESTful API**: FastAPI-based API for accessing game state and advice
- **ML Training Data Logging**: Structured logging for future machine learning integration
- **Future Support**: Plans to support screen parsing for simulators (TCG Arena, Tabletop Simulator)

## Project Goals

1. **Reads or receives a GameState** - Accepts game state data for analysis ✅
2. **Returns advice / suggestions** - Provides strategic recommendations ✅
3. **Has a local card catalog database** - Complete card database ✅
4. **Battlefield-aware decisions** - Recommends optimal unit placement ✅
5. **Legend ability awareness** - Considers legend abilities in recommendations ✅
6. **Aims to eventually support screen parsing** - Future support for TCG Arena and Tabletop Simulator

## Installation

1. Clone this repository:
```bash
git clone https://github.com/kingelvyn/rift-assistant.git
cd rift-assistant
```

2. Create a virtual environment:
```bash
python -m venv venv
```

3. Activate the virtual environment:
- Windows: `venv\Scripts\activate`
- macOS/Linux: `source venv/bin/activate`

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Initialize the database:
```bash
python -c "from card_db import init_db; init_db()"
```

## Usage

### Running the API Server

Start the FastAPI server:
```bash
uvicorn api:app --reload
```

The API will be available at `http://localhost:8000`

### API Endpoints

- `GET /health` - Health check endpoint
- `POST /advice` - Get strategic advice based on game state
- `POST /advice/mulligan` - Get mulligan recommendations (which cards to keep/mulligan)
- `POST /advice/playable` - Get playable cards with battlefield placement recommendations
- `GET /cards` - List all cards in the database (with optional filters)
- `GET /cards/{card_id}` - Get a specific card by ID
- `POST /cards` - Create or update a card
- `GET /cards/count` - Get the total number of cards in the database

### Example: Getting Playable Cards Advice
# POST this json 
```python
{
  "hand_ids": ["OGN-199", "OGN-199", "OGN-055", "OGN-189"],
  "legend_id": "OGN-076",
  "opponent_legend_id": "OGN-263",
  "my_energy": 3,
  "my_power": {
    "chaos": 2,
    "calm": 1
  },
  "turn": 2,
  "phase": "main",
  "going_first": true,
  "battlefields": [
    {
      "battlefield_id": null,
      "my_unit": {
        "card_id": "OGN-034",
        "name": "Goblin Scout",
        "might": 2
      },
      "opponent_unit": null
    },
    {
      "battlefield_id": null,
      "my_unit": null,
      "opponent_unit": {
        "card_id": "OGN-197",
        "name": "Teemo",
        "might": 1
      }
    }
  ],
  "my_legend_exhausted": false,
  "opponent_legend_exhausted": true,
  "my_health": 20,
  "opponent_health": 18
}

response = requests.post("http://localhost:8000/advice/playable", json=game_state)
print(response.json())
```


## Project Structure

```
riftbound-assistant/
├── api.py                  # FastAPI application and endpoints
├── advisor.py              # Strategic advice logic with battlefield and legend awareness
├── card_db.py              # SQLite database operations
├── game_state.py           # Game state data models (GameState, Battlefield, Legend, etc.)
├── logger_config.py        # Logging configuration for ML training data
├── demo.py                 # Example usage and demos
├── requirements.txt        # Python dependencies
├── cards.db                # SQLite card database
├── data/
│   └── cards.csv           # Card data CSV
├── scripts/
│   ├── import_from_csv.py  # Import cards from CSV
│   └── update_csv.py       # Update CSV data
└── logs/
    ├── ml_training_data.jsonl  # JSON Lines format training data
    ├── advisor.log             # Human-readable logs
    └── README.md               # Logging documentation
```

## Advisor Features

### Mulligan Advisor (`/advice/mulligan`)
- Analyzes opening hand
- Recommends which cards to keep vs. mulligan
- Considers curve, unit count, and card costs
- Provides reasoning for each decision

### Playable Cards Advisor (`/advice/playable`)
- **Battlefield-Aware**: Recommends optimal battlefield placement for units
  - Prioritizes empty battlefields for early game
  - Suggests contesting battlefields where you can win trades
  - Avoids overcommitting to winning battlefields
- **Legend Integration**: Considers legend abilities
  - Cards requiring legend exhaustion (e.g., Bard - Mercurial)
  - Legend activated abilities that support plays
  - Opponent legend abilities that might counter your plays
- **Mana Efficiency**: Calculates and reports mana usage
- **Priority Ranking**: Orders recommendations by importance

## Development

### Adding Cards

Cards can be added via the API or by importing from CSV:

```bash
python scripts/import_from_csv.py
```

### Database Schema

The card database stores:
- Card ID, name, type, domain (rune)
- Energy and power costs
- Might (for units)
- Tags, keywords, rules text
- Set name

### Logging and ML Training Data

The advisor automatically logs all game states and decisions to `logs/ml_training_data.jsonl` in JSON Lines format. This data can be used for future ML model training.

See `logs/README.md` for details on the logging format and how to use the data.

## Architecture Overview

The project is designed with modularity in mind:

1. **Game State Layer** (`game_state.py`)
   - Represents game state with Pydantic models
   - Supports battlefields, legends, units, cards in hand

2. **Advisor Layer** (`playable_cards_advisor.py, mulligan_advisor`)
   - Rule-based decision making
   - Battlefield analysis and placement recommendations
   - Legend ability integration
   - Structured recommendations with priorities

3. **API Layer** (`api.py`)
   - FastAPI REST endpoints
   - Request/response models
   - Automatic logging initialization

4. **Data Layer** (`card_db.py`)
   - SQLite database for card catalog
   - CRUD operations for cards

5. **Logging Layer** (`logger_config.py`)
   - Structured JSON logging for ML training
   - Human-readable logs for debugging

## Future Enhancements

- Screen capture and parsing for TCG Arena
- Tabletop Simulator integration
- Machine learning-based advice (using logged training data)
- Advanced game state analysis
- Win probability calculations
- Deck building recommendations
- Matchup analysis

## License

See [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
