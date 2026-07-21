from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sber_a2a.domain.models import LedgerAnchorRecord, utc_now
from sber_a2a.shared.security.signatures import canonical_json, payload_hash

GENESIS_HASH = "0" * 64


class LedgerBase(DeclarativeBase):
    pass


class LedgerAnchorRow(LedgerBase):
    __tablename__ = "ledger_anchors"
    __table_args__ = (
        UniqueConstraint("deal_id", "sequence_number", name="uq_anchor_deal_sequence"),
        UniqueConstraint("deal_id", "current_hash", name="uq_anchor_deal_hash"),
    )

    anchor_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    deal_id: Mapped[str] = mapped_column(String(36), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    previous_hash: Mapped[str] = mapped_column(String(64))
    current_hash: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DatabaseHashChainAnchor:
    """Append-only SQL hash chain; it is deliberately not called a blockchain."""

    def __init__(self, database_url: str) -> None:
        url = make_url(database_url)
        if (
            url.drivername.startswith("sqlite")
            and url.database is not None
            and url.database != ":memory:"
        ):
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        options: dict = {"pool_pre_ping": True}
        if database_url.endswith(":memory:"):
            from sqlalchemy.pool import StaticPool

            options["poolclass"] = StaticPool
        self._engine: AsyncEngine = create_async_engine(database_url, **options)
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)
        self._initialized = False
        self._initialize_lock = asyncio.Lock()
        self._append_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._initialize_lock:
            if self._initialized:
                return
            async with self._engine.begin() as connection:
                await connection.run_sync(LedgerBase.metadata.create_all)
            self._initialized = True

    async def append(self, deal_id: UUID, payload: dict) -> LedgerAnchorRecord:
        await self.initialize()
        encoded_hash = payload_hash(payload)
        async with self._append_lock, self._sessions.begin() as session:
            latest = (
                await session.execute(
                    select(LedgerAnchorRow)
                    .where(LedgerAnchorRow.deal_id == str(deal_id))
                    .order_by(LedgerAnchorRow.sequence_number.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            sequence = (latest.sequence_number + 1) if latest else 1
            previous_hash = latest.current_hash if latest else GENESIS_HASH
            current_hash = hashlib.sha256(
                canonical_json(
                    {
                        "deal_id": str(deal_id),
                        "sequence_number": sequence,
                        "previous_hash": previous_hash,
                        "payload_hash": encoded_hash,
                    }
                )
            ).hexdigest()
            anchor = LedgerAnchorRecord(
                anchor_id=uuid4(),
                deal_id=deal_id,
                sequence_number=sequence,
                previous_hash=previous_hash,
                current_hash=current_hash,
                payload_hash=encoded_hash,
                created_at=utc_now(),
            )
            session.add(
                LedgerAnchorRow(
                    anchor_id=str(anchor.anchor_id),
                    deal_id=str(anchor.deal_id),
                    sequence_number=anchor.sequence_number,
                    previous_hash=anchor.previous_hash,
                    current_hash=anchor.current_hash,
                    payload_hash=anchor.payload_hash,
                    created_at=anchor.created_at,
                )
            )
            return anchor

    async def list(self, deal_id: UUID) -> list[LedgerAnchorRecord]:
        await self.initialize()
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(LedgerAnchorRow)
                        .where(LedgerAnchorRow.deal_id == str(deal_id))
                        .order_by(LedgerAnchorRow.sequence_number)
                    )
                )
                .scalars()
                .all()
            )
        return [
            LedgerAnchorRecord(
                anchor_id=row.anchor_id,
                deal_id=row.deal_id,
                sequence_number=row.sequence_number,
                previous_hash=row.previous_hash,
                current_hash=row.current_hash,
                payload_hash=row.payload_hash,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def verify(self, deal_id: UUID) -> bool:
        previous = GENESIS_HASH
        for expected_sequence, anchor in enumerate(await self.list(deal_id), start=1):
            expected = hashlib.sha256(
                canonical_json(
                    {
                        "deal_id": str(deal_id),
                        "sequence_number": expected_sequence,
                        "previous_hash": previous,
                        "payload_hash": anchor.payload_hash,
                    }
                )
            ).hexdigest()
            if (
                anchor.sequence_number != expected_sequence
                or anchor.previous_hash != previous
                or anchor.current_hash != expected
            ):
                return False
            previous = anchor.current_hash
        return True

    async def close(self) -> None:
        await self._engine.dispose()
