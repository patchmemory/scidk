# Convenience Makefile for docs/tools

.PHONY: flags-index docs-check

flags-index:
	python -m dev.tools.feature_flags_index --write

# docs-check: run generator and diff; non-zero exit if mismatched
# Note: this target assumes Unix tools (diff)
docs-check:
	python -m dev.tools.feature_flags_index > /tmp/feature-flags.md
	diff -q /tmp/feature-flags.md dev/features/feature-flags.md
