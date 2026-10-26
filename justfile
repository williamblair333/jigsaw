# List recipes
default:
    @just --list

# Install dependencies
setup:
    uv sync

# Run the test suite
test *args:
    uv run pytest -q {{args}}
