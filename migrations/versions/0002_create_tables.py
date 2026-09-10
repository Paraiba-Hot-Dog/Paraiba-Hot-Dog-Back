"""create tables

Revision ID: 0002_create_tables
Revises: 0001_create_users_table
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_create_tables"
down_revision = "0001_create_users_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tipo_permissao enum
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE tipo_permissao AS ENUM ('anotar_pedidos', 'cozinha', 'dashboard', 'configuracoes');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )

    # Create funcao_usuario enum
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE funcao_usuario AS ENUM ('administrador', 'caixa', 'cozinha');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )

    # Create permissoes table
    op.create_table(
        "permissoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", postgresql.ENUM('anotar_pedidos', 'cozinha', 'dashboard', 'configuracoes', name='tipo_permissao', create_type=False), nullable=False, unique=True),
    )
    op.create_index(op.f("ix_permissoes_id"), "permissoes", ["id"])

    # Create enderecos table
    op.create_table(
        "enderecos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cep", sa.String(8), nullable=False),
        sa.Column("logradouro", sa.String(255), nullable=False),
        sa.Column("numero", sa.String(10), nullable=True),
        sa.Column("complemento", sa.String(255), nullable=True),
        sa.Column("bairro", sa.String(255), nullable=False),
        sa.Column("cidade", sa.String(255), nullable=False),
        sa.Column("estado", sa.String(2), nullable=False),
    )
    op.create_index(op.f("ix_enderecos_id"), "enderecos", ["id"])

    # Create unidades table
    op.create_table(
        "unidades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("imagem", sa.String(500), nullable=True),
        sa.Column("abertura", sa.Time(), nullable=False),
        sa.Column("fechamento", sa.Time(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("endereco_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["endereco_id"], ["enderecos.id"], ),
    )
    op.create_index(op.f("ix_unidades_id"), "unidades", ["id"])

    # Create produtos table
    op.create_table(
        "produtos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(255), nullable=False, index=True),
        sa.Column("descricao", sa.String(500), nullable=True),
        sa.Column("preco", sa.Float(), nullable=False),
        sa.Column("preco_combo", sa.Float(), nullable=True),
        sa.Column("categoria", sa.String(100), nullable=False, index=True),
        sa.Column("esta_ativo", sa.Boolean(), nullable=False, server_default='true'),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("imagem", sa.String(500), nullable=True),
        sa.Column("unidade_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["unidade_id"], ["unidades.id"], ),
    )
    op.create_index(op.f("ix_produtos_id"), "produtos", ["id"])

    # Update usuarios table to add permissao_id and correct schema
    op.rename_table("users", "usuarios")
    op.add_column("usuarios", sa.Column("nome", sa.String(120), nullable=False, server_default=''))
    op.add_column("usuarios", sa.Column("funcao", postgresql.ENUM('administrador', 'caixa', 'cozinha', name='funcao_usuario', create_type=False), nullable=False, server_default='caixa'))
    op.add_column("usuarios", sa.Column("unidade_id", sa.Integer(), nullable=True))
    op.add_column("usuarios", sa.Column("permissao_id", sa.Integer(), nullable=True))
    op.drop_column("usuarios", "password")
    op.drop_column("usuarios", "role")
    op.add_column("usuarios", sa.Column("senha", sa.String(255), nullable=False, server_default=''))
    op.create_foreign_key("fk_usuarios_permissao_id", "usuarios", "permissoes", ["permissao_id"], ["id"])
    op.create_index(op.f("ix_usuarios_email"), "usuarios", ["email"], unique=True)
    op.create_index(op.f("ix_usuarios_id"), "usuarios", ["id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_usuarios_id"), table_name="usuarios")
    op.drop_index(op.f("ix_usuarios_email"), table_name="usuarios")
    op.drop_constraint("fk_usuarios_permissao_id", "usuarios", type_="foreignkey")
    op.drop_column("usuarios", "senha")
    op.drop_column("usuarios", "permissao_id")
    op.drop_column("usuarios", "unidade_id")
    op.drop_column("usuarios", "funcao")
    op.drop_column("usuarios", "nome")
    op.add_column("usuarios", sa.Column("role", postgresql.ENUM("admin", "caixa", "cozinha", name="user_role"), nullable=False))
    op.add_column("usuarios", sa.Column("password", sa.String(255), nullable=False))
    op.rename_table("usuarios", "users")
    
    op.drop_index(op.f("ix_produtos_id"), table_name="produtos")
    op.drop_table("produtos")
    
    op.drop_index(op.f("ix_unidades_id"), table_name="unidades")
    op.drop_table("unidades")
    
    op.drop_index(op.f("ix_enderecos_id"), table_name="enderecos")
    op.drop_table("enderecos")
    
    op.drop_index(op.f("ix_permissoes_id"), table_name="permissoes")
    op.drop_table("permissoes")
    
    op.execute("DROP TYPE IF EXISTS funcao_usuario")
    op.execute("DROP TYPE IF EXISTS tipo_permissao")
