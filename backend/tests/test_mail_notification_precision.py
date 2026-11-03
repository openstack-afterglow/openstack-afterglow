"""Notification opt-in must work with existing second-resolution activity rows."""

from datetime import timedelta

from sqlalchemy import select

from app.models.activity import ActivityLog
from app.models.email_delivery import EmailOperation
from app.services import mail_delivery as svc
from tests.test_mail_delivery import NOW, USER, rows
from tests.test_mail_delivery import state as state


async def test_subsecond_optin_keeps_current_second_errors_without_older_history(state, monkeypatch):
    activated = NOW + timedelta(microseconds=500000)
    monkeypatch.setattr(svc, "_now", lambda: activated)
    state.settings.notifications.resource_alerts_enabled = True
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": True})
    await svc._collect_notifications(state.settings, activated, 50)
    async with state.factory() as session, session.begin():
        # Existing MariaDB DATETIME activity storage does not preserve the
        # subsecond part of an event created immediately after this opt-in.
        for event_id, timestamp in ((1, NOW - timedelta(seconds=1)), (2, NOW)):
            session.add(
                ActivityLog(
                    id=event_id,
                    created_at=timestamp,
                    project_id="project",
                    user_id=USER,
                    username="user",
                    resource_type="instance",
                    resource_id="instance-id",
                    action="create",
                    status="failed",
                    source="afterglow",
                )
            )
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=2), 50)
    deliveries = await rows(state)
    assert [delivery.user_id for delivery in deliveries] == [USER]
    async with state.factory() as session:
        observed = (
            await session.scalars(
                select(EmailOperation.notification_activity_id).where(
                    EmailOperation.notification_activity_id.is_not(None)
                )
            )
        ).all()
    assert observed == [2]
