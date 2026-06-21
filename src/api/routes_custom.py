"""News Briefer API routes."""

from fastapi import APIRouter

from src.agents.news_briefer import news_briefer_agent
from src.config import settings
from src.database import async_session, NewsArticle

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/articles")
async def get_articles():
    """Get news articles with AI summaries."""
    data = news_briefer_agent.get_news()
    # If in-memory has articles, return them
    if data.get("articles"):
        return data

    # Otherwise read from DB (agent subprocess writes there)
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(NewsArticle).order_by(NewsArticle.fetched_at.desc()).limit(30)
        )
        rows = result.scalars().all()

    articles = [
        {
            "title": r.title,
            "source": r.source or "Unknown",
            "description": r.description or "",
            "url": r.url or "",
            "image_url": r.image_url or "",
            "published_at": r.published_at.isoformat() if r.published_at else "",
            "category": r.category or "",
            "ai_summary": r.ai_summary or "",
        }
        for r in rows
    ]

    # Group by category
    by_category = {}
    for a in articles:
        cat = a.get("category", "general")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(a)

    return {
        "articles": articles,
        "by_category": by_category,
        "categories": settings.news_categories_list,
        "daily_brief": "",
        "last_updated": rows[0].fetched_at.isoformat() if rows else None,
    }


@router.post("/refresh")
async def refresh_news():
    """Manually refresh news articles."""
    data = await news_briefer_agent.refresh()
    return data


@router.get("/brief")
async def get_daily_brief():
    """Get the daily brief narrative."""
    return {"daily_brief": news_briefer_agent.daily_brief}


@router.post("/send-digest")
async def send_digest():
    """Manually trigger daily digest email."""
    await news_briefer_agent.send_digest()
    return {"message": "News digest sent"}
