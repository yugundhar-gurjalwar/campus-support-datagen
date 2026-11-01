PY ?= python3
export PYTHONPATH := src

.PHONY: all test docs starter full repro clean

all: docs starter full repro test

test:
	$(PY) -m pytest -q

docs:
	$(PY) -m campus_support docs --dir docs

starter:
	$(PY) -m campus_support generate --tickets 250 --articles 40 --out data/starter

full:
	$(PY) -m campus_support generate --out data/full

repro:
	$(PY) -m campus_support repro-check --data data/full
	$(PY) -m campus_support repro-check --tickets 250 --articles 40 --data data/starter

clean:
	rm -rf data/full data/starter .pytest_cache
