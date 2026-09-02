"""seed dados iniciais

Revision ID: 1f32fc4f41bc
Revises: fb5f8f3b1303
Create Date: 2026-05-14 02:14:20.386419

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f32fc4f41bc'
down_revision = 'fb5f8f3b1303'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Enderecos
    conn.execute(sa.text("""
        INSERT INTO enderecos (cep, logradouro, numero, bairro, cidade, estado) VALUES
            ('58013000', 'Av. Epitacio Pessoa', '1000', 'Bairro dos Estados', 'Joao Pessoa', 'PB'),
            ('58040000', 'Rua das Trincheiras', '250', 'Trincheiras', 'Joao Pessoa', 'PB')
        ON CONFLICT DO NOTHING
    """))

    # Unidades
    res = conn.execute(sa.text("SELECT id FROM enderecos ORDER BY id LIMIT 2"))
    endereco_ids = [row[0] for row in res]
    conn.execute(sa.text("""
        INSERT INTO unidades (nome, abertura, fechamento, descricao, endereco_id) VALUES
            ('Unidade Centro',     '11:00', '23:00', 'Unidade principal no centro da cidade', :e1),
            ('Unidade Epitacio',   '11:00', '22:00', 'Unidade na orla de Joao Pessoa',        :e2)
        ON CONFLICT DO NOTHING
    """), {"e1": endereco_ids[0], "e2": endereco_ids[1]})

    # Usuarios (senha = "admin123" em texto plano — trocar por hash em producao)
    conn.execute(sa.text("""
        INSERT INTO usuarios (nome, email, senha, funcao, unidade_id) VALUES
            ('Administrador', 'admin@paraibahd.com', 'admin123', 'administrador', NULL),
            ('Caixa Central', 'caixa@paraibahd.com', 'caixa123', 'caixa',         1)
        ON CONFLICT (email) DO NOTHING
    """))

    # Categorias
    conn.execute(sa.text("""
        INSERT INTO categorias (nome) VALUES
            ('Lanches'),
            ('Bebidas'),
            ('Sobremesas')
        ON CONFLICT DO NOTHING
    """))

    # Subcategorias
    res = conn.execute(sa.text("SELECT id, nome FROM categorias ORDER BY id"))
    cat = {row[1]: row[0] for row in res}
    conn.execute(sa.text("""
        INSERT INTO subcategorias (nome, categoria_id) VALUES
            ('Hot Dogs',      :lanches),
            ('Hambúrgueres',  :lanches),
            ('Refrigerantes', :bebidas),
            ('Sucos',         :bebidas),
            ('Sorvetes',      :sobremesas)
        ON CONFLICT DO NOTHING
    """), {"lanches": cat["Lanches"], "bebidas": cat["Bebidas"], "sobremesas": cat["Sobremesas"]})

    # Produtos
    res = conn.execute(sa.text("SELECT id, nome FROM subcategorias ORDER BY id"))
    sub = {row[1]: row[0] for row in res}
    conn.execute(sa.text("""
        INSERT INTO produtos (nome, descricao, ativo, subcategoria_id) VALUES
            ('Hot Dog Tradicional',  'Salsicha, molho e mostarda',          true, :hd),
            ('Hot Dog Especial',     'Salsicha dupla com catupiry',          true, :hd),
            ('Hamburguer Classico',  'Carne, queijo, alface e tomate',       true, :hb),
            ('Coca-Cola 350ml',      'Lata gelada',                          true, :ref),
            ('Suco de Laranja',      'Suco natural 300ml',                   true, :suco),
            ('Sorvete 2 Bolas',      'Escolha 2 sabores',                    true, :sor)
        ON CONFLICT DO NOTHING
    """), {
        "hd": sub["Hot Dogs"], "hb": sub["Hambúrgueres"],
        "ref": sub["Refrigerantes"], "suco": sub["Sucos"], "sor": sub["Sorvetes"]
    })

    # Clientes
    conn.execute(sa.text("""
        INSERT INTO clientes (nome, telefone, email, pontos_fidelidade, data_cadastro) VALUES
            ('Joao Silva',   '83999990001', 'joao@email.com',  10, '2026-01-10'),
            ('Maria Santos', '83999990002', 'maria@email.com',  5, '2026-02-15')
        ON CONFLICT DO NOTHING
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM clientes WHERE email IN ('joao@email.com', 'maria@email.com')"))
    conn.execute(sa.text("DELETE FROM produtos WHERE nome IN ('Hot Dog Tradicional','Hot Dog Especial','Hamburguer Classico','Coca-Cola 350ml','Suco de Laranja','Sorvete 2 Bolas')"))
    conn.execute(sa.text("DELETE FROM subcategorias WHERE nome IN ('Hot Dogs','Hambúrgueres','Refrigerantes','Sucos','Sorvetes')"))
    conn.execute(sa.text("DELETE FROM categorias WHERE nome IN ('Lanches','Bebidas','Sobremesas')"))
    conn.execute(sa.text("DELETE FROM usuarios WHERE email IN ('admin@paraibahd.com', 'caixa@paraibahd.com')"))
    conn.execute(sa.text("DELETE FROM unidades WHERE nome IN ('Unidade Centro','Unidade Epitacio')"))
    conn.execute(sa.text("DELETE FROM enderecos WHERE logradouro IN ('Av. Epitacio Pessoa','Rua das Trincheiras')"))