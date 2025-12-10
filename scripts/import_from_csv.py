# scripts/import_cards_from_csv.py

import csv
from pathlib import Path

from card_db import CardRecord, upsert_card, init_db, DB_PATH
from game_state import Rune, CardType


CSV_PATH = Path("data/cards.csv")


def parse_tags(raw: str) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def import_cards_from_csv(csv_path: Path) -> int:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    init_db()

    imported_count = 0

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for line_num, row in enumerate(reader, start=2):  # start=2 (line after header)
            # Skip completely empty rows
            if not row or all(v in (None, "", " ") for v in row.values()):
                print(f"Skipping empty row at line {line_num}")
                continue

            raw_id = (row.get("card_id") or "").strip()
            if not raw_id:
                print(f"Skipping row {line_num}: missing card_id -> {row}")
                continue

            raw_type = (row.get("card_type") or "").strip().lower()
            raw_domain = (row.get("domain") or "").strip().lower()

            if not raw_type or not raw_domain:
                print(
                    f"Skipping row {line_num}: missing card_type or domain "
                    f"(card_type='{raw_type}', domain='{raw_domain}') -> {row}"
                )
                continue

            try:
                card_type = CardType(raw_type)
            except ValueError as e:
                print(f"Skipping row {line_num}: invalid card_type '{raw_type}' -> {e}")
                continue

            try:
                domain = Rune(raw_domain)
            except ValueError as e:
                print(f"Skipping row {line_num}: invalid domain '{raw_domain}' -> {e}")
                continue

            # Safe integer parsing
            def to_int(value, default=0):
                s = (value or "").strip()
                if not s:
                    return default
                try:
                    return int(s)
                except ValueError:
                    return default

            record = CardRecord(
                card_id=raw_id,
                name=(row.get("name") or "").strip(),
                card_type=card_type,
                domain=domain,
                energy_cost=to_int(row.get("energy_cost"), 0),
                power_cost=to_int(row.get("power_cost"), 0),
                might=to_int(row.get("might"), None),
                tags=parse_tags(row.get("tags") or ""),
                keywords=parse_tags(row.get("keywords") or ""),
                rules_text=(row.get("rules_text") or "").strip() or None,
                set_name=(row.get("set_name") or "").strip() or None,
            )

            upsert_card(record)
            imported_count += 1

    return imported_count


def main() -> None:
    count = import_cards_from_csv(CSV_PATH)
    print(f"Imported/updated {count} cards from {CSV_PATH} into db {DB_PATH.resolve()}")


if __name__ == "__main__":
    main()
