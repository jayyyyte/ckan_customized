"""Tables of the shared code lists ("Danh mục chuẩn", MDS).

Created by the extension's Alembic migrations: ``ckan db upgrade -p evntheme``.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, UnicodeText, UniqueConstraint
from sqlalchemy.orm import relationship

import ckan.plugins.toolkit as tk
from ckan.model.types import make_uuid


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class MdsCatalog(tk.BaseModel):
    """One published code list, e.g. MDS-VT-001 'Nhóm vật tư thiết bị'."""

    __tablename__ = "mds_catalog"

    id = Column(UnicodeText, primary_key=True, default=make_uuid)
    code = Column(UnicodeText, nullable=False, unique=True)
    name = Column(UnicodeText, nullable=False)
    group = Column("group_name", UnicodeText, nullable=False, default="")
    position = Column(Integer, nullable=False, default=0)
    description = Column(UnicodeText, nullable=False, default="")
    version = Column(UnicodeText, nullable=False, default="")
    effective_from = Column(Date)
    status = Column(UnicodeText, nullable=False, default="active")
    issuer = Column(UnicodeText, nullable=False, default="")
    sync_note = Column(UnicodeText, nullable=False, default="")
    # Column headers differ per list ("Tên nhóm" / "Số vật tư" vs "Tên đơn vị"...).
    name_label = Column(UnicodeText, nullable=False, default="")
    count_label = Column(UnicodeText, nullable=False, default="")
    created = Column(DateTime, nullable=False, default=_now)
    modified = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    codes = relationship(
        "MdsCode", back_populates="catalog", cascade="all, delete-orphan",
        order_by=lambda: (MdsCode.position, MdsCode.code),
    )
    versions = relationship(
        "MdsVersion", back_populates="catalog", cascade="all, delete-orphan",
        order_by=lambda: MdsVersion.released_on.desc(),
    )
    consumers = relationship(
        "MdsConsumer", back_populates="catalog", cascade="all, delete-orphan",
        order_by=lambda: MdsConsumer.position,
    )


class MdsCode(tk.BaseModel):
    """One code inside a catalog. Hierarchy through `parent_code` (VT-01 -> VT-01-01)."""

    __tablename__ = "mds_code"
    __table_args__ = (UniqueConstraint("catalog_id", "code"),)

    id = Column(UnicodeText, primary_key=True, default=make_uuid)
    catalog_id = Column(UnicodeText, ForeignKey("mds_catalog.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(UnicodeText, nullable=False)
    name = Column(UnicodeText, nullable=False)
    parent_code = Column(UnicodeText)
    item_count = Column(Integer)
    status = Column(UnicodeText, nullable=False, default="active")
    position = Column(Integer, nullable=False, default=0)

    catalog = relationship("MdsCatalog", back_populates="codes")


class MdsVersion(tk.BaseModel):
    """Release history of a catalog."""

    __tablename__ = "mds_version"

    id = Column(UnicodeText, primary_key=True, default=make_uuid)
    catalog_id = Column(UnicodeText, ForeignKey("mds_catalog.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(UnicodeText, nullable=False)
    note = Column(UnicodeText, nullable=False, default="")
    released_on = Column(Date)

    catalog = relationship("MdsCatalog", back_populates="versions")


class MdsConsumer(tk.BaseModel):
    """A system that references a catalog (ERP, EAM...) and how it stays in sync."""

    __tablename__ = "mds_consumer"

    id = Column(UnicodeText, primary_key=True, default=make_uuid)
    catalog_id = Column(UnicodeText, ForeignKey("mds_catalog.id", ondelete="CASCADE"), nullable=False, index=True)
    system_name = Column(UnicodeText, nullable=False)
    sync_note = Column(UnicodeText, nullable=False, default="")
    status = Column(UnicodeText, nullable=False, default="ok")
    position = Column(Integer, nullable=False, default=0)

    catalog = relationship("MdsCatalog", back_populates="consumers")
