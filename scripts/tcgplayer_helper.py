# tcgplayer_api.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Any, List
import requests


TCG_SEARCH_URL = "https://mp-search-api.tcgplayer.com/v1/search/request"


@dataclass(frozen=True)
class TcgCardAttrs:
    product_id: int
    product_name: str
    set_name: Optional[str]
    number: Optional[str]
    domain: Optional[str]
    card_types: List[str]
    energy_cost: Optional[int]
    power_cost: Optional[int]
    might: Optional[int]


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def build_riftbound_payload(
    query: str = "",
    from_: int = 0,
    size: int = 24,
    product_line: str = "riftbound-league-of-legends-trading-card-game",
    shipping_country: str = "US",
) -> Dict[str, Any]:
    """
    Matches what you captured in DevTools/curl. Keep this centralized so you can tweak it easily.
    """
    return {
        "algorithm": "sales_dismax",
        "from": from_,
        "size": size,
        "filters": {
            "term": {"productLineName": [product_line]},
            "range": {},
            "match": {},
        },
        "listingSearch": {
            "context": {"cart": {}},
            "filters": {
                "term": {"sellerStatus": "Live", "channelId": 0},
                "range": {"quantity": {"gte": 1}},
                "exclude": {"channelExclusion": 0},
            },
        },
        "context": {
            "cart": {},
            "shippingCountry": shipping_country,
            "userProfile": {"productLineAffinity": "Riftbound: League of Legends Trading Card Game"},
        },
        "settings": {"useFuzzySearch": True, "didYouMean": {}},
        "sort": {},
    }


def search_riftbound(
    query: str,
    from_: int = 0,
    size: int = 24,
    mpfev: str = "4622",
    timeout: int = 20,
) -> Dict[str, Any]:
    """
    Sends the POST body and returns raw JSON.
    Note: q/isList/mpfev are query params; the payload is JSON body.
    """
    params = {"q": query, "isList": "false", "mpfev": mpfev}

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://www.tcgplayer.com",
        "referer": "https://www.tcgplayer.com/",
        # user-agent optional, but helps look like a normal browser request
        "user-agent": "Mozilla/5.0",
    }

    payload = build_riftbound_payload(query=query, from_=from_, size=size)

    resp = requests.post(TCG_SEARCH_URL, params=params, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def iter_tcg_products(raw: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """
    Yields each product object in the search response.
    """
    results = raw.get("results") or []
    for block in results:
        for prod in (block.get("results") or []):
            yield prod


def extract_card_attrs(product: Dict[str, Any]) -> Optional[TcgCardAttrs]:
    """
    Pulls the useful parts from one product.
    """
    ca = product.get("customAttributes") or {}
    product_id = product.get("productId")
    product_name = product.get("productName")

    if product_id is None or product_name is None:
        return None

    return TcgCardAttrs(
        product_id=int(product_id),
        product_name=str(product_name),
        set_name=product.get("setName"),
        number=ca.get("number"),
        domain=ca.get("domain"),
        card_types=list(ca.get("cardType") or []),
        energy_cost=_to_int(ca.get("energyCost")),
        power_cost=_to_int(ca.get("powerCost")),
        might=_to_int(ca.get("might")),
    )


def build_powercost_index_from_query(query: str) -> Dict[str, int]:
    """
    Returns a mapping you can use to enrich dotgg cards:
      key: a normalized "name|set|number" string (or just name), value: power_cost
    """
    raw = search_riftbound(query=query)
    idx: Dict[str, int] = {}

    for prod in iter_tcg_products(raw):
        attrs = extract_card_attrs(prod)
        if not attrs or attrs.power_cost is None:
            continue

        key = normalize_key(attrs.product_name, attrs.set_name, attrs.number)
        idx[key] = attrs.power_cost

    return idx


def normalize_key(name: str, set_name: Optional[str], number: Optional[str]) -> str:
    # You can improve this later: strip punctuation, normalize whitespace, etc.
    n = name.strip().lower()
    s = (set_name or "").strip().lower()
    num = (number or "").strip().lower()
    return f"{n}|{s}|{num}"
