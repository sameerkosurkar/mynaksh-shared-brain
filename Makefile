.PHONY: up down logs install run test demo eval clean

up:        ## build & start Neo4j + API (http://localhost:8000/docs)
	docker compose up --build -d
	@echo "API: http://localhost:8000/docs   Neo4j: http://localhost:7474 (neo4j / mynaksh-dev-password)"

down:
	docker compose down

logs:
	docker compose logs -f app

install:   ## local virtualenv
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

run:       ## run API locally (Neo4j from `docker compose up -d neo4j`, or GRAPH_BACKEND=memory)
	.venv/bin/uvicorn app.main:app --reload --port 8000

test:
	.venv/bin/pytest -q

demo:
	./scripts/demo.sh

eval:
	.venv/bin/python -m eval.memory_eval

clean:
	docker compose down -v
