"""create grupos opcoes e complementos and drop legacy produto_adicionais

Revision ID: f2a4b6c8d0e1
Revises: e5f8a2b4c7d9
Create Date: 2026-11-05
"""

from alembic import op
import sqlalchemy as sa
from decimal import Decimal


revision = "f2a4b6c8d0e1"
down_revision = "28bff5923890"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Cria tabela grupos_opcoes
    op.create_table(
        "grupos_opcoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("obrigatorio", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("minimo", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("maximo", sa.Integer(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. Cria tabela opcoes_complemento
    op.create_table(
        "opcoes_complemento",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grupo_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("preco", sa.Numeric(precision=10, scale=2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["grupo_id"], ["grupos_opcoes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 3. Cria tabela associativa produto_grupos_opcoes
    op.create_table(
        "produto_grupos_opcoes",
        sa.Column("produto_id", sa.Integer(), nullable=False),
        sa.Column("grupo_id", sa.Integer(), nullable=False),
        sa.Column("ordem", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(["grupo_id"], ["grupos_opcoes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["produto_id"], ["produtos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("produto_id", "grupo_id"),
    )

    # 4. Semeia os grupos iniciais padrão
    conn = op.get_bind()

    # Grupo 1: Maionese (sem limite min/max)
    conn.execute(
        sa.text(
            "INSERT INTO grupos_opcoes (id, nome, obrigatorio, minimo, maximo, ativo) "
            "VALUES (1, 'Escolha a maionese', false, 0, NULL, true)"
        )
    )
    maioneses = ["Tradicional", "Alho", "Ervas", "Bacon", "Apimentada"]
    for nome in maioneses:
        conn.execute(
            sa.text(
                "INSERT INTO opcoes_complemento (grupo_id, nome, preco, ativo) "
                "VALUES (1, :nome, 0.00, true)"
            ),
            {"nome": nome},
        )

    # Grupo 2: Retirar ingredientes (sem limite min/max)
    conn.execute(
        sa.text(
            "INSERT INTO grupos_opcoes (id, nome, obrigatorio, minimo, maximo, ativo) "
            "VALUES (2, 'Retirar ingredientes', false, 0, NULL, true)"
        )
    )
    remocoes = [
        "Sem cebola",
        "Sem milho",
        "Sem queijo",
        "Sem vinagrete",
        "Sem batata palha",
        "Sem tomate",
        "Sem salada",
        "Sem ovo de codorna",
    ]
    for nome in remocoes:
        conn.execute(
            sa.text(
                "INSERT INTO opcoes_complemento (grupo_id, nome, preco, ativo) "
                "VALUES (2, :nome, 0.00, true)"
            ),
            {"nome": nome},
        )

    # Grupo 3: Adicionais
    conn.execute(
        sa.text(
            "INSERT INTO grupos_opcoes (id, nome, obrigatorio, minimo, maximo, ativo) "
            "VALUES (3, 'Adicionais', false, 0, NULL, true)"
        )
    )
    adicionais = [
        ("Bacon em tiras", Decimal("5.00")),
        ("Queijo muçarela extra", Decimal("4.00")),
        ("Hambúrguer artesanal 120g", Decimal("10.00")),
        ("Salsicha extra", Decimal("4.00")),
        ("Carne moída temperada", Decimal("5.00")),
    ]
    for nome, preco in adicionais:
        conn.execute(
            sa.text(
                "INSERT INTO opcoes_complemento (grupo_id, nome, preco, ativo) "
                "VALUES (3, :nome, :preco, true)"
            ),
            {"nome": nome, "preco": preco},
        )

    # Migra dados existentes de produto_adicionais para opcoes_complemento se houver
    try:
        linhas = conn.execute(sa.text("SELECT id, nome, preco, produto_id FROM produto_adicionais")).fetchall()
        for linha in linhas:
            conn.execute(
                sa.text(
                    "INSERT INTO opcoes_complemento (grupo_id, nome, preco, ativo) "
                    "VALUES (3, :nome, :preco, true)"
                ),
                {"nome": linha[1], "preco": linha[2]},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO produto_grupos_opcoes (produto_id, grupo_id, ordem) "
                    "VALUES (:prod_id, 3, 2) ON CONFLICT DO NOTHING"
                ),
                {"prod_id": linha[3]},
            )
    except Exception:
        pass

    # Vincula todos os lanches existentes aos 3 grupos
    try:
        produtos = conn.execute(sa.text("SELECT id FROM produtos")).fetchall()
        for prod in produtos:
            prod_id = prod[0]
            conn.execute(
                sa.text(
                    "INSERT INTO produto_grupos_opcoes (produto_id, grupo_id, ordem) "
                    "VALUES (:prod_id, 1, 1), (:prod_id, 3, 2), (:prod_id, 2, 3) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"prod_id": prod_id},
            )
    except Exception:
        pass

    # Remove FK da tabela item_pedido_adicionais e vincula a opcoes_complemento
    try:
        op.drop_constraint("item_pedido_adicionais_adicional_id_fkey", "item_pedido_adicionais", type_="foreignkey")
    except Exception:
        pass

    try:
        op.create_foreign_key(
            "item_pedido_adicionais_adicional_id_fkey",
            "item_pedido_adicionais",
            "opcoes_complemento",
            ["adicional_id"],
            ["id"],
            ondelete="SET NULL",
        )
    except Exception:
        pass

    # Dropa a tabela legada produto_adicionais
    try:
        op.drop_table("produto_adicionais")
    except Exception:
        pass


def downgrade() -> None:
    # Recria tabela legada se necessário
    op.create_table(
        "produto_adicionais",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("preco", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("produto_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["produto_id"], ["produtos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    try:
        op.drop_constraint("item_pedido_adicionais_adicional_id_fkey", "item_pedido_adicionais", type_="foreignkey")
        op.create_foreign_key(
            "item_pedido_adicionais_adicional_id_fkey",
            "item_pedido_adicionais",
            "produto_adicionais",
            ["adicional_id"],
            ["id"],
        )
    except Exception:
        pass

    op.drop_table("produto_grupos_opcoes")
    op.drop_table("opcoes_complemento")
    op.drop_table("grupos_opcoes")
