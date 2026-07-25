# AI API Builder — dev tasks

VENV = venv
BIN = $(VENV)/Scripts
PYTHON = python

.PHONY: install run test lock

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade -r requirements.in

run:
	cd src && ../$(BIN)/uvicorn server:app --reload --port 8080

test:
	$(BIN)/pytest

# Regenerate the hash-locked requirements.txt from requirements.in.
# Runs inside python:3.12-slim so the lock matches the Docker/CI environment.
lock:
	docker run --rm -v "$(CURDIR):/work" -w /work python:3.12-slim \
		sh -c "pip install --quiet pip-tools && pip-compile --generate-hashes --output-file=requirements.txt requirements.in"
