# .PHONY: dev test format migrate makemigrations shell

# dev:
# 	uv run manage.py runserver

# test:
# 	uv run manage.py test users.tests

# format:
# 	uv run black .
# 	uv run isort .

# makemigrations:
# 	uv run manage.py makemigrations

# migrate:
# 	uv run manage.py migrate

# shell:
# 	uv run manage.py shell


.PHONY: dev test format migrate makemigrations shell

dev:
	uv run manage.py runserver

# Run tests with pytest if available, otherwise fallback to Django's test runner
test:
	@if uv run pytest --version >/dev/null 2>&1; then \
		echo "✅ Running tests with pytest..."; \
		uv run pytest -v; \
	else \
		echo "⚠️  pytest not found, running with Django's test runner..."; \
		uv run manage.py test users.tests; \
	fi

format:
	uv run black .
	uv run isort .

makemigrations:
	uv run manage.py makemigrations

migrate:
	uv run manage.py migrate

shell:
	uv run manage.py shell
