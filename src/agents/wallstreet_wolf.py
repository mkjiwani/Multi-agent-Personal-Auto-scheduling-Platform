"""Agent-3: Wallstreet Wolf — Stock tracking with LLM market commentary."""

from __future__ import annotations

import logging
from datetime import datetime

import yfinance as yf

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.database import async_session, StockSnapshot
from src.llm.ollama_client import ollama_client
from src.email_service.sender import send_email

logger = logging.getLogger(__name__)

CURRENCY_PAIRS = ["EURUSD=X", "GBPUSD=X", "JPYUSD=X", "CADUSD=X"]
METALS = ["GC=F", "SI=F"]  # Gold, Silver

COMMENTARY_PROMPT = """You are a witty Wall Street analyst. Based on the following market data, provide a brief market commentary (3-4 sentences). Be insightful and slightly humorous.

Top 5 Gainers:
{gainers}

Top 5 Losers:
{losers}

Overall market sentiment and your take:"""


class WallstreetWolfAgent(BaseAgent):
    """Tracks stocks via Yahoo Finance, provides LLM market commentary."""

    def __init__(self):
        super().__init__("wallstreet_wolf")
        self.stocks: list[dict] = []
        self.gainers: list[dict] = []
        self.losers: list[dict] = []
        self.currencies: list[dict] = []
        self.metals: list[dict] = []
        self.commentary: str = ""
        self._last_fetch: datetime | None = None
        self._market_open: bool = False

    @staticmethod
    def _is_market_open() -> bool:
        """Check if US stock market is currently open (Mon-Fri 9:30-16:00 ET)."""
        from zoneinfo import ZoneInfo
        now_et = datetime.now(ZoneInfo("America/New_York"))
        # Weekday 0=Mon...4=Fri
        if now_et.weekday() > 4:
            return False
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_open <= now_et <= market_close

    async def run(self):
        """Main loop — fetch data periodically."""
        await self._load_from_db()
        await self.run_loop(interval_seconds=3600, initial_delay=60)  # Delay to not block LLM on startup

    async def execute(self):
        """Fetch stock data and generate commentary."""
        self.logger.info("Fetching stock market data...")
        self._market_open = self._is_market_open()
        await self._fetch_stocks()
        await self._fetch_currencies_metals()
        await self._generate_commentary()
        self._last_fetch = datetime.utcnow()
        self.logger.info(f"Market data updated: {len(self.stocks)} stocks tracked")
        await self._persist_to_db()

    async def _load_from_db(self):
        """Load cached stock data from SQLite on startup."""
        from sqlalchemy import select
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(StockSnapshot).order_by(StockSnapshot.fetched_at.desc()).limit(50)
                )
                rows = result.scalars().all()
                seen_tickers = set()
                for row in rows:
                    if row.ticker in seen_tickers:
                        continue
                    seen_tickers.add(row.ticker)
                    self.stocks.append({
                        "ticker": row.ticker,
                        "price": row.price,
                        "change_percent": row.change_percent,
                        "volume": row.volume or 0,
                        "market_cap": row.market_cap or 0,
                    })
                if self.stocks:
                    sorted_stocks = sorted(self.stocks, key=lambda x: x.get("change_percent", 0), reverse=True)
                    self.gainers = sorted_stocks[:5]
                    self.losers = sorted_stocks[-5:][::-1]
                    self.logger.info(f"Loaded {len(self.stocks)} cached stocks from DB")
        except Exception as e:
            self.logger.warning(f"Could not load cached stocks from DB: {e}")

    async def _persist_to_db(self):
        """Save stock data to SQLite."""
        try:
            async with async_session() as session:
                for s in self.stocks:
                    record = StockSnapshot(
                        ticker=s["ticker"],
                        price=s.get("price"),
                        change_percent=s.get("change_percent"),
                        volume=s.get("volume"),
                        market_cap=s.get("market_cap", 0),
                        name=s.get("name", s["ticker"]),
                        fetched_at=datetime.utcnow(),
                    )
                    session.add(record)
                await session.commit()
            self.logger.info("Stock data persisted to DB")
        except Exception as e:
            self.logger.warning(f"Could not persist stocks to DB: {e}")

    async def refresh(self) -> dict:
        """Manual refresh from API."""
        await self.execute()
        return self.get_market_data()

    def get_market_data(self) -> dict:
        """Get current market data for dashboard."""
        return {
            "stocks": self.stocks,
            "gainers": self.gainers,
            "losers": self.losers,
            "currencies": self.currencies,
            "metals": self.metals,
            "commentary": self.commentary,
            "market_open": self._market_open,
            "last_updated": self._last_fetch.isoformat() if self._last_fetch else None,
        }

    async def send_daily_brief(self):
        """Send daily market brief email."""
        if not self.stocks:
            await self.execute()

        html = self._build_brief_html()
        await send_email(
            subject=f"🐺 Wallstreet Wolf Daily Brief — {datetime.utcnow().strftime('%B %d, %Y')}",
            html_body=html,
        )

    async def _fetch_stocks(self):
        """Fetch stock data for the watchlist."""
        import asyncio

        tickers = settings.watchlist_tickers
        self.stocks = []

        try:
            data = await asyncio.to_thread(self._download_stock_data, tickers)
            self.stocks = data

            # Sort for gainers/losers
            sorted_stocks = sorted(data, key=lambda x: x.get("change_percent", 0), reverse=True)
            self.gainers = sorted_stocks[:5]
            self.losers = sorted_stocks[-5:][::-1]  # Worst first

        except Exception as e:
            self.logger.error(f"Stock fetch error: {e}")

    def _download_stock_data(self, tickers: list[str]) -> list[dict]:
        """Download stock data using batch download (runs in thread)."""
        import time
        stocks = []

        try:
            # Use 5d period to ensure data is available on weekends/holidays
            df = yf.download(tickers, period="5d", progress=False, threads=False)

            if df.empty:
                logger.warning("yfinance batch download returned empty dataframe")
                return stocks

            for ticker in tickers:
                try:
                    # yfinance 1.x uses MultiIndex columns: (Price, Ticker)
                    if ("Close", ticker) not in df.columns:
                        continue

                    close_series = df[("Close", ticker)].dropna()
                    if len(close_series) < 1:
                        continue

                    current = float(close_series.iloc[-1])
                    change_pct = 0.0
                    if len(close_series) >= 2:
                        prev_close = float(close_series.iloc[-2])
                        if prev_close > 0:
                            change_pct = ((current - prev_close) / prev_close) * 100

                    volume = 0
                    if ("Volume", ticker) in df.columns:
                        vol_series = df[("Volume", ticker)].dropna()
                        if len(vol_series) > 0:
                            volume = int(vol_series.iloc[-1])

                    stocks.append({
                        "ticker": ticker,
                        "price": round(current, 2),
                        "change_percent": round(change_pct, 2),
                        "volume": volume,
                        "market_cap": 0,
                    })
                except Exception as e:
                    logger.debug(f"Error processing {ticker}: {e}")

        except Exception as e:
            logger.error(f"Batch download failed: {e}")
            # Fallback: try individual downloads with delay
            for ticker in tickers:
                try:
                    time.sleep(0.5)
                    hist = yf.download(ticker, period="5d", progress=False)
                    if hist.empty:
                        continue
                    close_series = hist[("Close", ticker)].dropna() if ("Close", ticker) in hist.columns else hist["Close"].dropna()
                    if len(close_series) < 1:
                        continue
                    current = float(close_series.iloc[-1])
                    change_pct = 0.0
                    if len(close_series) >= 2:
                        prev_close = float(close_series.iloc[-2])
                        if prev_close > 0:
                            change_pct = ((current - prev_close) / prev_close) * 100
                    stocks.append({
                        "ticker": ticker,
                        "price": round(current, 2),
                        "change_percent": round(change_pct, 2),
                        "volume": 0,
                        "market_cap": 0,
                    })
                except Exception:
                    pass

        return stocks

    async def _fetch_currencies_metals(self):
        """Fetch currency pairs and precious metals in batch."""
        import asyncio

        self.currencies = []
        self.metals = []

        try:
            all_symbols = CURRENCY_PAIRS + METALS
            results = await asyncio.to_thread(self._download_quotes_batch, all_symbols)

            for symbol in CURRENCY_PAIRS:
                if symbol in results:
                    self.currencies.append(results[symbol])
            for symbol in METALS:
                if symbol in results:
                    self.metals.append(results[symbol])
        except Exception as e:
            self.logger.error(f"Currency/metals fetch error: {e}")

    def _download_quotes_batch(self, symbols: list[str]) -> dict:
        """Batch download quotes for currencies and metals."""
        results = {}
        try:
            df = yf.download(symbols, period="5d", progress=False, threads=False)
            if df.empty:
                return results

            for symbol in symbols:
                try:
                    # yfinance 1.x MultiIndex: (Price, Ticker)
                    if ("Close", symbol) not in df.columns:
                        continue

                    close_series = df[("Close", symbol)].dropna()
                    if len(close_series) < 1:
                        continue

                    current = float(close_series.iloc[-1])
                    change_pct = 0.0
                    if len(close_series) >= 2:
                        prev = float(close_series.iloc[-2])
                        if prev > 0:
                            change_pct = ((current - prev) / prev) * 100

                    results[symbol] = {
                        "symbol": symbol.replace("=X", "").replace("=F", ""),
                        "price": round(current, 4),
                        "change_percent": round(change_pct, 2),
                    }
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Batch quote download failed: {e}")

        return results

    async def _generate_commentary(self):
        """Generate LLM market commentary."""
        if not self.gainers or not self.losers:
            self.commentary = "Market data not yet available."
            return

        gainers_text = "\n".join(
            f"  {s['ticker']}: +{s['change_percent']:.2f}%" for s in self.gainers
        )
        losers_text = "\n".join(
            f"  {s['ticker']}: {s['change_percent']:.2f}%" for s in self.losers
        )

        try:
            self.commentary = await ollama_client.generate(
                prompt=COMMENTARY_PROMPT.format(gainers=gainers_text, losers=losers_text),
                agent_name="wallstreet_wolf",
                temperature=0.8,
            )
        except Exception as e:
            self.logger.error(f"Commentary generation error: {e}")
            self.commentary = "Commentary unavailable — LLM busy."

    def _build_brief_html(self) -> str:
        """Build daily market brief HTML email."""
        html = """
        <html><body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto;">
        <h1 style="color: #1b5e20;">🐺 Wallstreet Wolf Daily Brief</h1>
        <hr>
        <h2 style="color: #2e7d32;">📈 Top 5 Gainers</h2>
        <table style="width: 100%; border-collapse: collapse;">
        <tr><th style="text-align: left;">Ticker</th><th>Price</th><th>Change</th></tr>
        """
        for s in self.gainers:
            html += f'<tr><td><strong>{s["ticker"]}</strong></td><td>${s["price"]:.2f}</td><td style="color: green;">+{s["change_percent"]:.2f}%</td></tr>'

        html += """</table>
        <h2 style="color: #c62828;">📉 Top 5 Losers</h2>
        <table style="width: 100%; border-collapse: collapse;">
        <tr><th style="text-align: left;">Ticker</th><th>Price</th><th>Change</th></tr>
        """
        for s in self.losers:
            html += f'<tr><td><strong>{s["ticker"]}</strong></td><td>${s["price"]:.2f}</td><td style="color: red;">{s["change_percent"]:.2f}%</td></tr>'

        html += f"""</table>
        <h2>💬 Market Commentary</h2>
        <p style="background: #f5f5f5; padding: 15px; border-radius: 8px; font-style: italic;">{self.commentary}</p>
        </body></html>
        """
        return html


# Singleton
wallstreet_wolf_agent = WallstreetWolfAgent()


if __name__ == "__main__":
    import asyncio
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(wallstreet_wolf_agent.start())
