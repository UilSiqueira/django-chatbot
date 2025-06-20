FROM python:3.10-slim

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala Poetry
ENV POETRY_VERSION=1.8.2
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Define o diretório de trabalho
WORKDIR /app

# Copia arquivos do Poetry
COPY pyproject.toml poetry.lock* /app/

# Instala dependências
RUN poetry config virtualenvs.create false \
    && poetry install --no-root --no-interaction --no-ansi

# Copia restante da aplicação
COPY . /app

# Expõe a porta
EXPOSE 8000