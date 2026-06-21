"""Agent-1: AI-Times — Fetches AI YouTube videos and sends daily HTML email digest."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.database import async_session, CachedVideo
from src.llm.ollama_client import ollama_client
from src.email_service.sender import send_email

logger = logging.getLogger(__name__)

# Search queries for YouTube
AI_NEWS_QUERIES = ["artificial intelligence news this week", "AI breakthroughs 2024", "latest machine learning developments"]
AI_PERSONALITY_QUERIES = ["AI thought leaders interview", "artificial intelligence expert talk", "AI industry podcast"]

VIDEO_SUMMARY_PROMPT = """Summarize the following YouTube video in 2 concise sentences based on its title and description. Focus on the key takeaway.

Title: {title}
Channel: {channel}
Description: {description}

Summary:"""


class AITimesAgent(BaseAgent):
    """Fetches latest AI YouTube videos and sends daily HTML email digest."""

    def __init__(self):
        super().__init__("ai_times")
        self.videos_news: list[dict] = []
        self.videos_personality: list[dict] = []

    async def run(self):
        """Main loop — execute on schedule."""
        await self._load_from_db()
        await self.run_loop(interval_seconds=3600 * 12, initial_delay=180)  # Delay to not block LLM on startup

    async def execute(self):
        """Fetch videos and send digest."""
        self.logger.info("Fetching AI YouTube videos...")
        self.videos_news = await self._fetch_videos(AI_NEWS_QUERIES, max_results=5)
        self.videos_personality = await self._fetch_videos(AI_PERSONALITY_QUERIES, max_results=5)
        self.logger.info(
            f"Fetched {len(self.videos_news)} news + {len(self.videos_personality)} personality videos"
        )
        await self._persist_to_db()

    async def _load_from_db(self):
        """Load cached videos from SQLite on startup."""
        from sqlalchemy import select
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(CachedVideo).order_by(CachedVideo.fetched_at.desc()).limit(20)
                )
                rows = result.scalars().all()
                for row in rows:
                    video = {
                        "video_id": row.video_id,
                        "title": row.title,
                        "channel": row.channel,
                        "thumbnail": row.thumbnail_url,
                        "published_at": row.published_at.isoformat() if row.published_at else "",
                        "url": f"https://www.youtube.com/watch?v={row.video_id}",
                        "view_count": 0,
                        "like_count": 0,
                        "description": "",
                        "summary": "",
                    }
                    if row.category == "news":
                        self.videos_news.append(video)
                    else:
                        self.videos_personality.append(video)
                if rows:
                    self.logger.info(f"Loaded {len(rows)} cached videos from DB")
        except Exception as e:
            self.logger.warning(f"Could not load cached videos from DB: {e}")

    async def _persist_to_db(self):
        """Save fetched videos to SQLite for persistence."""
        from sqlalchemy.dialects.sqlite import insert
        try:
            async with async_session() as session:
                for category, videos in [("news", self.videos_news), ("personality", self.videos_personality)]:
                    for v in videos:
                        stmt = insert(CachedVideo).values(
                            video_id=v["video_id"],
                            title=v["title"],
                            channel=v.get("channel", ""),
                            thumbnail_url=v.get("thumbnail", ""),
                            published_at=datetime.fromisoformat(v["published_at"].replace("Z", "+00:00")) if v.get("published_at") else None,
                            category=category,
                            fetched_at=datetime.utcnow(),
                        ).on_conflict_do_update(
                            index_elements=["video_id"],
                            set_={"title": v["title"], "fetched_at": datetime.utcnow()}
                        )
                        await session.execute(stmt)
                await session.commit()
            self.logger.info("Videos persisted to DB")
        except Exception as e:
            self.logger.warning(f"Could not persist videos to DB: {e}")

    async def fetch_videos(self) -> dict:
        """Public method for manual refresh from API."""
        await self.execute()
        return self.get_videos()

    def get_videos(self) -> dict:
        """Get currently cached videos."""
        return {
            "news": self.videos_news,
            "personality": self.videos_personality,
            "last_updated": self._last_run.isoformat() if self._last_run else None,
        }

    async def send_digest(self):
        """Send HTML email digest with current videos."""
        if not self.videos_news and not self.videos_personality:
            await self.execute()

        html = self._build_digest_html()
        await send_email(
            subject=f"🤖 AI-Times Daily Digest — {datetime.utcnow().strftime('%B %d, %Y')}",
            html_body=html,
        )

    async def _fetch_videos(self, queries: list[str], max_results: int = 5) -> list[dict]:
        """Fetch videos from YouTube Data API v3, sorted by relevance and view count."""
        if not settings.youtube_api_key:
            self.logger.warning("YouTube API key not configured")
            return []

        videos = []
        published_after = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"

        async with httpx.AsyncClient(timeout=30.0) as client:
            for query in queries:
                if len(videos) >= max_results * 2:  # Fetch extra to pick best
                    break
                try:
                    # Search with relevance ordering (YouTube's default considers views + recency)
                    response = await client.get(
                        "https://www.googleapis.com/youtube/v3/search",
                        params={
                            "part": "snippet",
                            "q": query,
                            "type": "video",
                            "order": "relevance",
                            "publishedAfter": published_after,
                            "maxResults": max_results,
                            "key": settings.youtube_api_key,
                            "videoDuration": "medium",  # Filter out shorts
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    # Collect video IDs for statistics lookup
                    video_ids = [item["id"]["videoId"] for item in data.get("items", [])]

                    if not video_ids:
                        continue

                    # Get view counts and descriptions from videos endpoint
                    stats_response = await client.get(
                        "https://www.googleapis.com/youtube/v3/videos",
                        params={
                            "part": "statistics,snippet",
                            "id": ",".join(video_ids),
                            "key": settings.youtube_api_key,
                        },
                    )
                    stats_response.raise_for_status()
                    stats_data = stats_response.json()

                    # Build a map of video stats
                    stats_map = {}
                    for v in stats_data.get("items", []):
                        stats_map[v["id"]] = {
                            "view_count": int(v["statistics"].get("viewCount", 0)),
                            "like_count": int(v["statistics"].get("likeCount", 0)),
                            "description": v["snippet"].get("description", "")[:300],
                        }

                    for item in data.get("items", []):
                        video_id = item["id"]["videoId"]
                        snippet = item["snippet"]
                        stats = stats_map.get(video_id, {})

                        videos.append({
                            "video_id": video_id,
                            "title": snippet["title"],
                            "channel": snippet["channelTitle"],
                            "thumbnail": snippet["thumbnails"]["medium"]["url"],
                            "published_at": snippet["publishedAt"],
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "view_count": stats.get("view_count", 0),
                            "like_count": stats.get("like_count", 0),
                            "description": stats.get("description", ""),
                            "summary": "",  # Will be filled by LLM
                        })
                except Exception as e:
                    self.logger.error(f"YouTube API error for '{query}': {e}")

        # Sort by view count and take top results
        videos.sort(key=lambda x: x["view_count"], reverse=True)
        top_videos = videos[:max_results]

        # Generate LLM summaries for each video
        for video in top_videos:
            try:
                summary = await ollama_client.generate(
                    prompt=VIDEO_SUMMARY_PROMPT.format(
                        title=video["title"],
                        channel=video["channel"],
                        description=video["description"][:200],
                    ),
                    agent_name="ai_times",
                    temperature=0.3,
                )
                video["summary"] = summary.strip()
            except Exception as e:
                self.logger.debug(f"Summary generation failed for '{video['title']}': {e}")
                video["summary"] = ""

        return top_videos

    def _build_digest_html(self) -> str:
        """Build HTML email body for the digest."""
        html = """
        <html><body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto;">
        <h1 style="color: #1a73e8;">🤖 AI-Times Daily Digest</h1>
        <p style="color: #666;">Your daily roundup of AI news and personalities</p>
        <hr>
        <h2>📰 AI News</h2>
        """
        for v in self.videos_news:
            html += self._video_card(v)

        html += "<h2>🎙️ AI Personalities & Interviews</h2>"
        for v in self.videos_personality:
            html += self._video_card(v)

        html += "</body></html>"
        return html

    def _video_card(self, video: dict) -> str:
        return f"""
        <div style="margin: 15px 0; padding: 10px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <a href="{video['url']}" style="text-decoration: none; color: #1a73e8;">
                <img src="{video['thumbnail']}" style="width: 100%; border-radius: 4px;" />
                <h3 style="margin: 8px 0 4px;">{video['title']}</h3>
            </a>
            <p style="color: #666; margin: 0;">{video['channel']} • {video['published_at'][:10]}</p>
        </div>
        """


# Singleton
ai_times_agent = AITimesAgent()


if __name__ == "__main__":
    import asyncio
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(ai_times_agent.start())
