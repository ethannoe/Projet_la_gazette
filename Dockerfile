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
COPY sources.csv ./
COPY tests ./tests
CMD ["sh", "-c", "ruff check src tests && pytest -p no:cacheprovider"]

# --- 3. runtime : image finale, juste Python + le venv, utilisateur non root ---
FROM python:${PYTHON_VERSION}-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    GAZETTE_RAW_DIR=/data/raw
RUN groupadd --gid 10001 gazette \
 && useradd --uid 10001 --gid gazette --no-create-home --shell /usr/sbin/nologin gazette \
 && mkdir /data && chown gazette:gazette /data
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY sources.csv ./
USER gazette
ENTRYPOINT ["python", "-m", "gazette.collect"]
CMD ["--source", "lemonde"]
