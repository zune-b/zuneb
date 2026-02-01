"""Demo mode - test the prediction engine with simulated data."""

import asyncio
import random
from datetime import datetime, timedelta
from src.signals.base import MarketContext, SignalDirection
from src.signals.ensemble import EnsemblePredictor

# Simulated crypto markets
DEMO_MARKETS = [
    {
        "id": "btc-100k-march",
        "question": "Will Bitcoin be above $100,000 on March 1, 2026?",
        "description": "This market resolves YES if BTC/USD is above $100,000.",
        "current_price": 0.45,
    },
    {
        "id": "eth-5k-q1",
        "question": "Will Ethereum reach $5,000 in Q1 2026?",
        "description": "Resolves YES if ETH hits $5,000 before April 1.",
        "current_price": 0.32,
    },
    {
        "id": "sol-ath-feb",
        "question": "Will Solana hit a new all-time high in February?",
        "description": "SOL must exceed previous ATH of $260.",
        "current_price": 0.28,
    },
    {
        "id": "doge-1-dollar",
        "question": "Will Dogecoin reach $1 in 2026?",
        "description": "DOGE must trade at or above $1.00.",
        "current_price": 0.15,
    },
]


def generate_price_history(current_price: float, points: int = 50) -> list[float]:
    """Generate realistic-looking price history."""
    prices = []
    price = current_price - 0.1 + random.random() * 0.05

    for _ in range(points):
        # Random walk with mean reversion
        change = random.gauss(0, 0.02)
        mean_reversion = (current_price - price) * 0.1
        price += change + mean_reversion
        price = max(0.05, min(0.95, price))
        prices.append(price)

    return prices


async def run_demo():
    """Run a demo prediction cycle."""
    print("=" * 60)
    print("POLYMARKET PREDICTION MACHINE - DEMO MODE")
    print("=" * 60)
    print()

    # Initialize predictor
    predictor = EnsemblePredictor()
    await predictor.initialize()

    print(f"Analyzing {len(DEMO_MARKETS)} simulated crypto markets...\n")

    for market in DEMO_MARKETS:
        print("-" * 60)
        print(f"Market: {market['question']}")
        print(f"Current Price: {market['current_price']:.0%} (YES)")
        print()

        # Build context with simulated data
        price_history = generate_price_history(market['current_price'])

        context = MarketContext(
            market_id=market['id'],
            question=market['question'],
            description=market['description'],
            current_price=market['current_price'],
            volume_24h=random.uniform(10000, 500000),
            liquidity=random.uniform(5000, 100000),
            end_date=datetime.utcnow() + timedelta(days=random.randint(7, 90)),
            price_history=price_history,
            category="crypto",
        )

        # Generate prediction
        prediction = await predictor.predict(context)

        if prediction:
            print("PREDICTION RESULT:")
            print(f"  Direction:    {prediction.direction.value.upper()}")
            print(f"  Confidence:   {prediction.combined_confidence:.1%}")
            print(f"  Predicted:    {prediction.predicted_probability:.1%}")
            print(f"  Current:      {prediction.current_price:.1%}")
            print(f"  Edge:         {prediction.expected_edge:+.1%}")
            print(f"  Action:       {prediction.recommended_action.value.upper()}")
            print()

            # Show individual signals
            print("  Signal Breakdown:")
            for signal in prediction.signals:
                print(f"    - {signal.source}: {signal.direction.value} "
                      f"(strength={signal.strength:.2f}, conf={signal.confidence:.2f})")

            if prediction.recommended_action.value != "hold":
                print()
                print(f"  >> WOULD TRADE: {prediction.recommended_action.value.upper()}")
                print(f"     Size: $25-50 (based on Kelly criterion)")
        else:
            print("  No prediction generated (insufficient data)")

        print()

    await predictor.shutdown()

    print("=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print()
    print("This was a simulation with fake data.")
    print("To trade real markets, add your Polymarket API keys to .env")


if __name__ == "__main__":
    asyncio.run(run_demo())
