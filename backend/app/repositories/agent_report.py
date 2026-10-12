from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.agent_chat import AgentChatMessage, AgentChatSession, AgentChatTurn
from app.models.agent_report import AgentResearchReport, AgentResearchReportComparison


class AgentReportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_owned_source_message(
        self, *, owner_user_id: uuid.UUID, chat_id: uuid.UUID, message_id: uuid.UUID
    ) -> AgentChatMessage | None:
        return self.db.execute(
            select(AgentChatMessage)
            .join(AgentChatSession, AgentChatSession.id == AgentChatMessage.session_id)
            .where(
                AgentChatMessage.id == message_id,
                AgentChatMessage.session_id == chat_id,
                AgentChatSession.owner_user_id == owner_user_id,
            )
        ).scalar_one_or_none()

    def get_source_turn(
        self, *, chat_id: uuid.UUID, message_id: uuid.UUID
    ) -> AgentChatTurn | None:
        return self.db.execute(
            select(AgentChatTurn).where(
                AgentChatTurn.session_id == chat_id,
                AgentChatTurn.assistant_message_id == message_id,
                AgentChatTurn.status == "COMPLETED",
            )
        ).scalar_one_or_none()

    def add_report(self, **values: object) -> AgentResearchReport:
        row = AgentResearchReport(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def get_by_request(
        self, *, owner_user_id: uuid.UUID, request_id: str
    ) -> AgentResearchReport | None:
        return self.db.execute(
            select(AgentResearchReport).where(
                AgentResearchReport.owner_user_id == owner_user_id,
                AgentResearchReport.request_id == request_id,
            )
        ).scalar_one_or_none()

    def get_owned_report(
        self, *, owner_user_id: uuid.UUID, report_id: uuid.UUID, for_update: bool = False
    ) -> AgentResearchReport | None:
        statement = select(AgentResearchReport).where(
            AgentResearchReport.id == report_id,
            AgentResearchReport.owner_user_id == owner_user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.execute(statement).scalar_one_or_none()

    def report_page(
        self,
        *,
        owner_user_id: uuid.UUID,
        limit: int,
        offset: int,
        include_archived: bool,
        report_type: str | None,
        archived: bool | None,
    ) -> tuple[list[AgentResearchReport], int]:
        where = [AgentResearchReport.owner_user_id == owner_user_id]
        if report_type is not None:
            where.append(AgentResearchReport.report_type == report_type)
        if archived is True:
            where.append(AgentResearchReport.archived_at.is_not(None))
        elif archived is False or not include_archived:
            where.append(AgentResearchReport.archived_at.is_(None))
        total = int(
            self.db.scalar(select(func.count()).select_from(AgentResearchReport).where(*where))
            or 0
        )
        rows = list(
            self.db.scalars(
                select(AgentResearchReport)
                .where(*where)
                .order_by(AgentResearchReport.created_at.desc(), AgentResearchReport.id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return rows, total

    def archive(self, row: AgentResearchReport) -> AgentResearchReport:
        if row.archived_at is None:
            row.archived_at = datetime.now(UTC)
            self.db.add(row)
            self.db.flush()
        return row

    def add_comparison(self, **values: object) -> AgentResearchReportComparison:
        row = AgentResearchReportComparison(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def get_comparison_by_request(
        self, *, owner_user_id: uuid.UUID, request_id: str
    ) -> AgentResearchReportComparison | None:
        return self.db.execute(
            select(AgentResearchReportComparison).where(
                AgentResearchReportComparison.owner_user_id == owner_user_id,
                AgentResearchReportComparison.request_id == request_id,
            )
        ).scalar_one_or_none()

    def get_owned_comparison(
        self, *, owner_user_id: uuid.UUID, comparison_id: uuid.UUID
    ) -> AgentResearchReportComparison | None:
        return self.db.execute(
            select(AgentResearchReportComparison).where(
                AgentResearchReportComparison.id == comparison_id,
                AgentResearchReportComparison.owner_user_id == owner_user_id,
            )
        ).scalar_one_or_none()
