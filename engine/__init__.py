"""Merit-order market matching algorithm with uniform clearing price.

Implements the same algorithm used in real wholesale electricity markets:
1. Sort sell offers by price ascending (cheapest first).
2. Sort buy demands by max willingness-to-pay descending (highest first).
3. Match cheapest supply to highest-value demand until exhausted.
4. Clearing price = price of the marginal (most expensive matched) offer.
5. ALL matched trades settle at the uniform clearing price, not at
   individual ask prices. This is standard uniform-price auction design
   (as used in PJM, NordPool, EPEX SPOT).
"""

from __future__ import annotations

from agents import EnergyDemand, EnergyOffer, TradeMatch


def match_orders(
    offers: list[EnergyOffer],
    demands: list[EnergyDemand],
    tick: int,
) -> tuple[list[TradeMatch], float]:
    """Run merit-order matching. Returns (matches, clearing_price).

    Args:
        offers: All sell offers this tick, will be sorted by price asc.
        demands: All buy demands this tick, will be sorted by max_price desc.
        tick: Current simulation tick number.

    Returns:
        Tuple of (list of matched trades, clearing price in USD/kWh).
        Clearing price is 0.0 if no matches occurred.
    """
    if not offers or not demands:
        return [], 0.0

    # Merit order: cheapest supply first
    sorted_offers = sorted(offers, key=lambda o: o.price_usd_per_kwh)
    # Highest willingness-to-pay first
    sorted_demands = sorted(demands, key=lambda d: d.max_price_usd_per_kwh, reverse=True)

    matches: list[TradeMatch] = []
    clearing_price = 0.0

    # Track remaining capacity for each offer/demand
    offer_remaining = {i: o.amount_kwh for i, o in enumerate(sorted_offers)}
    demand_remaining = {i: d.amount_kwh for i, d in enumerate(sorted_demands)}

    # Phase 1: Find all feasible matches and determine the marginal offer price
    provisional: list[tuple[int, int, float]] = []  # (o_idx, d_idx, trade_kwh)

    for d_idx, demand in enumerate(sorted_demands):
        if demand_remaining[d_idx] <= 0.0001:
            continue

        for o_idx, offer in enumerate(sorted_offers):
            if offer_remaining[o_idx] <= 0.0001:
                continue

            # Match only if buyer is willing to pay the asking price
            if demand.max_price_usd_per_kwh < offer.price_usd_per_kwh:
                break  # No more affordable offers (sorted ascending)

            # Trade the minimum of remaining supply and demand
            trade_kwh = min(offer_remaining[o_idx], demand_remaining[d_idx])

            provisional.append((o_idx, d_idx, trade_kwh))
            # Track the marginal (most expensive) matched offer price
            clearing_price = max(clearing_price, offer.price_usd_per_kwh)

            offer_remaining[o_idx] -= trade_kwh
            demand_remaining[d_idx] -= trade_kwh

            if demand_remaining[d_idx] <= 0.0001:
                break

    # Phase 2: Build TradeMatch objects using uniform clearing price
    for o_idx, d_idx, trade_kwh in provisional:
        total_usd = round(trade_kwh * clearing_price, 8)
        matches.append(
            TradeMatch(
                seller_id=sorted_offers[o_idx].agent_id,
                buyer_id=sorted_demands[d_idx].agent_id,
                amount_kwh=round(trade_kwh, 6),
                price_usd_per_kwh=clearing_price,
                total_usd=total_usd,
                tick=tick,
            )
        )

    return matches, clearing_price
