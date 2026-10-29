# SAHPRA API

> **Note — M5 implementation:** This file describes the original Express/SQLite scaffold (port 3000, `/items` CRUD). The active M5 QA-RAG backend is a FastAPI service in `backend/` (port 8000). For the M5 architecture, agents, and endpoints see [README-M5.md](README-M5.md).

A simple Express API with SQLite persistence for managing catalog items. The service exposes CRUD endpoints and is ready for local development.

## Features

- Express REST API
- SQLite database persistence
- CRUD endpoints for `/items`
- Automated tests with Node's built-in test runner

## Getting started

1. Install dependencies:
   npm install
2. Start the API:
   npm start
3. Run tests:
   npm test

## API endpoints

- `GET /health` - returns service health data
- `GET /items` - lists all items
- `POST /items` - creates a new item
- `GET /items/:id` - fetches one item
- `PUT /items/:id` - updates an item
- `DELETE /items/:id` - deletes an item

Example request:

```bash
curl -X POST http://localhost:3000/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Sample item","description":"Example"}'
```
