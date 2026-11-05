"""create eventos_analytics

Revision ID: 8d4f68e6ba5f
Revises: e5f8a2b4c7d9
Create Date: 2026-10-26 14:59:12.487957

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8d4f68e6ba5f'
down_revision = 'e5f8a2b4c7d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('eventos_analytics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.Enum('visita_site', 'abertura_cardapio', 'selecao_unidade', 'visualizacao_produto', 'clique_pedir', name='tipo_evento_analytics'), nullable=False),
    sa.Column('primeiro_na_visita', sa.Boolean(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=True),
    sa.Column('produto_id', sa.Integer(), nullable=True),
    sa.Column('canal', sa.Enum('instagram', 'qrcode', 'campanha_outros', 'busca', 'outros_sites', 'direto', name='canal_aquisicao'), nullable=False),
    sa.Column('utm_source', sa.String(length=100), nullable=True),
    sa.Column('utm_medium', sa.String(length=100), nullable=True),
    sa.Column('utm_campaign', sa.String(length=100), nullable=True),
    sa.Column('referrer_host', sa.String(length=255), nullable=True),
    sa.Column('ocorrido_em', sa.DateTime(), nullable=False),
    sa.Column('versao_coleta', sa.SmallInteger(), nullable=False),
    sa.ForeignKeyConstraint(['produto_id'], ['produtos.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_eventos_analytics_ocorrido_em', 'eventos_analytics', ['ocorrido_em'], unique=False)
    op.create_index('ix_eventos_analytics_tipo_ocorrido_em', 'eventos_analytics', ['tipo', 'ocorrido_em'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_eventos_analytics_tipo_ocorrido_em', table_name='eventos_analytics')
    op.drop_index('ix_eventos_analytics_ocorrido_em', table_name='eventos_analytics')
    op.drop_table('eventos_analytics')
    sa.Enum(name='canal_aquisicao').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='tipo_evento_analytics').drop(op.get_bind(), checkfirst=True)
