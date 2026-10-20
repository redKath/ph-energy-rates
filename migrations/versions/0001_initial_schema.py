"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-20 17:56:41.799361

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "utility",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "private_du",
                "electric_cooperative",
                "supplier",
                name="ck_utilitytype",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("psgc_code", sa.String(length=16), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("erc_id", sa.String(length=64), nullable=True),
        sa.Column("nea_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "pipeline_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("utility_id", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "succeeded",
                "failed",
                name="ck_runstatus",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("documents_fetched", sa.Integer(), nullable=False),
        sa.Column("rates_created", sa.Integer(), nullable=False),
        sa.Column("rates_flagged", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["utility_id"],
            ["utility.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pipeline_run_utility_id"), "pipeline_run", ["utility_id"], unique=False
    )
    op.create_table(
        "source_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("utility_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("archive_path", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["utility_id"],
            ["utility.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("utility_id", "sha256"),
    )
    op.create_index(
        op.f("ix_source_document_utility_id"), "source_document", ["utility_id"], unique=False
    )
    op.create_table(
        "rate_observation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("utility_id", sa.String(length=64), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column(
            "customer_class",
            sa.Enum(
                "residential",
                name="ck_customerclass",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("rate_per_kwh", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column(
            "rate_basis",
            sa.Enum(
                "published_total",
                "summed_components",
                name="ck_ratebasis",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("generation_charge_per_kwh", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=False),
        sa.Column(
            "extraction_method",
            sa.Enum(
                "html_parser",
                "pdf_parser",
                "ocr_parser",
                "llm",
                "manual",
                name="ck_extractionmethod",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("confidence", sa.Double(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "published",
                "flagged",
                "rejected",
                name="ck_ratestatus",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("flags", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_document.id"],
        ),
        sa.ForeignKeyConstraint(
            ["utility_id"],
            ["utility.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("utility_id", "period", "customer_class", "source_document_id"),
    )
    op.create_index(
        op.f("ix_rate_observation_period"), "rate_observation", ["period"], unique=False
    )
    op.create_index(
        op.f("ix_rate_observation_status"), "rate_observation", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_rate_observation_utility_id"), "rate_observation", ["utility_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_rate_observation_utility_id"), table_name="rate_observation")
    op.drop_index(op.f("ix_rate_observation_status"), table_name="rate_observation")
    op.drop_index(op.f("ix_rate_observation_period"), table_name="rate_observation")
    op.drop_table("rate_observation")
    op.drop_index(op.f("ix_source_document_utility_id"), table_name="source_document")
    op.drop_table("source_document")
    op.drop_index(op.f("ix_pipeline_run_utility_id"), table_name="pipeline_run")
    op.drop_table("pipeline_run")
    op.drop_table("utility")
