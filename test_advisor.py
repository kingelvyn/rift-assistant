#!/usr/bin/env python3
"""
Test script for the battlefield-aware advisor.
Run this to test the advisor with the sample board state.
"""

import json
import requests
from pprint import pprint

# Load the test board state
with open("test_board_state.json", "r") as f:
    game_state = json.load(f)

# Test the playable cards advisor endpoint
print("=" * 80)
print("Testing /advice/playable endpoint with Deadbloom (8 might) in battlefield 1")
print("=" * 80)
print("\nBoard State:")
print(f"  Turn: {game_state['turn']}")
print(f"  Phase: {game_state['phase']}")
print(f"  My Mana: {game_state['me']['mana_total']}")
print(f"  Battlefields:")
for i, battlefield in enumerate(game_state['battlefields']):
    if battlefield['my_unit']:
        print(f"    Battlefield {i}: My {battlefield['my_unit']['might']} might unit")
    elif battlefield['op_unit']:
        print(f"    Battlefield {i}: Opponent's {battlefield['op_unit']['might']} might {battlefield['op_unit']['card_id']}")
    else:
        print(f"    Battlefield {i}: Empty")
print(f"\n  Hand: {len(game_state['me']['hand'])} cards")
for card in game_state['me']['hand']:
    print(f"    - {card['name']} ({card['card_type']}, {card['energy_cost']} cost, {card.get('might', 'N/A')} might)")

print("\n" + "=" * 80)
print("POSTing to http://localhost:8000/advice/playable")
print("=" * 80 + "\n")

try:
    response = requests.post(
        "http://localhost:8000/advice/playable",
        json=game_state,
        headers={"Content-Type": "application/json"}
    )
    response.raise_for_status()
    
    advice = response.json()
    
    print("ADVISOR RESPONSE:")
    print("-" * 80)
    print(f"Summary: {advice['summary']}")
    if advice.get('mana_efficiency_note'):
        print(f"Mana Efficiency: {advice['mana_efficiency_note']}")
    
    print(f"\nRecommended Plays: {advice['recommended_plays']}")
    
    print("\nDetailed Recommendations:")
    print("-" * 80)
    for rec in advice['playable_cards']:
        print(f"\n{rec['name']} ({rec['card_type']}, {rec['energy_cost']} cost)")
        print(f"  Priority: {rec['priority']}")
        print(f"  Recommended: {rec['recommended']}")
        print(f"  Reason: {rec['reason']}")
        if rec.get('battlefield_placement'):
            bp = rec['battlefield_placement']
            print(f"  Battlefield Placement: Battlefield {bp['battlefield_index']} - {bp['reason']} (Priority: {bp['priority']})")
    
    print("\n" + "=" * 80)
    print("Expected Behavior:")
    print("=" * 80)
    print("1. Small units (1-2 might) should be recommended for empty Battlefield 0")
    print("2. Big unit (9 might) should be recommended for contested Battlefield 1 (can beat 8 might Deadbloom)")
    print("3. Medium unit (5 might) should NOT be recommended for Battlefield 1 (can't win)")
    print("4. Removal spell should be recommended to answer the Deadbloom")
    print("5. Only 2 battlefields in Riftbound 1v1 scenario")
    
except requests.exceptions.ConnectionError:
    print("ERROR: Could not connect to API server.")
    print("Make sure the server is running: uvicorn api:app --reload")
except requests.exceptions.HTTPError as e:
    print(f"ERROR: HTTP {e.response.status_code}")
    print(e.response.text)
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

