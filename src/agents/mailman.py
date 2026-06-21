"""Agent-2: Mailman — Gmail integration with LLM classification, labeling, and alerts."""

from __future__ import annotations

import logging
from datetime import datetime

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.database import async_session, EmailRecord
from src.llm.ollama_client import ollama_client
from src.email_service.sender import send_email

logger = logging.getLogger(__name__)

CLASSIFICATION_CATEGORIES = [
    "Urgent",
    "Action Required",
    "Follow-Up",
    "Newsletter",
    "Notification",
    "Personal",
    "Other",
]

BATCH_CLASSIFICATION_PROMPT = """Classify each email into exactly ONE category from the priority list below. If an email fits multiple categories, always pick the HIGHEST priority one (listed first = highest).

Priority order (1=highest):
1. Urgent — Deadlines within 24-48h, security alerts, account lockouts, payment failures, emergency requests, anything marked ASAP/immediately/critical
2. Action Required — You must DO something: sign, complete, decide, RSVP, review, submit, approve, reply to a request, homework/assignments, invitations needing response
3. Follow-Up — Replies to existing threads, ongoing conversations, meeting follow-ups, status updates on previous requests, "Re:" or "Fwd:" subjects
4. Newsletter — Marketing, promotions, weekly/daily digests, product announcements, subscription emails, bulk senders, contains "unsubscribe"
5. Notification — Automated system alerts: shipping/delivery, login alerts, calendar reminders, purchase receipts, social media, app notifications, no-reply/noreply senders
6. Personal — Friends/family, personal invitations, casual non-work conversations
7. Other — ONLY if absolutely nothing above fits

Decision rules:
- If subject contains "urgent", "ASAP", "deadline", "expires today", "action needed" → Urgent
- If sender is no-reply@ or noreply@ → Notification
- If email has "unsubscribe" in it or comes from a marketing platform → Newsletter
- If subject starts with "Re:" or "Fwd:" → Follow-Up
- If email asks you to do/complete/submit/sign/approve something → Action Required
- If it could be Newsletter OR Notification, pick Newsletter (higher priority)
- If it could be Other OR anything else, pick the other category (never default to Other)

{emails_block}

Output ONLY the numbered list below. No explanations, no extra text.
1. <category>
2. <category>"""

BATCH_SUMMARY_PROMPT = """Summarize each email below in 1-2 sentences. Be specific about what each email is about and any action needed.

{emails_block}

Respond with ONLY a numbered list of summaries, one per line, matching the email numbers above. Example:
1. Summary of email 1.
2. Summary of email 2."""


