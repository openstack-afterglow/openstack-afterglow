"""Per-domain network policy: address ranges reserved for VPN tunnels.

Absence of a row means the documented default (Waygate's default tunnel CIDR).
The Keystone domain ID is the tenant boundary; no credential is stored here.
"""

from datetime import UTC, datetime

from sqlalchemy import BIGINT, JSON, VARCHAR, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class DomainNetworkPolicy(Base):
    __tablename__ = "domain_network_policies"

    domain_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    vpn_reserved_cidrs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(BIGINT, nullable=False, default=1)
    updated_by_user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
