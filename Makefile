# ==============================================================================
# Incubrix Engine Makefile
# ==============================================================================

PYTHON ?= python

.PHONY: help run test install clean lint serve

help:
	@echo "Incubrix Engine Commands:"
	@echo "  make serve              Start web studio and command center at http://localhost:8000"
	@echo "  make run INPUT=<file>   Run pipeline on the specified input file"
	@echo "  make test               Run automated test suite"
	@echo "  make install            Install project dependencies"
	@echo "  make clean              Remove temporary artifacts and bytecode"

serve:
	$(PYTHON) server.py --port 8000

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	@if [ -z "$(INPUT)" ]; then \
		echo "ERROR: INPUT parameter is required. Example: make run INPUT=data/inputs/sample_input.txt"; \
		exit 1; \
	fi
	$(PYTHON) -m src.main --input $(INPUT)

test:
	$(PYTHON) -m pytest -v tests/

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('.pytest_cache')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in [pathlib.Path('data/outputs/temp_thumbs'), pathlib.Path('data/outputs/temp_videos')]]"
