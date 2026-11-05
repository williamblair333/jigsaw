# List recipes
default:
    @just --list

# Install dependencies
setup:
    uv sync

# Run the test suite
test *args:
    uv run pytest -q {{args}}

# Run a consumer's tests (default: Parley) against this checkout; do this before every tag
contract *consumer:
    bash scripts/contract-test.sh {{consumer}}
