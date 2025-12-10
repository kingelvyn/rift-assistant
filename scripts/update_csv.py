# scripts/update_csv.py
#
# Fetches card data from riftbound.gg (dotgg JSON),
# writes data/cards.csv in the format expected by import_from_csv.py.

import csv
from pathlib import Path
from typing import Dict, Iterable, List

import requests

from game_state import Rune, CardType

# Output CSV path
CSV_PATH = Path("data/cards.csv")

# DotGG Riftbound cards endpoint
CARDS_JSON_URL = "https://api.dotgg.gg/cgfw/getcards?game=riftbound&mode=indexed&cache=2726"


def fetch_cards_json() -> Dict:
    """Fetch the raw JSON from dotgg."""
    resp = requests.get(CARDS_JSON_URL, timeout=20)
    resp.raise_for_status()
    return resp.json()


def iter_cards(raw: Dict) -> Iterable[Dict]:
    """
    Convert dotgg structure:
      { "names": [...], "data": [[...], [...], ...] }
    into a stream of dicts like { "id": "...", "name": "...", ... }.
    """
    names: List[str] = raw.get("names") or []
    data_rows: List[List] = raw.get("data") or []

    if not names or not data_rows:
        raise ValueError("Could not find 'names' and 'data' in dotgg JSON.")

    for row in data_rows:
        # Some rows may be shorter/longer, so zip safely.
        card_dict = dict(zip(names, row))
        yield card_dict


# ------------------ Normalization helpers ------------------ #

def normalize_rune_from_colors(colors_value) -> Rune:
    """
    Dotgg 'color' field is a list of strings: e.g. ["Chaos"] or ["Calm","Mind"].
    We pick the first non-colorless color, or COLORLESS if that is all there is.
    """
    if not colors_value:
        raise ValueError("Missing color")

    if isinstance(colors_value, list):
        non_colorless = []
        for c in colors_value:
            s = str(c).strip().lower()
            if s == "colorless":
                continue
            non_colorless.append(s)

        if non_colorless:
            # Use the first non-colorless color
            return Rune(non_colorless[0])

        # All colors were colorless
        return Rune.COLORLESS
    else:
        s = str(colors_value).strip().lower()
        if s == "colorless":
            return Rune.COLORLESS
        return Rune(s)


def normalize_card_type(type_str: str) -> CardType:
    """
    Dotgg 'type' values include: "Unit", "Spell", "Gear", "Legend",
    "Champion", "Battlefield" etc.
    We map them to our 3 types; Battlefield and some others we skip for now.
    """
    s = (type_str or "").strip().lower()

    # Units / legends / champions → UNIT
    if s in ("unit", "legend", "champion", "champion unit"):
        return CardType.UNIT

    # Gear / equipment / items → GEAR
    if s in ("gear", "equipment", "item"):
        return CardType.GEAR

    # Spell-like
    if s in ("spell", "action", "reaction"):
        return CardType.SPELL

    # Battlefield
    if s in ("battlefield"):
        return CardType.BATTLEFIELD

    # Other unsupported types
    raise ValueError(f"Unsupported card_type from dotgg: {type_str!r}")


def to_int_or_none(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(float(s))  # handle "2", "2.0"
    except ValueError:
        return None


def to_int_or_zero(value) -> int:
    v = to_int_or_none(value)
    return v if v is not None else 0


# ------------------ CSV writing ------------------ #

def write_csv_from_dotgg_cards(cards: Iterable[Dict], csv_path: Path) -> int:
    """
    Convert dotgg card dicts → our CSV schema.
    Returns number of cards written.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "card_id",
        "name",
        "card_type",
        "domain",
        "energy_cost",
        "power_cost",
        "might",
        "tags",
        "keywords",
        "rules_text",
        "set_name",
    ]

    count = 0

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for c in cards:
            # Dotgg columns (from raw["names"]):
            # ["id","slug","name","effect","flavor","color","cost","type","might","tags","set_name", ...]
            raw_id = str(c.get("id") or "").strip()
            if not raw_id:
                continue

            name = (c.get("name") or "").strip()
            raw_type = c.get("type") or ""
            raw_color = c.get("color")  # list of colors
            raw_might = c.get("might")
            raw_cost = c.get("cost")
            raw_tags = c.get("tags") or []
            set_name = (c.get("set_name") or "").strip()
            rules_text = (c.get("effect") or "").strip()

            try:
                card_type = normalize_card_type(raw_type)
            except ValueError as e:
                print(f"Skipping {raw_id} ({name}): {e}")
                continue

            try:
                domain = normalize_rune_from_colors(raw_color)
            except ValueError as e:
                # e.g. Colorless / unsupported colors
                print(f"Skipping {raw_id} ({name}): {e}")
                continue

            energy_cost = to_int_or_zero(raw_cost)
            power_cost = 0  # dotgg doesn't expose power-cost separately yet
            might = to_int_or_none(raw_might)

            # tags from dotgg are usually a list, e.g. ["Ahri","Ionia"]
            if isinstance(raw_tags, list):
                tags_list = [str(t).strip() for t in raw_tags if str(t).strip()]
            elif isinstance(raw_tags, str):
                tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
            else:
                tags_list = []

            # We don't have separate keywords here yet
            keywords_list: list[str] = []

            writer.writerow(
                {
                    "card_id": raw_id,
                    "name": name,
                    "card_type": card_type.value,
                    "domain": domain.value,
                    "energy_cost": energy_cost,
                    "power_cost": power_cost,
                    "might": "" if might is None else might,
                    "tags": ", ".join(tags_list),
                    "keywords": ", ".join(keywords_list),
                    "rules_text": rules_text,
                    "set_name": set_name,
                }
            )
            count += 1

    return count


def main() -> None:
    print(f"Fetching card data from gallery JSON: {CARDS_JSON_URL}")
    raw = fetch_cards_json()
    cards_list = list(iter_cards(raw))
    print(f"Found {len(cards_list)} raw card rows from dotgg.")

    written = write_csv_from_dotgg_cards(cards_list, CSV_PATH)
    print(f"Wrote {written} cards to {CSV_PATH}")


if __name__ == "__main__":
    main()