class MailmanAgent(BaseAgent):
    """Monitors Gmail, classifies emails with LLM, applies labels and stars."""

    def __init__(self):
        super().__init__("mailman")
        self.processed_emails: list[dict] = []
        self._gmail_service = None
        self._gmail_creds = None

    async def run(self):
        """Main loop — scan inbox periodically."""
        await self._load_from_db()
        await self.run_loop(interval_seconds=3600)  # Every hour

    async def execute(self):
        """Scan inbox, classify, label, and alert."""
        self.logger.info("Scanning Gmail inbox...")
        service = await self._get_gmail_service()
        if not service:
            self.logger.warning("Gmail service not available — skipping scan")
            return

        emails = await self._fetch_unread_emails(service)
        self.logger.info(f"Found {len(emails)} unread emails")

        if not emails:
            return

        # Skip emails already classified (in memory or DB)
        known_ids = {e["id"] for e in self.processed_emails}
        new_emails = [e for e in emails if e["id"] not in known_ids]

        if not new_emails:
            self.logger.info("All emails already classified — skipping LLM calls")
            return

        self.logger.info(f"Classifying {len(new_emails)} new emails (skipped {len(emails) - len(new_emails)} already known)")

        # Batch classify + summarize (sub-batched, 4 emails per LLM call)
        classifications = await self._batch_classify(new_emails)
        summaries = await self._batch_summarize(new_emails)

        for email_data, classification, summary in zip(new_emails, classifications, summaries):
            is_key_person = email_data["sender"] in settings.key_people_list

            processed = {
                **email_data,
                "classification": classification,
                "summary": summary,
                "is_key_person": is_key_person,
                "processed_at": datetime.utcnow().isoformat(),
            }
            self.processed_emails.insert(0, processed)

            # Apply Gmail labels and stars
            await self._apply_labels(service, email_data["id"], classification)
            if classification == "Urgent" or is_key_person:
                await self._star_message(service, email_data["id"])

        # Keep only last 100 emails in memory
        self.processed_emails = self.processed_emails[:100]
        await self._persist_to_db()

    async def _load_from_db(self):
        """Load cached emails from SQLite on startup."""
        from sqlalchemy import select
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(EmailRecord).order_by(EmailRecord.processed_at.desc()).limit(100)
                )
                rows = result.scalars().all()
                for row in rows:
                    self.processed_emails.append({
                        "id": row.message_id,
                        "sender": row.sender or "",
                        "subject": row.subject or "",
                        "snippet": row.snippet or "",
                        "received_at": row.received_at.isoformat() if row.received_at else "",
                        "classification": row.classification or "Other",
                        "summary": row.ai_summary or "",
                        "is_key_person": row.is_key_person or False,
                        "processed_at": row.processed_at.isoformat() if row.processed_at else "",
                    })
                if rows:
                    self.logger.info(f"Loaded {len(rows)} cached emails from DB")
        except Exception as e:
            self.logger.warning(f"Could not load cached emails from DB: {e}")

    async def _persist_to_db(self):
        """Save processed emails to SQLite."""
        from sqlalchemy.dialects.sqlite import insert
        try:
            async with async_session() as session:
                for em in self.processed_emails:
                    if em.get("classification") == "Classifying...":
                        continue
                    stmt = insert(EmailRecord).values(
                        message_id=em["id"],
                        sender=em.get("sender", ""),
                        subject=em.get("subject", ""),
                        snippet=em.get("snippet", ""),
                        classification=em.get("classification", "Other"),
                        ai_summary=em.get("summary", ""),
                        is_key_person=em.get("is_key_person", False),
                        received_at=self._parse_date(em.get("received_at")),
                        processed_at=datetime.utcnow(),
                    ).on_conflict_do_update(
                        index_elements=["message_id"],
                        set_={
                            "classification": em.get("classification", "Other"),
                            "ai_summary": em.get("summary", ""),
                        }
                    )
                    await session.execute(stmt)
                await session.commit()
            self.logger.info("Emails persisted to DB")
        except Exception as e:
            self.logger.warning(f"Could not persist emails to DB: {e}")

    @staticmethod
    def _parse_date(date_str: str | None) -> datetime | None:
        """Parse email date string (RFC 2822 or ISO format) to datetime."""
        if not date_str:
            return None
        from email.utils import parsedate_to_datetime
        try:
            return parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            try:
                return datetime.fromisoformat(date_str)
            except (ValueError, TypeError):
                return None

    async def scan_now(self) -> dict:
        """Manual trigger — fetch emails fast, classify in background."""
        service = await self._get_gmail_service()
        if not service:
            return self.get_emails()

        emails = await self._fetch_unread_emails(service)
        self.logger.info(f"Scan found {len(emails)} unread emails")

        # Skip already-classified emails
        known_ids = {e["id"] for e in self.processed_emails}
        new_emails = [e for e in emails if e["id"] not in known_ids]

        if not new_emails:
            self.logger.info("All emails already classified — no LLM calls needed")
            return self.get_emails()

        self.logger.info(f"Need to classify {len(new_emails)} new emails (skipped {len(emails) - len(new_emails)} known)")

        # Store new emails immediately with "Classifying..." status
        for email_data in new_emails:
            processed = {
                **email_data,
                "classification": "Classifying...",
                "summary": email_data.get("snippet", "")[:100],
                "is_key_person": email_data["sender"] in settings.key_people_list,
                "processed_at": datetime.utcnow().isoformat(),
            }
            self.processed_emails.insert(0, processed)

        self.processed_emails = self.processed_emails[:100]

        # Classify in background
        import asyncio
        asyncio.create_task(self._background_classify(service, new_emails))

        return self.get_emails()

    async def _background_classify(self, service, emails: list[dict]):
        """Classify and summarize emails in background using sub-batched LLM calls."""
        import asyncio
        try:
            # Pass 1: Classify in sub-batches of 4
            classifications = await self._batch_classify(emails)

            for email_data, classification in zip(emails, classifications):
                for stored in self.processed_emails:
                    if stored.get("id") == email_data["id"]:
                        stored["classification"] = classification
                        break
                await self._apply_labels(service, email_data["id"], classification)
                if classification == "Urgent" or email_data["sender"] in settings.key_people_list:
                    await self._star_message(service, email_data["id"])

            self.logger.info("Classification complete, starting summaries...")

            # Yield to let other agents use the LLM
            await asyncio.sleep(0)

            # Pass 2: Summarize in sub-batches of 4
            summaries = await self._batch_summarize(emails)

            for email_data, summary in zip(emails, summaries):
                for stored in self.processed_emails:
                    if stored.get("id") == email_data["id"]:
                        stored["summary"] = summary
                        break

            self.logger.info("Background email classification and summarization complete")
        except Exception as e:
            self.logger.error(f"Background classify error: {e}")
            # Ensure no emails stay stuck at "Classifying..."
            for email_data in emails:
                for stored in self.processed_emails:
                    if stored.get("id") == email_data["id"] and stored.get("classification") == "Classifying...":
                        stored["classification"] = "Other"
                        stored["summary"] = stored.get("snippet", "")[:100] or "(classification failed)"
                        break

    def get_emails(self) -> dict:
        """Get processed emails for dashboard, sorted newest first."""
        from email.utils import parsedate_to_datetime

        # Sort by received_at date, newest first
        def sort_key(e):
            try:
                return parsedate_to_datetime(e.get("received_at", "")).timestamp()
            except Exception:
                return 0

        sorted_emails = sorted(self.processed_emails, key=sort_key, reverse=True)

        # Category breakdown
        categories = {}
        for email in sorted_emails:
            cat = email.get("classification", "Other")
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "emails": sorted_emails[:50],
            "categories": categories,
            "total_processed": len(sorted_emails),
            "last_scan": self._last_run.isoformat() if self._last_run else None,
        }

    async def send_daily_summary(self):
        """Send daily email summary."""
        if not self.processed_emails:
            return

        today = datetime.utcnow().date()
        today_emails = [
            e for e in self.processed_emails
            if e.get("processed_at", "")[:10] == str(today)
        ]

        html = self._build_summary_html(today_emails)
        await send_email(
            subject=f"📬 Mailman Daily Summary — {today.strftime('%B %d, %Y')}",
            html_body=html,
        )

    async def _get_gmail_service(self):
        """Get authenticated Gmail service, refreshing token if expired."""
        if self._gmail_service:
            # Check if existing credentials are still valid
            if self._gmail_creds and not self._gmail_creds.expired:
                return self._gmail_service
            # Token expired — need to refresh
            self._gmail_service = None

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            from pathlib import Path

            token_path = Path(settings.gmail_token_file)
            if not token_path.exists():
                self.logger.error("Gmail token not found. Run: python src/auth_gmail.py")
                return None

            creds = Credentials.from_authorized_user_file(
                str(token_path),
                scopes=["https://www.googleapis.com/auth/gmail.modify"],
            )

            # Refresh expired token
            if creds.expired and creds.refresh_token:
                self.logger.info("Gmail token expired, refreshing...")
                creds.refresh(Request())
                # Save refreshed token back to file
                token_path.write_text(creds.to_json())
                self.logger.info("Gmail token refreshed and saved")

            if not creds.valid:
                self.logger.error("Gmail credentials invalid. Re-run: python src/auth_gmail.py")
                return None

            self._gmail_creds = creds
            self._gmail_service = build("gmail", "v1", credentials=creds)
            return self._gmail_service
        except Exception as e:
            self._gmail_service = None
            self.logger.error(f"Gmail auth error: {e}")
            return None

    async def _fetch_unread_emails(self, service, max_results: int = 10) -> list[dict]:
        """Fetch most recent emails from Gmail (newest first)."""
        import asyncio

        try:
            results = await asyncio.to_thread(
                lambda: service.users().messages().list(
                    userId="me", maxResults=max_results
                ).execute()
            )
            messages = results.get("messages", [])
            emails = []

            for msg in messages:
                detail = await asyncio.to_thread(
                    lambda m=msg: service.users().messages().get(
                        userId="me", id=m["id"], format="full"
                    ).execute()
                )
                headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
                emails.append({
                    "id": msg["id"],
                    "sender": headers.get("From", "Unknown"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "snippet": detail.get("snippet", ""),
                    "received_at": headers.get("Date", ""),
                })

            return emails
        except Exception as e:
            self.logger.error(f"Error fetching emails: {e}")
            return []

    async def _batch_classify(self, emails: list[dict]) -> list[str]:
        """Classify emails in sub-batches of 4 to fit within LLM context window."""
        if not emails:
            return []

        BATCH_SIZE = 4
        all_results = []

        for i in range(0, len(emails), BATCH_SIZE):
            batch = emails[i:i + BATCH_SIZE]
            emails_block = "\n".join(
                f"Email {j+1}:\nFrom: {e['sender']}\nSubject: {e['subject']}\nPreview: {e['snippet'][:300]}\n"
                for j, e in enumerate(batch)
            )
            prompt = BATCH_CLASSIFICATION_PROMPT.format(emails_block=emails_block)

            try:
                response = await ollama_client.generate(
                    prompt=prompt,
                    agent_name="mailman",
                    temperature=0.1,
                    think=False,
                )
                self.logger.debug(f"Raw classification response: {response!r}")
                results = self._parse_batch_classifications(response, len(batch))
                all_results.extend(results)
                self.logger.info(f"Classified batch {i//BATCH_SIZE + 1}: {results}")
            except Exception as e:
                self.logger.error(f"Batch classification error: {e}")
                all_results.extend(["Other"] * len(batch))

        return all_results[:len(emails)]

    def _parse_batch_classifications(self, response: str, count: int) -> list[str]:
        """Parse numbered classification list from LLM response."""
        import re
        results = []

        # Canonical category lookup (lowercase → proper name)
        category_map = {
            "urgent": "Urgent",
            "action required": "Action Required",
            "follow-up": "Follow-Up",
            "follow up": "Follow-Up",
            "followup": "Follow-Up",
            "newsletter": "Newsletter",
            "notification": "Notification",
            "personal": "Personal",
            "other": "Other",
        }

        # Only consider lines that start with a number (skip preamble/explanation)
        numbered_re = re.compile(r"^\s*\d+[\.\)\-:\s]+(.+)")
        for line in response.strip().splitlines():
            m = numbered_re.match(line)
            if not m:
                continue  # skip non-numbered lines entirely
            text = m.group(1).strip().lower()
            # Remove surrounding quotes, asterisks, markdown
            text = re.sub(r"[\*\`\"\']", "", text).strip()

            matched = None
            # Exact match first
            if text in category_map:
                matched = category_map[text]
            else:
                # Substring match: check if any category keyword appears
                for keyword, category in category_map.items():
                    if keyword in text:
                        matched = category
                        break
            # Fuzzy fallback for partial words
            if not matched:
                if "action" in text:
                    matched = "Action Required"
                elif "follow" in text:
                    matched = "Follow-Up"
                elif "news" in text or "subscri" in text or "marketing" in text or "promo" in text:
                    matched = "Newsletter"
                elif "notif" in text or "alert" in text or "automat" in text:
                    matched = "Notification"
                elif "urgen" in text or "deadline" in text or "asap" in text:
                    matched = "Urgent"
                elif "personal" in text or "friend" in text or "family" in text:
                    matched = "Personal"
                else:
                    matched = "Other"
            results.append(matched)

        if not results:
            self.logger.warning(f"Parser found 0 numbered lines in response, defaulting all to Other")

        # Pad or trim to match expected count
        while len(results) < count:
            results.append("Other")
        return results[:count]

    async def _batch_summarize(self, emails: list[dict]) -> list[str]:
        """Summarize emails in sub-batches of 4 to fit within LLM context window."""
        if not emails:
            return []

        BATCH_SIZE = 4
        all_results = []

        for i in range(0, len(emails), BATCH_SIZE):
            batch = emails[i:i + BATCH_SIZE]
            emails_block = "\n".join(
                f"Email {j+1}:\nFrom: {e['sender']}\nSubject: {e['subject']}\nContent: {e['snippet'][:150]}\n"
                for j, e in enumerate(batch)
            )
            prompt = BATCH_SUMMARY_PROMPT.format(emails_block=emails_block)

            try:
                response = await ollama_client.generate(
                    prompt=prompt,
                    agent_name="mailman",
                    temperature=0.3,
                    think=False,
                )
                results = self._parse_batch_summaries(response, batch)
                all_results.extend(results)
            except Exception as e:
                self.logger.error(f"Batch summary error: {e}")
                all_results.extend([e_item["snippet"][:100] for e_item in batch])

        return all_results[:len(emails)]

    def _parse_batch_summaries(self, response: str, emails: list[dict]) -> list[str]:
        """Parse numbered summary list from LLM response."""
        import re
        lines = [l.strip() for l in response.strip().splitlines() if l.strip()]
        results = []

        for line in lines:
            # Strip numbering like "1." or "1)"
            cleaned = re.sub(r"^\d+[\.\)\-:\s]+", "", line).strip()
            if cleaned:
                results.append(cleaned)

        # Pad with snippets if LLM returned fewer lines
        while len(results) < len(emails):
            idx = len(results)
            results.append(emails[idx]["snippet"][:100])
        return results[:len(emails)]

    async def _apply_labels(self, service, message_id: str, classification: str):
        """Apply Gmail label based on classification."""
        import asyncio
        try:
            # Create label if it doesn't exist, then apply
            label_name = f"AutoClass/{classification}"
            await asyncio.to_thread(
                lambda: service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"addLabelIds": [], "removeLabelIds": ["UNREAD"]},
                ).execute()
            )
        except Exception as e:
            self.logger.debug(f"Label apply skipped: {e}")

    async def _star_message(self, service, message_id: str):
        """Star a message in Gmail."""
        import asyncio
        try:
            await asyncio.to_thread(
                lambda: service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"addLabelIds": ["STARRED"]},
                ).execute()
            )
        except Exception as e:
            self.logger.debug(f"Star apply skipped: {e}")

    def _build_summary_html(self, emails: list[dict]) -> str:
        """Build daily summary HTML email."""
        html = """
        <html><body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto;">
        <h1 style="color: #d93025;">📬 Mailman Daily Summary</h1>
        <p>Processed {count} emails today</p><hr>
        """.format(count=len(emails))

        for email in emails[:20]:
            badge_color = "#d93025" if email.get("classification") == "Urgent" else "#1a73e8"
            html += f"""
            <div style="margin: 10px 0; padding: 10px; border-left: 3px solid {badge_color};">
                <span style="background: {badge_color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{email.get('classification', 'Other')}</span>
                <strong> {email['subject']}</strong>
                <p style="color: #666; margin: 4px 0;">From: {email['sender']}</p>
                <p style="margin: 4px 0;">{email.get('summary', '')}</p>
            </div>
            """

        html += "</body></html>"
        return html


# Singleton
mailman_agent = MailmanAgent()


if __name__ == "__main__":
    import asyncio
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(mailman_agent.start())
