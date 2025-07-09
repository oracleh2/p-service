"""remove_rotation_method_enum_constraint

Revision ID: e1d9aec7a691
Revises: 958f75e5f351
Create Date: 2025-07-09 15:52:29.844031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1d9aec7a691'
down_revision: Union[str, None] = '958f75e5f351'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем жесткое ограничение на методы ротации
    op.drop_constraint('rotation_config_rotation_method_check', 'rotation_config', type_='check')

def downgrade() -> None:
    # При откате возвращаем исходное ограничение
    op.create_check_constraint(
        'rotation_config_rotation_method_check',
        'rotation_config',
        "rotation_method IN ('airplane_mode', 'data_toggle', 'api_call', 'network_reset')"
    )
