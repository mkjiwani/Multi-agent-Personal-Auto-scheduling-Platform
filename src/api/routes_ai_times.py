"""AI-Times API routes."""

from fastapi import APIRouter

from src.agents.ai_times import ai_times_agent
from src.database import async_session, CachedVideo

router = APIRouter(prefix="/api/ai-times", tags=["ai-times"])


@router.get("/videos")
async def get_videos():
    """Get cached AI videos."""
    data = ai_times_agent.get_videos()
    # If in-memory has videos, return them
    if data.get("news") or data.get("personality"):
        return data

    # Otherwise read from DB (agent subprocess writes there)
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(CachedVideo).order_by(CachedVideo.fetched_at.desc()).limit(20)
        )
        rows = result.scalars().all()

    news = []
    personality = []
    for row in rows:
        video = {
            "video_id": row.video_id,
            "title": row.title,
            "channel": row.channel or "",
            "thumbnail": row.thumbnail_url or "",
            "published_at": row.published_at.isoformat() if row.published_at else "",
            "url": f"https://www.youtube.com/watch?v={row.video_id}",
            "view_count": 0,
            "like_count": 0,
            "description": "",
            "summary": "",
        }
        if row.category == "news":
            news.append(video)
        else:
            personality.append(video)

    return {
        "news": news,
        "personality": personality,
        "last_updated": rows[0].fetched_at.isoformat() if rows else None,
    }


@router.post("/refresh")
async def refresh_videos():
    """Manually refresh videos from YouTube."""
    data = await ai_times_agent.fetch_videos()
    return data


@router.post("/send-digest")
async def send_digest():
    """Manually trigger email digest."""
    await ai_times_agent.send_digest()
    return {"message": "Digest sent"}
