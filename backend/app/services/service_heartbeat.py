import os
import socket
import threading
import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.job import ServiceHeartbeat


def new_instance_id(service_name: str) -> str:
    return f"{service_name}:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def touch_service_heartbeat(
    db,
    service_name: str,
    instance_id: str,
    *,
    now: datetime | None = None,
    metadata: dict[str, object] | None = None,
) -> ServiceHeartbeat:
    current = now or datetime.now(UTC)
    row = db.scalar(
        select(ServiceHeartbeat).where(
            ServiceHeartbeat.service_name == service_name,
            ServiceHeartbeat.instance_id == instance_id,
        )
    )
    if row is None:
        row = ServiceHeartbeat(
            service_name=service_name,
            instance_id=instance_id,
            started_at=current,
            heartbeat_at=current,
            version=get_settings().algo_version,
            status="UP",
            service_metadata=metadata or {},
        )
    else:
        row.heartbeat_at = current
        row.status = "UP"
        row.service_metadata = metadata or row.service_metadata
    db.add(row)
    db.commit()
    return row


def start_service_heartbeat(
    service_name: str, *, interval_seconds: float = 45
) -> tuple[threading.Event, threading.Thread]:
    stop = threading.Event()
    instance_id = new_instance_id(service_name)

    def loop() -> None:
        while not stop.is_set():
            try:
                with SessionLocal() as db:
                    touch_service_heartbeat(db, service_name, instance_id)
            except Exception:
                logger.exception(
                    "service heartbeat failed service={} instance={}",
                    service_name,
                    instance_id,
                )
            stop.wait(interval_seconds)

    thread = threading.Thread(target=loop, name=f"{service_name}-heartbeat", daemon=True)
    thread.start()
    return stop, thread
