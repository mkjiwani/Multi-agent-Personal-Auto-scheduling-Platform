"""Wallstreet Wolf API routes."""

from fastapi import APIRouter

from src.agents.wallstreet_wolf import wallstreet_wolf_agent
from src.database import async_session, StockSnapshot

router = APIRouter(prefix="/api/wallstreet", tags=["wallstreet"])


@router.get("/stocks")
async def get_stocks():
    """Get stock market data, gainers, losers, watchlist."""
    data = wallstreet_wolf_agent.get_market_data()
    # If in-memory has data, return it
    if data.get("stocks"):
        return data

    # Otherwise read from DB (agent subprocess writes there)
    from sqlalchemy import select, func
    async with async_session() as session:
        # Get the most recent snapshot per ticker
        subq = (
            select(StockSnapshot.ticker, func.max(StockSnapshot.fetched_at).label("latest"))
            .group_by(StockSnapshot.ticker)
            .subquery()
        )
        result = await session.execute(
            select(StockSnapshot).join(
                subq,
                (StockSnapshot.ticker == subq.c.ticker) &
                (StockSnapshot.fetched_at == subq.c.latest)
            )
        )
        rows = result.scalars().all()

    stocks = [
        {
            "ticker": r.ticker,
            "price": r.price,
            "change_percent": r.change_percent,
            "volume": r.volume or 0,
            "market_cap": r.market_cap or 0,
            "name": r.name or r.ticker,
        }
        for r in rows
    ]
    sorted_stocks = sorted(stocks, key=lambda x: x.get("change_percent", 0), reverse=True)

    return {
        "stocks": stocks,
        "gainers": sorted_stocks[:5],
        "losers": sorted_stocks[-5:][::-1],
        "currencies": [],
        "metals": [],
        "commentary": "",
        "market_open": False,
        "last_updated": rows[0].fetched_at.isoformat() if rows else None,
    }


@router.post("/refresh")
async def refresh_stocks():
    """Manually refresh stock data."""
    data = await wallstreet_wolf_agent.refresh()
    return data


@router.get("/commentary")
async def get_commentary():
    """Get LLM market commentary."""
    return {"commentary": wallstreet_wolf_agent.commentary}


@router.post("/send-brief")
async def send_brief():
    """Manually trigger daily market brief email."""
    await wallstreet_wolf_agent.send_daily_brief()
    return {"message": "Market brief sent"}
