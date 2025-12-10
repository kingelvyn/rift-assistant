# Riftbound Assistant

A Python-based assistant for the Riftbound card game by Riot Games. This project provides game state analysis and strategic advice to help players improve their gameplay.

## Features

- **Game State Analysis**: Reads and processes game state information
- **Strategic Advice**: Provides suggestions and recommendations based on current game state
- **Local Card Database**: Complete card catalog stored in SQLite database
- **RESTful API**: FastAPI-based API for accessing game state and advice
- **Future Support**: Plans to support screen parsing for simulators (TCG Arena, Tabletop Simulator)

## Project Goals

1. **Reads or receives a GameState** - Accepts game state data for analysis
2. **Returns advice / suggestions** - Provides strategic recommendations
3. **Has a local card catalog database** - Complete card database (✅ Complete)
4. **Aims to eventually support screen parsing** - Future support for TCG Arena and Tabletop Simulator

## Installation

1. Clone this repository:
```bash
git clone <your-github-repo-url>
cd riftbound-assistant
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
- `GET /cards` - List all cards in the database (with optional filters)
- `GET /cards/{card_id}` - Get a specific card by ID
- `POST /cards` - Create or update a card
- `GET /cards/count` - Get the total number of cards in the database

### Example: Getting Advice

```python
import requests

game_state = {
    "turn": 3,
    "phase": "main",
    "active_player": "me",
    "me": {
        "mana_total": 3,
        "mana_by_rune": {"calm": 1, "mind": 2},
        "hand": [
            {
                "card_id": "VeilDancer",
                "name": "Veil Dancer",
                "card_type": "unit",
                "domain": "mind",
                "energy_cost": 2,
                "power_cost": 1
            }
        ]
    },
    "opponent": {
        "mana_total": 2
    },
    "lanes": []
}

response = requests.post("http://localhost:8000/advice", json=game_state)
print(response.json())
```

### Running the Demo

See example game states and advice:
```bash
python demo.py
```

## Project Structure

```
riftbound-assistant/
├── api.py              # FastAPI application and endpoints
├── advisor.py          # Strategic advice logic
├── card_db.py          # SQLite database operations
├── game_state.py       # Game state data models
├── demo.py             # Example usage and demos
├── requirements.txt    # Python dependencies
├── cards.db            # SQLite card database
├── data/
│   └── cards.csv       # Card data CSV
└── scripts/
    ├── import_from_csv.py  # Import cards from CSV
    └── update_csv.py       # Update CSV data
```

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

## Future Enhancements

- Screen capture and parsing for TCG Arena
- Tabletop Simulator integration
- Machine learning-based advice
- Advanced game state analysis
- Win probability calculations

## License

[Add your license here]

## Contributing

[Add contribution guidelines if needed]

