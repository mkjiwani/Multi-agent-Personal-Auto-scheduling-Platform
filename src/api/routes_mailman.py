"""Mailman API routes."""

from fastapi import APIRouter

from src.agents.mailman import mailman_agent
from src.database import async_session, EmailRecord

router = APIRouter(prefix="/api/mailman", tags=["mailman"])


@router.get("/emails")
async def get_emails():
    """Get processed emails with classifications."""
    # If in-memory has data (scan_now was used), return it
    if mailman_agent.processed_emails:
        return mailman_agent.get_emails()

    # Otherwise read from DB (agent runs as subprocess, its memory is separate)
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(EmailRecord).order_by(EmailRecord.processed_at.desc()).limit(50)
        )
        rows = result.scalars().all()

    emails = []
    categories = {}
    for row in rows:
        email = {
            "id": row.message_id,
            "sender": row.sender or "",
            "subject": row.subject or "",
            "snippet": row.snippet or "",
            "received_at": row.received_at.isoformat() if row.received_at else "",
            "classification": row.classification or "Other",
            "summary": row.ai_summary or "",
            "is_key_person": row.is_key_person or False,
            "processed_at": row.processed_at.isoformat() if row.processed_at else "",
        }
        emails.append(email)
        cat = email["classification"]
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "emails": emails,
        "categories": categories,
        "total_processed": len(emails),
        "last_scan": emails[0]["processed_at"] if emails else None,
    }


@router.post("/scan")
async def scan_inbox():
    """Manually trigger inbox scan — returns immediately, classifies in background."""
    data = await mailman_agent.scan_now()
    return data


@router.post("/send-summary")
async def send_summary():
    """Manually trigger daily summary email."""
    await mailman_agent.send_daily_summary()
    return {"message": "Summary sent"}
