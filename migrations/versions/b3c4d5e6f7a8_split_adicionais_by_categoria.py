"""split adicionais by categoria smashdogs and hotdogs

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-11-05
"""

from alembic import op
import sqlalchemy as sa
from decimal import Decimal


revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Renomeia Grupo 3 para 'Adicionais Smashdogs'
    conn.execute(
        sa.text("UPDATE grupos_opcoes SET nome = 'Adicionais Smashdogs' WHERE id = 3")
    )

    # 2. Cria Grupo 4: 'Adicionais Hotdogs' se não existir
    conn.execute(
        sa.text(
            "INSERT INTO grupos_opcoes (id, nome, obrigatorio, minimo, maximo, ativo) "
            "VALUES (4, 'Adicionais Hotdogs', false, 0, NULL, true) "
            "ON CONFLICT (id) DO UPDATE SET nome = 'Adicionais Hotdogs', ativo = true"
        )
    )

    # 3. Limpa opções antigas dos grupos 3 e 4
    conn.execute(sa.text("DELETE FROM opcoes_complemento WHERE grupo_id IN (3, 4)"))

    # 4. Insere opções de Adicionais para Smashdogs (Grupo 3)
    adicionais_smash = [
        ("Hambúrguer artesanal 120g", Decimal("10.00")),
        ("Bacon em tiras", Decimal("5.00")),
        ("Queijo muçarela extra", Decimal("4.00")),
    ]
    for nome, preco in adicionais_smash:
        conn.execute(
            sa.text(
                "INSERT INTO opcoes_complemento (grupo_id, nome, preco, ativo) "
                "VALUES (3, :nome, :preco, true)"
            ),
            {"nome": nome, "preco": preco},
        )

    # 5. Insere opções de Adicionais para Hotdogs (Grupo 4)
    adicionais_hotdog = [
        ("Salsicha extra", Decimal("4.00")),
        ("Carne moída temperada", Decimal("5.00")),
        ("Queijo muçarela extra", Decimal("4.00")),
        ("Bacon em tiras", Decimal("5.00")),
    ]
    for nome, preco in adicionais_hotdog:
        conn.execute(
            sa.text(
                "INSERT INTO opcoes_complemento (grupo_id, nome, preco, ativo) "
                "VALUES (4, :nome, :preco, true)"
            ),
            {"nome": nome, "preco": preco},
        )

    # 6. Atualiza vínculos em produto_grupos_opcoes
    # Remove vínculos de bebidas e acompanhamentos (ids 19 a 23) de todos os grupos
    conn.execute(
        sa.text("DELETE FROM produto_grupos_opcoes WHERE produto_id IN (19, 20, 21, 22, 23)")
    )

    # Remove vínculos antigos de adicionais (grupos 3 e 4) dos lanches
    conn.execute(
        sa.text("DELETE FROM produto_grupos_opcoes WHERE grupo_id IN (3, 4)")
    )

    # Vincula Smashdogs (ids 1 a 9) ao Grupo 3 (Adicionais Smashdogs)
    for prod_id in range(1, 10):
        conn.execute(
            sa.text(
                "INSERT INTO produto_grupos_opcoes (produto_id, grupo_id, ordem) "
                "VALUES (:prod_id, 3, 2) ON CONFLICT DO NOTHING"
            ),
            {"prod_id": prod_id},
        )

    # Vincula Hotdogs (ids 10 a 18) ao Grupo 4 (Adicionais Hotdogs)
    for prod_id in range(10, 19):
        conn.execute(
            sa.text(
                "INSERT INTO produto_grupos_opcoes (produto_id, grupo_id, ordem) "
                "VALUES (:prod_id, 4, 2) ON CONFLICT DO NOTHING"
            ),
            {"prod_id": prod_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM produto_grupos_opcoes WHERE grupo_id = 4"))
    conn.execute(sa.text("DELETE FROM opcoes_complemento WHERE grupo_id = 4"))
    conn.execute(sa.text("DELETE FROM grupos_opcoes WHERE id = 4"))
    conn.execute(sa.text("UPDATE grupos_opcoes SET nome = 'Acréscimos / Adicionais' WHERE id = 3"))

