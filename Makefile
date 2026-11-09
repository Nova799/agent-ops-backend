.PHONY: test run docker

test:
	python -m pytest tests -W error -q

run:
	uvicorn main:app --reload --port 8001

docker:
	docker compose up --build -d