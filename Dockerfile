FROM python:3.14-slim

# Dedicated non-root user — the app never needs root at runtime.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY requirements.txt .
# The lock is fully hash-pinned (pip-compile --generate-hashes): every package,
# including transitives, must match a known hash, and no sdist setup.py runs.
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.txt

COPY src ./src

ENV PYTHONPATH=/app/src
WORKDIR /app/src
USER appuser

EXPOSE 8080
# 0.0.0.0 is deliberate here: inside the container only mapped ports are reachable.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
