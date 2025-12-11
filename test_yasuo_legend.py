#!/usr/bin/env python3
"""
Test script for the legend-aware advisor with Yasuo.
Run this to test the advisor with Yasuo legend abilities.
"""

import json
import requests
from pprint import pprint

# Load the test board state
with open("test_yasuo_legend.json", "r") as f:
    game_state = json.load(f)

# Test the playable cards advisor endpoint
print("=" * 80)
print("Testing /advice/playable endpoint with Yasuo Legend")
print("=" * 80)
print("\nBoard State:")
print(f"  Turn: {game_state['turn']}")
print(f"  Phase: {game_state['phase']}")
print(f"  My Mana: {game_state['me']['mana_total']}")

# Display legend info
if game_state['me'].get('legend'):
    legend = game_state['me']['legend']
    print(f"\n  My Legend: {legend.get('name', legend.get('card_id'))}")
    print(f"    Domain: {legend.get('domain')}")
    print(f"    Exhausted: {legend.get('exhausted', False)}")
    if legend.get('activated_abilities'):
        print(f"    Activated Abilities:")
        for ab in legend['activated_abilities']:
            print(f"      - {ab}")

if game_state['opponent'].get('legend'):
    op_legend = game_state['opponent']['legend']
    print(f"\n  Opponent Legend: {op_legend.get('name', op_legend.get('card_id'))}")
    print(f"    Domain: {op_legend.get('domain')}")
    print(f"    Exhausted: {op_legend.get('exhausted', False)}")
    if op_legend.get('triggered_abilities'):
        print(f"    Triggered Abilities:")
        for ab in op_legend['triggered_abilities']:
            print(f"      - {ab}")

print(f"\n  Battlefields:")
for i, battlefield in enumerate(game_state['battlefields']):
    if battlefield['my_unit']:
        print(f"    Battlefield {i}: My {battlefield['my_unit']['might']} might unit")
    elif battlefield['op_unit']:
        print(f"    Battlefield {i}: Opponent's {battlefield['op_unit']['might']} might {battlefield['op_unit']['card_id']}")
    else:
        print(f"    Battlefield {i}: Empty")

print(f"\n  Hand: {len(game_state['me']['hand'])} cards")
for card in game_state['me']['hand']:
    rules_note = ""
    if card.get('rules_text'):
        rules_preview = card['rules_text'][:50] + "..." if len(card.get('rules_text', '')) > 50 else card.get('rules_text', '')
        rules_note = f" ({rules_preview})"
    print(f"    - {card['name']} ({card['card_type']}, {card['energy_cost']} cost, {card.get('might', 'N/A')} might){rules_note}")

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
        if rec.get('legend_synergy'):
            print(f"  Legend Synergy: {rec['legend_synergy']}")
    
    print("\n" + "=" * 80)
    print("Expected Behavior:")
    print("=" * 80)
    print("1. Bard - Mercurial should show legend synergy (can exhaust Yasuo)")
    print("2. Royal Entourage should show legend synergy (can ready/exhaust legend)")
    print("3. Last Breath should show legend synergy (Yasuo can move units to support)")
    print("4. Summary should mention both your and opponent's legend states")
    print("5. Opponent legend (Annie) should be noted in summary")
    
except requests.exceptions.ConnectionError:
    print("ERROR: Could not connect to API server.")
    print("Make sure the server is running: uvicorn api:app --reload")
except requests.exceptions.HTTPError as e:
    print(f"ERROR: HTTP {e.response.status_code}")
    print(e.response.text)
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

