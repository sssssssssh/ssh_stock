from sqlalchemy import select

from app.domain.decision.contracts import PaperError, content_hash
from app.domain.decision.risk import plan_order
from app.models.paper import (
    DecisionApprovalEvent,
    DecisionObservation,
    DecisionProposal,
    PaperAccount,
    PaperAccountEvent,
    PaperDayRun,
    PaperNavDaily,
    PaperOrder,
)
from app.repositories.paper import PaperRepository
from app.services.decision.source import DecisionSourceReadiness
from app.services.paper.account_state import account_settings, frozen_config, load_close
from app.services.paper.records import (
    make_record,
    next_open,
    open_cutoff,
    replay,
    request_hash,
    request_lock,
    utc_now,
    verify_record,
)


class ApprovalApplication:
    def __init__(self, db, settings, *, clock=utc_now, fault_hook=None):
        self.db, self.settings, self.clock = db, settings, clock
        self.repo = PaperRepository(db)
        self.fault_hook = fault_hook or (lambda phase: None)

    def approve(self, owner, proposal_id, body):
        return self._decide(owner, proposal_id, body, approved=True)

    def reject(self, owner, proposal_id, body):
        return self._decide(owner, proposal_id, body, approved=False)

    def _decide(self, owner, proposal_id, body, *, approved):
        if not self.settings.paper_config.enabled:
            raise PaperError("PAPER_DISABLED", status_code=403)
        account = None
        operation = "approve" if approved else "reject"
        digest = content_hash([str(proposal_id), request_hash(owner, operation, body)])
        try:
            request_lock(self.db, owner, "approval", body.request_id)
            event = replay(
                self.repo.by_request(DecisionApprovalEvent, owner, body.request_id), digest
            )
            if event:
                self.db.commit()
                return event
            proposal = self.repo.owned(DecisionProposal, owner, proposal_id)
            account = self.repo.owned(PaperAccount, owner, proposal.account_id, lock=True)
            proposal = self.repo.owned(DecisionProposal, owner, proposal_id, lock=True)
            frozen = verify_record(proposal)
            verify_record(account)
            if proposal.state != "PENDING_REVIEW":
                raise PaperError("DECISION_ALREADY_TERMINAL")
            if account.state == "CLOSED":
                raise PaperError("PAPER_ACCOUNT_CLOSED")
            now, plan, scheduled = self.clock(), None, None
            if approved:
                if account.state != "ACTIVE":
                    raise PaperError("PAPER_ACCOUNT_PAUSED")
                if now >= proposal.expires_at:
                    raise PaperError("DECISION_APPROVAL_WINDOW_EXPIRED")
                observation = self.repo.owned(DecisionObservation, owner, proposal.observation_id)
                source = verify_record(observation)
                if frozen["observation_hash"] != observation.record_hash:
                    raise PaperError("DECISION_SOURCE_DRIFT")
                current = DecisionSourceReadiness(
                    self.db, account_settings(account, self.settings)
                ).capture(
                    observation.signal_date, cutoff=now, include_codes=source["include_codes"]
                )
                if any(
                    current[key] != source[key]
                    for key in ("source_hash", "strategy_identity_hash", "candidate_snapshot_hash")
                ):
                    raise PaperError("DECISION_SOURCE_DRIFT")
                scheduled = next_open(self.db, observation.signal_date)
                if now >= open_cutoff(scheduled) or scheduled < account.first_trade_date:
                    raise PaperError("DECISION_APPROVAL_WINDOW_EXPIRED")
                if self.db.scalar(
                    select(PaperDayRun.id)
                    .where(
                        PaperDayRun.account_id == account.id, PaperDayRun.trade_date == scheduled
                    )
                    .limit(1)
                ):
                    raise PaperError("PAPER_SETTLEMENT_STARTED")
                snapshot, contexts, snapshot_hash = load_close(
                    self.db, account, observation.signal_date
                )
                nav = self.db.scalar(
                    select(PaperNavDaily).where(
                        PaperNavDaily.account_id == account.id,
                        PaperNavDaily.trade_date == observation.signal_date,
                    )
                )
                if nav and nav.source_hash != current["source_hash"]:
                    raise PaperError("PAPER_SOURCE_DRIFT")
                pending = list(
                    self.db.scalars(
                        select(PaperOrder)
                        .where(
                            PaperOrder.account_id == account.id,
                            PaperOrder.status == "ORDER_PENDING",
                        )
                        .order_by(PaperOrder.id)
                    )
                )
                pending = [
                    {
                        "ts_code": order.ts_code,
                        "side": order.side,
                        "target_weight": order.target_weight,
                        "data": verify_record(order),
                    }
                    for order in pending
                ]
                plan = plan_order(
                    candidate=frozen["candidate"],
                    action=proposal.action,
                    weight=body.target_weight,
                    snapshot=snapshot,
                    contexts=contexts,
                    pending=pending,
                    scheduled=scheduled,
                    config=frozen_config(account),
                )
                plan["account_snapshot_hash"] = snapshot_hash
            decision = "APPROVED" if approved else "REJECTED"
            event = make_record(
                DecisionApprovalEvent,
                owner,
                body.request_id,
                now=now,
                data={
                    "proposal_hash": proposal.record_hash,
                    "plan": plan,
                    "scheduled_date": scheduled,
                    "note": body.note if approved else body.reason,
                    "approval_mode": "MANUAL_CONFIRM",
                },
                account_id=account.id,
                proposal_id=proposal.id,
                actor_user_id=owner,
                decision=decision,
                approved_target_weight=body.target_weight if approved else proposal.target_weight,
                event_at=now,
                request_id=body.request_id,
                request_hash=digest,
            )
            self.repo.add(event)
            self.fault_hook("after_approval")
            if plan:
                self.repo.add(
                    make_record(
                        PaperOrder,
                        owner,
                        str(event.id),
                        now=now,
                        data=plan,
                        account_id=account.id,
                        approval_id=event.id,
                        proposal_id=proposal.id,
                        signal_date=observation.signal_date,
                        scheduled_date=scheduled,
                        ts_code=proposal.ts_code,
                        side=plan["side"],
                        quantity=plan["quantity"],
                        target_weight=body.target_weight,
                        source_hash=frozen["source_hash"],
                    )
                )
            proposal.state, proposal.version = decision, proposal.version + 1
            self.db.flush()
            self.fault_hook("before_commit")
            self.db.commit()
            return event
        except Exception as exc:
            self.db.rollback()
            if isinstance(exc, PaperError) and account is not None and exc.status_code != 404:
                self._blocked_audit(
                    owner, proposal_id, account.id, body.request_id, digest, exc.code
                )
            raise

    def _blocked_audit(self, owner, proposal_id, account_id, original_request, digest, reason):
        request = "blocked:" + digest
        request_lock(self.db, owner, "approval-blocked", request)
        if self.repo.by_request(PaperAccountEvent, owner, request) is None:
            account = self.repo.owned(PaperAccount, owner, account_id, lock=True)
            self.repo.add(
                make_record(
                    PaperAccountEvent,
                    owner,
                    request,
                    now=self.clock(),
                    data={
                        "kind": "APPROVAL_BLOCKED",
                        "proposal_id": proposal_id,
                        "reason_code": reason,
                        "original_request_id": original_request,
                        "payload_hash": digest,
                    },
                    account_id=account_id,
                    from_state=account.state,
                    to_state=account.state,
                    request_id=request,
                    request_hash=digest,
                )
            )
        self.db.commit()
