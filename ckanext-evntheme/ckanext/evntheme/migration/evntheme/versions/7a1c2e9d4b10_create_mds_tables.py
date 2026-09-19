"""Create the shared code list (MDS) tables

Revision ID: 7a1c2e9d4b10
Revises:
Create Date: 2026-09-19 18:00:00

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7a1c2e9d4b10"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mds_catalog",
        sa.Column("id", sa.UnicodeText, primary_key=True),
        sa.Column("code", sa.UnicodeText, nullable=False, unique=True),
        sa.Column("name", sa.UnicodeText, nullable=False),
        sa.Column("group_name", sa.UnicodeText, nullable=False, server_default=""),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("description", sa.UnicodeText, nullable=False, server_default=""),
        sa.Column("version", sa.UnicodeText, nullable=False, server_default=""),
        sa.Column("effective_from", sa.Date),
        sa.Column("status", sa.UnicodeText, nullable=False, server_default="active"),
        sa.Column("issuer", sa.UnicodeText, nullable=False, server_default=""),
        sa.Column("sync_note", sa.UnicodeText, nullable=False, server_default=""),
        sa.Column("name_label", sa.UnicodeText, nullable=False, server_default=""),
        sa.Column("count_label", sa.UnicodeText, nullable=False, server_default=""),
        sa.Column("created", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("modified", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "mds_code",
        sa.Column("id", sa.UnicodeText, primary_key=True),
        sa.Column("catalog_id", sa.UnicodeText, sa.ForeignKey("mds_catalog.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("code", sa.UnicodeText, nullable=False),
        sa.Column("name", sa.UnicodeText, nullable=False),
        sa.Column("parent_code", sa.UnicodeText),
        sa.Column("item_count", sa.Integer),
        sa.Column("status", sa.UnicodeText, nullable=False, server_default="active"),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("catalog_id", "code"),
    )
    op.create_table(
        "mds_version",
        sa.Column("id", sa.UnicodeText, primary_key=True),
        sa.Column("catalog_id", sa.UnicodeText, sa.ForeignKey("mds_catalog.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("version", sa.UnicodeText, nullable=False),
        sa.Column("note", sa.UnicodeText, nullable=False, server_default=""),
        sa.Column("released_on", sa.Date),
    )
    op.create_table(
        "mds_consumer",
        sa.Column("id", sa.UnicodeText, primary_key=True),
        sa.Column("catalog_id", sa.UnicodeText, sa.ForeignKey("mds_catalog.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("system_name", sa.UnicodeText, nullable=False),
        sa.Column("sync_note", sa.UnicodeText, nullable=False, server_default=""),
        sa.Column("status", sa.UnicodeText, nullable=False, server_default="ok"),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade():
    for table in ("mds_consumer", "mds_version", "mds_code", "mds_catalog"):
        op.drop_table(table)
