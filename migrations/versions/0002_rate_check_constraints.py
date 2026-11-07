"""rate check constraints

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERIOD_FORMAT = "length(period) = 7 AND substr(period, 5, 1) = '-' AND substr(period, 6, 2) BETWEEN '01' AND '12'"


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("rate_observation") as batch:
        batch.create_check_constraint("ck_rate_observation_period_format", PERIOD_FORMAT)
        batch.create_check_constraint("ck_rate_observation_rate_non_negative", "rate_per_kwh >= 0")
        batch.create_check_constraint(
            "ck_rate_observation_generation_non_negative",
            "generation_charge_per_kwh IS NULL OR generation_charge_per_kwh >= 0",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("rate_observation") as batch:
        batch.drop_constraint("ck_rate_observation_generation_non_negative", type_="check")
        batch.drop_constraint("ck_rate_observation_rate_non_negative", type_="check")
        batch.drop_constraint("ck_rate_observation_period_format", type_="check")
