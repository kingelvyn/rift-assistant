# Riftbound TCG Arena Advisor

A cross platform, low resource **Riftbound / TCG Arena advisor** written in Python.

This project does **not** play the game for you. Instead, it:
- Captures the TCG Arena window from your screen
- Reconstructs a simplified view of the current game state
- Provides **suggested plays and research style insights** through a local web interface

Think of it as a personal coach and analysis tool that helps you understand:
- What your board and hand look like in a structured way
- Which plays are likely strong in the current situation
- How different choices might affect your win chance over time

---

## High level goals

1. **Low resource advisor**
   - Lightweight Python service that can run alongside TCG Arena on typical hardware
   - No heavy deep learning required to get value, but ML hooks are possible later

2. **Cross platform**
   - Target Windows and macOS first
   - All logic in Python so it can run on any platform that supports Python and OpenCV

3. **Suggestive and research focused**
   - Tool gives advice, odds, and analysis
   - It does not send input to the game and is not an automation bot
   - Meant for learning, deck research, and post game review

4. **Modular and extensible**
   - Clear separation between:
     - Screen capture
     - Visual recognition
     - Game state representation
     - Advisor logic
     - API and user interface

---

## Architecture overview

The project is divided into three main layers:

1. **Observation layer**
   - Captures the game window as images
   - Crops important regions:
     - Player hand
     - Board lanes
     - Mana, health, turn indicator
   - Uses template matching or simple ML models to identify cards and units

2. **State layer**
   - Converts raw visual info into a structured game state object, for example:
     ```json
     {
       "turn": 5,
       "my_hp": 18,
       "opponent_hp": 14,
       "my_mana": 5,
       "my_hand": ["CardA", "CardB", "CardC"],
       "lanes": [
         {"my_unit": "UnitX", "op_unit": "UnitY"},
         {"my_unit": null, "op_unit": "UnitZ"}
       ]
     }
     ```

3. **Advisor layer**
   - Accepts a game state and returns:
     - Suggested plays or lines of play
     - Explanation text
     - Any estimated metrics such as win probability
   - Starts with rule based logic, later can use ML models trained on recorded games

A small **FastAPI** service exposes this over HTTP, and a browser based UI displays the advice.

---

## Folder layout

Planned folder structure:

```text
riftbound-tcg-advisor/
│
├─ README.md
├─ requirements.txt
├─ pyproject.toml           # optional, if you want to use poetry or similar
│
├─ src/
│  ├─ capture/              # Screen capture and window handling
│  │  ├─ __init__.py
│  │  ├─ screen_capture.py  # Grab frames from the screen
│  │  └─ regions.py         # Definitions of pixel regions for hand, board, mana, etc.
│  │
│  ├─ vision/               # Computer vision utilities and card recognition
│  │  ├─ __init__.py
│  │  ├─ card_recognizer.py # Template matching or ML based card identification
│  │  ├─ ocr.py             # Optional: read numbers or text for HP, mana, etc.
│  │  └─ card_templates/    # Image crops of individual cards (templates)
│  │
│  ├─ state/                # Game state representation
│  │  ├─ __init__.py
│  │  ├─ game_state.py      # Data classes for state (hand, board, mana)
│  │  └─ encoder.py         # Convert raw vision output into a clean GameState object
│  │
│  ├─ advisor/              # Advisor logic and models
│  │  ├─ __init__.py
│  │  ├─ rules_engine.py    # Initial rule based advisor
│  │  ├─ ml_model.py        # Placeholder for later ML based decision making
│  │  └─ features.py        # Feature extraction from GameState for models
│  │
│  ├─ api/                  # Local API for UI and tools
│  │  ├─ __init__.py
│  │  └─ server.py          # FastAPI app that exposes /state and /advice endpoints
│  │
│  ├─ ui/                   # Front end, simple web UI
│  │  ├─ __init__.py
│  │  ├─ templates/         # HTML templates if using server side rendering
│  │  └─ static/            # CSS, JS
│  │
│  └─ main.py               # Entry point, starts capture loop and FastAPI server
│
├─ data/
│  ├─ raw_screens/          # Raw screenshots taken during games
│  ├─ annotated/            # Cropped and labeled card or board images
│  └─ models/               # Saved ML models (if used)
│
├─ tests/
│  ├─ test_capture.py
│  ├─ test_state.py
│  ├─ test_advisor.py
│  └─ ...
│
└─ scripts/
   ├─ grab_screenshots.py   # Utility scripts, like capturing sample frames
   └─ label_cards.py        # Simple CLI tool to label card crops
