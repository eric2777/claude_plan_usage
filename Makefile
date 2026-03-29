PLUGIN_DIR := $(HOME)/Library/Application Support/SwiftBar/Plugins

install:
	cp claude-usage.60s.py "$(PLUGIN_DIR)/claude-usage.60s.py"

test:
	python3 -m pytest tests/

run:
	python3 claude-usage.60s.py

.PHONY: install test run
