FROM python:3.14-slim

WORKDIR /app

RUN pip install --no-cache-dir --root-user-action=ignore poetry==2.1.2

COPY pyproject.toml poetry.lock README.md ./

RUN poetry config virtualenvs.create false && poetry install --without dev --no-root --no-interaction --no-ansi

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
