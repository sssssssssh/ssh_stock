from sqlalchemy import select

from app.domain.decision.contracts import PaperError


class PaperRepository:
    def __init__(self, db):
        self.db = db

    def owned(self, model, owner_id, row_id, *, lock=False):
        query = select(model).where(model.id == row_id, model.owner_user_id == owner_id)
        row = self.db.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise PaperError("PAPER_NOT_FOUND", status_code=404)
        return row

    def by_request(self, model, owner_id, request_id):
        return self.db.scalar(
            select(model).where(model.owner_user_id == owner_id, model.request_id == request_id)
        )

    def add(self, row):
        self.db.add(row)
        self.db.flush()
        return row
