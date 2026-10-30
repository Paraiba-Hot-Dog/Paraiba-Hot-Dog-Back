# Paraiba Hot Dog — Backend

API REST do sistema de gerenciamento de vendas e pedidos da rede de lanchonetes **Paraiba Hot Dog**.

## Sobre o Projeto

Projeto desenvolvido para a disciplina **Técnicas de Programação em Plataformas Emergentes** sob orientação do Professor **Thiago Luiz de Souza Gomes**.

- **Cliente**: Paraiba Hot Dog (loja de cachorro-quente em Brasília)
- **Período**: 2026
- **Stack**: Python 3.12+ · FastAPI · SQLAlchemy · PostgreSQL · Alembic · Docker

## Membros do Grupo

<table>
  <tr>
    <td align="center">
      <img src="https://github.com/camilascareli.png" width="100px"><br>
      <small><strong>Camila Careli</strong><br>221007582</small>
    </td>
    <td align="center">
      <img src="https://github.com/DanielFsR.png" width="100px"><br>
      <small><strong>Daniel Ferreira</strong><br>222006632</small>
    </td>
    <td align="center">
      <img src="https://github.com/Mach1r0.png" width="100px"><br>
      <small><strong>Daniel Nunes</strong><br>211061565</small>
    </td>
    <td align="center">
      <img src="https://github.com/guilermanoo.png" width="100px"><br>
      <small><strong>Guilherme Coelho</strong><br>202016364</small>
    </td>
    <td align="center">
      <img src="https://github.com/jmarquees.png" width="100px"><br>
      <small><strong>João Victor</strong><br>200058576</small>
    </td>
    <td align="center">
      <img src="https://github.com/magnluiz.png" width="100px"><br>
      <small><strong>Magno Luiz</strong><br>180042696</small>
    </td>
    <td align="center">
      <img src="https://github.com/SamuelRicosta.png" width="100px"><br>
      <small><strong>Samuel Ribeiro</strong><br>211031486</small>
    </td>
  </tr>
</table>

---

## Como Executar

### Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) e [Docker Compose](https://docs.docker.com/compose/)
- **ou** Python 3.12+ e [Poetry](https://python-poetry.org/) (para desenvolvimento local)

### Opção 1: Docker (Recomendado)

O Docker Compose sobe o backend e o PostgreSQL automaticamente, aplicando as migrações na inicialização.

```bash
# 1. Clonar o repositório
git clone https://github.com/TPPE-GP-09/Paraiba-Hot-Dog-Back.git
cd Paraiba-Hot-Dog-Back

# 2. Subir os serviços
docker-compose up -d

# 3. Acompanhar os logs
docker-compose logs -f
```

Serviços disponíveis após subir:

| Serviço | URL |
|---------|-----|
| API | http://localhost:8000 |
| Documentação Swagger | http://localhost:8000/docs |
| Documentação Redoc | http://localhost:8000/redoc |
| PostgreSQL | localhost:5432 |

Para parar os serviços:

```bash
docker-compose down
```

Para parar e remover os volumes (apaga o banco):

```bash
docker-compose down -v
```

---

### Opção 2: Desenvolvimento Local

#### 1. Configurar o banco de dados

Certifique-se de ter um PostgreSQL rodando e configure o `.env`:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=paraiba_hotdog_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

#### 2. Instalar dependências com Poetry

```bash
# Instalar Poetry (caso não tenha)
pip install poetry

# Instalar dependências do projeto
poetry install

# Ativar o ambiente virtual
poetry shell
```

#### 3. Aplicar as migrações

```bash
alembic upgrade head
```

#### 4. Iniciar o servidor

```bash
uvicorn app.main:app --reload --port 8000
```

---

## Migrações com Alembic

As migrações ficam em `migrations/versions/`. O Alembic gerencia o schema do banco de forma versionada.

### Comandos essenciais

```bash
# Aplicar todas as migrações pendentes
alembic upgrade head

# Reverter a última migração
alembic downgrade -1

# Reverter todas as migrações
alembic downgrade base

# Ver o histórico de migrações
alembic history --verbose

# Ver a revisão atual do banco
alembic current
```

### Criar uma nova migração

Após alterar ou criar um model em `app/models/`, gere a migração:

```bash
# Geração automática (compara models com o banco)
alembic revision --autogenerate -m "descricao_da_migracao"

# Criação manual (arquivo vazio para edição manual)
alembic revision -m "descricao_da_migracao"
```

> **Atenção:** sempre revise o arquivo gerado antes de aplicar. O autogenerate pode não detectar todas as mudanças (ex.: tipos ENUM, renomeações).

### Nomenclatura

Siga o padrão já adotado no projeto:

```
migrations/versions/
├── 0001_create_users_table.py
├── 0002_create_tables.py
└── NNNN_descricao_curta.py
```

---

## Estrutura do Projeto

```
Paraiba-Hot-Dog-Back/
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── routers/        # Endpoints da API (usuarios, produtos...)
│   ├── core/
│   │   └── database.py         # Configuração do SQLAlchemy
│   ├── models/                 # Models ORM (SQLAlchemy)
│   ├── schemas/                # Schemas Pydantic (validação/serialização)
│   └── main.py                 # Entrypoint FastAPI
├── migrations/
│   ├── versions/               # Arquivos de migração Alembic
│   └── env.py                  # Configuração do Alembic
├── Docker/
│   └── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml
└── .env
```

---

## Tecnologias

| Camada | Tecnologia |
|--------|-----------|
| API | Python 3.12, FastAPI |
| ORM | SQLAlchemy 2.0 |
| Migrações | Alembic |
| Banco de Dados | PostgreSQL |
| Validação | Pydantic v2 |
| Gerenciador de pacotes | Poetry |
| Infraestrutura | Docker, Docker Compose |
| Testes | Pytest, HTTPX |

---

## Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `POSTGRES_USER` | Usuário do PostgreSQL | `postgres` |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL | `postgres` |
| `POSTGRES_DB` | Nome do banco de dados | `paraiba_hotdog_db` |
| `POSTGRES_HOST` | Host do banco | `localhost` |
| `POSTGRES_PORT` | Porta do banco | `5432` |

> No Docker Compose, `POSTGRES_HOST` é sobrescrito automaticamente para `postgres` (nome do serviço).


## Protótipo iFood (somente testes)

O painel **Pedidos** (`/admin/pedidos`) reúne comandas e pedidos iFood de teste.
A integração é desativada por padrão. Configure `IFOOD_ENABLED`, `IFOOD_CLIENT_ID`,
`IFOOD_CLIENT_SECRET` e `IFOOD_TEST_MERCHANTS` conforme `.env.example`, usando apenas
lojas de teste e um banco local. Execute as migrações antes de iniciar a API.

```bash
docker compose --profile ifood-testes up --build
# Ou, com API/banco já disponíveis:
python -m src.ifood.worker
```

Guia completo e roteiro de validação: repositório Paraiba-Hot-Dog-Docs,
`docs/desenvolvimento/ifood.md`. A homologação, a conta profissional e a verificação
de coexistência com o Gestor de Pedidos real continuam pendentes.

Testes simulados (sem credenciais e sem chamar serviços externos):

```bash
python -m pytest src/ifood/test_ifood.py src/pedidos src/bi/test_bi_integracao.py -q
```
