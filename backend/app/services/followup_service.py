from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.config import settings
from app.models.email import Email
from app.models.email_analysis import EmailAnalysis
from app.models.followup_item import FollowupItem
from app.models.user import User
from app.schemas.followup_schema import FollowupExtractionItem


class FollowupService:
    def sync_email_followups(
        self,
        *,
        db: Session,
        user: User,
        email_row: Email,
        analysis: EmailAnalysis,
        extracted_items: list[FollowupExtractionItem] | None,
    ) -> list[FollowupItem]:
        existing_open = (
            db.query(FollowupItem)
            .filter(FollowupItem.user_id == user.id)
            .filter(FollowupItem.email_id == email_row.id)
            .filter(FollowupItem.status == "open")
            .all()
        )
        existing_by_key = {self._task_key(item.task_text): item for item in existing_open}

        normalized_items = extracted_items or self._fallback_items_from_analysis(analysis=analysis)
        candidate_keys = {self._task_key(item.task) for item in normalized_items}

        for row in existing_open:
            if self._task_key(row.task_text) not in candidate_keys:
                row.status = "resolved_auto"
                row.resolved_at = datetime.now(timezone.utc)
                db.add(row)

        created_or_updated: list[FollowupItem] = []
        for item in normalized_items:
            key = self._task_key(item.task)
            due_at = self._parse_due_at(item.due_at_iso, user.timezone)
            existing = existing_by_key.get(key)
            if existing:
                existing.due_at = due_at
                existing.due_label = (item.due_label or "").strip() or None
                existing.needs_reply = bool(item.needs_reply)
                existing.confidence_score = item.confidence_score
                existing.source_quote = (item.source_quote or "").strip() or None
                existing.priority_score = max(analysis.priority_score, 1)
                db.add(existing)
                created_or_updated.append(existing)
                continue

            row = FollowupItem(
                user_id=user.id,
                email_id=email_row.id,
                task_text=item.task.strip(),
                due_at=due_at,
                due_label=(item.due_label or "").strip() or None,
                status="open",
                needs_reply=bool(item.needs_reply),
                priority_score=max(analysis.priority_score, 1),
                confidence_score=item.confidence_score,
                source_quote=(item.source_quote or "").strip() or None,
            )
            db.add(row)
            created_or_updated.append(row)

        db.commit()
        for row in created_or_updated:
            db.refresh(row)
        return created_or_updated

    def list_open_followups(self, *, db: Session, user: User, limit: int = 10) -> list[FollowupItem]:
        return (
            db.query(FollowupItem)
            .filter(FollowupItem.user_id == user.id)
            .filter(FollowupItem.status == "open")
            .order_by(FollowupItem.due_at.asc().nulls_last(), FollowupItem.priority_score.desc(), FollowupItem.created_at.desc())
            .limit(max(1, min(limit, 30)))
            .all()
        )

    def list_due_today(self, *, db: Session, user: User, now_utc: datetime | None = None, limit: int = 20) -> list[FollowupItem]:
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        user_tz = self._resolve_user_timezone(user.timezone)
        start_local = now.astimezone(user_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        return (
            db.query(FollowupItem)
            .filter(FollowupItem.user_id == user.id)
            .filter(FollowupItem.status == "open")
            .filter(FollowupItem.due_at.is_not(None))
            .filter(FollowupItem.due_at >= start_utc)
            .filter(FollowupItem.due_at < end_utc)
            .order_by(FollowupItem.due_at.asc(), FollowupItem.priority_score.desc())
            .limit(max(1, min(limit, 50)))
            .all()
        )

    def list_due_for_reminder(self, *, db: Session, user: User, now_utc: datetime | None = None) -> list[FollowupItem]:
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        lead_minutes = max(settings.followup_reminder_lead_minutes, 0)
        cooldown_hours = max(settings.followup_reminder_cooldown_hours, 1)
        due_before = now + timedelta(minutes=lead_minutes)
        reminded_before = now - timedelta(hours=cooldown_hours)

        return (
            db.query(FollowupItem)
            .filter(FollowupItem.user_id == user.id)
            .filter(FollowupItem.status == "open")
            .filter(FollowupItem.due_at.is_not(None))
            .filter(FollowupItem.due_at <= due_before)
            .filter((FollowupItem.last_reminded_at.is_(None)) | (FollowupItem.last_reminded_at <= reminded_before))
            .order_by(FollowupItem.due_at.asc(), FollowupItem.priority_score.desc())
            .limit(5)
            .all()
        )

    @staticmethod
    def mark_reminded(*, db: Session, rows: list[FollowupItem], reminded_at_utc: datetime | None = None) -> None:
        if not rows:
            return
        now = (reminded_at_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        for row in rows:
            row.last_reminded_at = now
            db.add(row)
        db.commit()

    @staticmethod
    def _task_key(text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    def _parse_due_at(self, due_at_iso: str | None, user_timezone: str | None) -> datetime | None:
        if not due_at_iso:
            return None
        raw = due_at_iso.strip()
        if not raw:
            return None
        candidate = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=self._resolve_user_timezone(user_timezone))
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _resolve_user_timezone(value: str | None):
        name = (value or "UTC").strip() or "UTC"
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            return timezone.utc

    @staticmethod
    def _fallback_items_from_analysis(analysis: EmailAnalysis) -> list[FollowupExtractionItem]:
        items: list[FollowupExtractionItem] = []
        for task in analysis.extracted_tasks:
            task_text = str(task).strip()
            if not task_text:
                continue
            items.append(
                FollowupExtractionItem(
                    task=task_text,
                    due_at_iso=None,
                    due_label=None,
                    needs_reply=True,
                    confidence_score=max(min(analysis.confidence_score, 1.0), 0.0),
                    source_quote=None,
                )
            )
        return items[:8]

