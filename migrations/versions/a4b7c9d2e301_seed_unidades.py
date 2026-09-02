"""seed unidades

Revision ID: a4b7c9d2e301
Revises: 7e2a9c4d6f10
Create Date: 2026-05-23 14:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a4b7c9d2e301"
down_revision = "7e2a9c4d6f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    unidades = [
        {
            "nome": "Unidade Asa Sul",
            "cep": "70390025",
            "logradouro": "CLS 308",
            "numero": "12",
            "complemento": "Loja 4",
            "bairro": "Asa Sul",
            "cidade": "Brasilia",
            "estado": "DF",
            "abertura": "11:00",
            "fechamento": "23:00",
            "descricao": "Unidade de atendimento na Asa Sul",
        },
        {
            "nome": "Unidade Aguas Claras",
            "cep": "71900000",
            "logradouro": "Avenida das Castanheiras",
            "numero": "500",
            "complemento": "Quiosque 2",
            "bairro": "Aguas Claras",
            "cidade": "Brasilia",
            "estado": "DF",
            "abertura": "11:00",
            "fechamento": "23:00",
            "descricao": "Unidade de atendimento em Aguas Claras",
        },
        {
            "nome": "Unidade Taguatinga",
            "cep": "72010010",
            "logradouro": "Avenida Comercial Norte",
            "numero": "150",
            "complemento": None,
            "bairro": "Taguatinga Norte",
            "cidade": "Brasilia",
            "estado": "DF",
            "abertura": "10:30",
            "fechamento": "22:30",
            "descricao": "Unidade de atendimento em Taguatinga",
        },
    ]

    for unidade in unidades:
        exists = conn.execute(
            sa.text("SELECT 1 FROM unidades WHERE nome = :nome"),
            {"nome": unidade["nome"]},
        ).first()
        if exists:
            continue

        endereco_id = conn.execute(
            sa.text(
                """
                INSERT INTO enderecos
                    (cep, logradouro, numero, complemento, bairro, cidade, estado)
                VALUES
                    (:cep, :logradouro, :numero, :complemento, :bairro, :cidade, :estado)
                RETURNING id
                """
            ),
            unidade,
        ).scalar_one()

        conn.execute(
            sa.text(
                """
                INSERT INTO unidades
                    (nome, abertura, fechamento, descricao, endereco_id)
                VALUES
                    (:nome, :abertura, :fechamento, :descricao, :endereco_id)
                """
            ),
            {**unidade, "endereco_id": endereco_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    nomes = ["Unidade Asa Sul", "Unidade Aguas Claras", "Unidade Taguatinga"]
    endereco_ids = [
        row[0]
        for row in conn.execute(
            sa.text("SELECT endereco_id FROM unidades WHERE nome = ANY(:nomes)"),
            {"nomes": nomes},
        )
    ]
    conn.execute(sa.text("DELETE FROM unidades WHERE nome = ANY(:nomes)"), {"nomes": nomes})
    if endereco_ids:
        conn.execute(sa.text("DELETE FROM enderecos WHERE id = ANY(:ids)"), {"ids": endereco_ids})
