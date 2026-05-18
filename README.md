# Simple FastAPI App

Quick start for the tiny FastAPI app in this folder.

Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Endpoints

- `GET /` -> greeting
- `GET /health` -> health check
- `GET /items/{item_id}` -> fetch an item
- `POST /items/` -> create an item (JSON body with `id`, `name`, optional `description`)

Example

```bash
curl -X POST "http://127.0.0.1:8000/items/" -H "Content-Type: application/json" -d '{"id":1,"name":"Test"}'
curl http://127.0.0.1:8000/items/1
```
