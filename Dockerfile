# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

# --- 1. builder : installe l'application et ses dépendances dans un venv ---
FROM python:${PYTHON_VERSION}-slim AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

# --- 2. test : builder + outils de dev ; utilisé par bin/test ---
FROM builder AS test
RUN pip install ".[dev]"
ENV HF_HOME=/tmp/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1
COPY sources.csv regles.toml ./
COPY config ./config
COPY tests ./tests
CMD ["sh", "-c", "ruff check --no-cache src tests && pytest -p no:cacheprovider"]

# --- 3. runtime : image finale, juste Python + le venv, utilisateur non root ---
FROM python:${PYTHON_VERSION}-slim AS runtime
# Le commit d'où vient l'image : tracé dans chaque run de regroupement (table runs)
ARG GIT_SHA=dev
ENV GAZETTE_CODE_VERSION=${GIT_SHA}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    GAZETTE_ARTICLES_DIR=/data/articles_bruts \
    GAZETTE_SOURCES_FILE=/app/sources.csv \
    GAZETTE_REGLES_FILE=/app/regles.toml \
    GAZETTE_RAPPORTS_DIR=/data/rapports \
    GAZETTE_CLUSTERING_FILE=/app/config/clustering.yaml \
    GAZETTE_MODELES_DIR=/data/modeles \
    GAZETTE_RUNS_DIR=/data/runs \
    HF_HOME=/tmp/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PREFECT_HOME=/tmp/prefect
RUN groupadd --gid 10001 gazette \
 && useradd --uid 10001 --gid gazette --no-create-home --shell /usr/sbin/nologin gazette \
 && mkdir -p /data/articles_bruts /data/rapports /data/modeles /data/runs \
 && chown -R gazette:gazette /data
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY sources.csv regles.toml ./
COPY config ./config
USER gazette
ENTRYPOINT ["python", "-m", "gazette"]
CMD ["planifier"]
