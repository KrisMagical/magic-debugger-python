# Magic Debug Makefile

.PHONY: all install test clean run check check-gdb doctor debug format lint build build-test help

all: check install

check:
	@echo "Checking Python version..."
	@python3 --version
	@echo "Checking Python imports..."
	@python3 -c "from adapters.gdb import *"
	@python3 -c "import main"
	@$(MAKE) test
	@python3 -c "import subprocess, sys; r = subprocess.run([sys.executable, 'main.py', '--check', '--json']); sys.exit(0 if r.returncode in (0, 1) else r.returncode)"

check-gdb:
	@python3 main.py doctor || test $$? -eq 1

doctor:
	@python3 main.py doctor || test $$? -eq 1

install:
	pip install -e .

test:
	pytest tests/ -q

run:
	python3 main.py

debug:
	python3 main.py --verbose

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +

format:
	black .
	isort .

lint:
	mypy .

build:
	python3 -m build

build-test:
	gcc -g -o tests/test_sample tests/test_sample.c

help:
	@echo "Magic Debug Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make check      - Run import checks and pytest"
	@echo "  make check-gdb  - Check GDB availability"
	@echo "  make doctor     - Run diagnostics"
	@echo "  make install    - Install the package"
	@echo "  make test       - Run tests"
	@echo "  make run        - Run the server"
	@echo "  make debug      - Run with verbose logging"
	@echo "  make clean      - Clean build artifacts"
	@echo "  make format     - Format code"
	@echo "  make lint       - Run type checker"
	@echo "  make build      - Build distribution package"
	@echo "  make build-test - Build test program"
