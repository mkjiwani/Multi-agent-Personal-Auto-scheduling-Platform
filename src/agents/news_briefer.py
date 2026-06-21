"""Agent-4: News Briefer — Multi-category news summarization via NewsAPI + LLM."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.database import async_session, NewsArticle
from src.llm.ollama_client import ollama_client
from src.email_service.sender import send_email

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Summarize the following news article in 2-3 concise sentences. Focus on key facts and impact.

Title: {title}
Source: {source}
Description: {description}

Summary:"""

DAILY_BRIEF_PROMPT = """You are a news anchor. Based on the following headlines from today, write a cohesive 4-5 sentence "Daily Brief" that captures the most important stories and their significance.

Headlines:
{headlines}

Daily Brief:"""


class NewsBrieferAgent(BaseAgent):
    """Fetches news from NewsAPI, summarizes with LLM, sends daily digest."""

    def __init__(self):
        super().__init__("news_briefer")
        self.articles: list[dict] = []
        self.daily_brief: str = ""
        self._last_fetch: datetime | None = None

    async def run(self):
        """Main loop — fetch news periodically."""
        await self._load_from_db()
        await self.run_loop(interval_seconds=3600 * 6, initial_delay=120)  # Delay to not block LLM on startup

    async def execute(self):
        """Fetch news articles and generate summaries."""
        self.logger.info("Fetching news articles...")
        raw_articles = await self._fetch_news()
        # Store articles immediately so dashboard shows them
        self.articles = raw_articles
        self._last_fetch = datetime.utcnow()
        # Persist raw articles to DB immediately (without summaries)
        await self._persist_to_db()
        self.logger.info(f"Fetched {len(self.articles)} articles, now summarizing...")
        # Summarize in place (updates self.articles as each finishes)
        self.articles = await self._summarize_articles(self.articles)
        self.daily_brief = await self._generate_daily_brief()
        self.logger.info(f"News updated: {len(self.articles)} articles with summaries")
        # Persist again with summaries
        await self._persist_to_db()

    async def _load_from_db(self):
        """Load cached articles from SQLite on startup."""
        from sqlalchemy import select
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(NewsArticle).order_by(NewsArticle.fetched_at.desc()).limit(30)
                )
                rows = result.scalars().all()
                for row in rows:
                    self.articles.append({
                        "title": row.title,
                        "source": row.source or "Unknown",
                        "description": row.description or "",
                        "url": row.url or "",
                        "image_url": row.image_url or "",
                        "published_at": row.published_at.isoformat() if row.published_at else "",
                        "category": row.category or "",
                        "ai_summary": row.ai_summary or "",
                    })
                if rows:
                    self._last_fetch = rows[0].fetched_at
                    self.logger.info(f"Loaded {len(rows)} cached articles from DB")
        except Exception as e:
            self.logger.warning(f"Could not load cached articles from DB: {e}")

    async def _persist_to_db(self):
        """Save articles to SQLite."""
        try:
            async with async_session() as session:
                for a in self.articles:
                    pub_at = None
                    if a.get("published_at"):
                        try:
                            pub_at = datetime.fromisoformat(a["published_at"].replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            pass
                    record = NewsArticle(
                        title=a["title"],
                        source=a.get("source", "Unknown"),
                        description=a.get("description", ""),
                        url=a.get("url", ""),
                        image_url=a.get("image_url", ""),
                        category=a.get("category", ""),
                        ai_summary=a.get("ai_summary", ""),
                        published_at=pub_at,
                        fetched_at=datetime.utcnow(),
                    )
                    session.add(record)
                await session.commit()
            self.logger.info("Articles persisted to DB")
        except Exception as e:
            self.logger.warning(f"Could not persist articles to DB: {e}")

    async def refresh(self) -> dict:
        """Manual refresh from API — fetch articles and return immediately, summarize in background."""
        self.logger.info("Manual refresh: fetching news articles...")
        raw_articles = await self._fetch_news()
        self.articles = raw_articles
        self._last_fetch = datetime.utcnow()

        # Start summarization in background so the API responds quickly
        import asyncio
        asyncio.create_task(self._background_summarize())

        return self.get_news()

    async def _background_summarize(self):
        """Summarize articles and generate daily brief in background."""
        try:
            self.articles = await self._summarize_articles(self.articles)
            self.daily_brief = await self._generate_daily_brief()
            self.logger.info("Background summarization complete")
        except Exception as e:
            self.logger.error(f"Background summarization error: {e}")

    def get_news(self) -> dict:
        """Get current news data for dashboard."""
        # Group by category
        by_category = {}
        for article in self.articles:
            cat = article.get("category", "general")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(article)

        return {
            "articles": self.articles,
            "by_category": by_category,
            "daily_brief": self.daily_brief,
            "categories": settings.news_categories_list,
            "last_updated": self._last_fetch.isoformat() if self._last_fetch else None,
        }

    async def send_digest(self):
        """Send daily news digest email."""
        if not self.articles:
            await self.execute()

        html = self._build_digest_html()
        await send_email(
            subject=f"📰 News Briefer Daily Digest — {datetime.utcnow().strftime('%B %d, %Y')}",
            html_body=html,
        )

    async def _fetch_news(self) -> list[dict]:
        """Fetch news from NewsAPI for all configured categories."""
        if not settings.newsapi_key:
            self.logger.warning("NewsAPI key not configured")
            return []

        all_articles = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for category in settings.news_categories_list:
                try:
                    response = await client.get(
                        "https://newsapi.org/v2/top-headlines",
                        params={
                            "category": category,
                            "country": settings.news_country,
                            "pageSize": settings.news_articles_count,
                            "apiKey": settings.newsapi_key,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    for article in data.get("articles", []):
                        all_articles.append({
                            "title": article.get("title", ""),
                            "source": article.get("source", {}).get("name", "Unknown"),
                            "description": article.get("description", ""),
                            "url": article.get("url", ""),
                            "image_url": article.get("urlToImage", ""),
                            "published_at": article.get("publishedAt", ""),
                            "category": category,
                        })
                except Exception as e:
                    self.logger.error(f"NewsAPI error for '{category}': {e}")

        return all_articles

    async def _summarize_articles(self, articles: list[dict]) -> list[dict]:
        """Add AI summaries to articles (limit to first 10 to avoid LLM overload)."""
        for i, article in enumerate(articles):
            if not article.get("title"):
                continue
            # Only summarize first 10 articles to keep response time reasonable
            if i >= 10:
                if not article.get("ai_summary"):
                    article["ai_summary"] = article.get("description", "")[:150]
                continue
            try:
                prompt = SUMMARY_PROMPT.format(
                    title=article["title"],
                    source=article["source"],
                    description=article.get("description", "")[:300],
                )
                summary = await ollama_client.generate(
                    prompt=prompt,
                    agent_name="news_briefer",
                    temperature=0.3,
                )
                article["ai_summary"] = summary.strip()
            except Exception as e:
                self.logger.debug(f"Summary failed for article: {e}")
                article["ai_summary"] = article.get("description", "")[:150]

        return articles

    async def _generate_daily_brief(self) -> str:
        """Generate cohesive daily brief narrative."""
        if not self.articles:
            return "No news articles available."

        headlines = "\n".join(
            f"- [{a['category']}] {a['title']}" for a in self.articles[:15]
        )

        try:
            brief = await ollama_client.generate(
                prompt=DAILY_BRIEF_PROMPT.format(headlines=headlines),
                agent_name="news_briefer",
                temperature=0.6,
            )
            return brief.strip()
        except Exception as e:
            self.logger.error(f"Daily brief generation error: {e}")
            return "Daily brief unavailable — LLM busy."

    def _build_digest_html(self) -> str:
        """Build daily news digest HTML email."""
        html = """
        <html><body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto;">
        <h1 style="color: #e65100;">📰 News Briefer Daily Digest</h1>
        <div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin: 15px 0;">
            <h3 style="margin: 0 0 8px;">Daily Brief</h3>
            <p style="margin: 0;">{brief}</p>
        </div>
        <hr>
        """.format(brief=self.daily_brief)

        for category in settings.news_categories_list:
            cat_articles = [a for a in self.articles if a.get("category") == category]
            if not cat_articles:
                continue

            html += f"<h2>{category.title()}</h2>"
            for article in cat_articles[:5]:
                html += f"""
                <div style="margin: 12px 0; padding: 10px; border-left: 3px solid #e65100;">
                    <a href="{article['url']}" style="text-decoration: none; color: #1a73e8;">
                        <strong>{article['title']}</strong>
                    </a>
                    <p style="color: #666; margin: 4px 0; font-size: 12px;">{article['source']} • {article.get('published_at', '')[:10]}</p>
                    <p style="margin: 4px 0;">{article.get('ai_summary', '')}</p>
                </div>
                """

        html += "</body></html>"
        return html


# Singleton
news_briefer_agent = NewsBrieferAgent()


if __name__ == "__main__":
    import asyncio
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(news_briefer_agent.start())
