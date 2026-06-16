PLUGIN_DIR := $(HOME)/swiftbar plugins

install:
	cp claude-usage.60s.py "$(PLUGIN_DIR)/claude-usage.60s.py"
	cp claude_fetch.py "$(PLUGIN_DIR)/claude_fetch.py"

test:
	python3 -m pytest tests/

run:
	python3 claude-usage.60s.py

.PHONY: install test run
