.PHONY: dev test format migrate makemigrations shell

dev:
	uv run manage.py runserver


test:
	@if uv run pytest --version >/dev/null 2>&1; then \
		echo " Running tests with pytest..."; \
		uv run pytest -v; \
	else \
		echo " pytest not found, running with Django's test runner..."; \
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
