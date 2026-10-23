const express = require('express');
const { all, get, run } = require('./db');

const app = express();

app.use(express.json());

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.get('/items', async (req, res, next) => {
  try {
    const items = await all('SELECT * FROM items ORDER BY created_at DESC');
    res.json(items);
  } catch (error) {
    next(error);
  }
});

app.get('/items/:id', async (req, res, next) => {
  try {
    const item = await get('SELECT * FROM items WHERE id = ?', [req.params.id]);

    if (!item) {
      return res.status(404).json({ message: 'Item not found' });
    }

    return res.json(item);
  } catch (error) {
    return next(error);
  }
});

app.post('/items', async (req, res, next) => {
  try {
    const name = typeof req.body?.name === 'string' ? req.body.name.trim() : '';
    const description = typeof req.body?.description === 'string' ? req.body.description.trim() : '';

    if (!name) {
      return res.status(400).json({ message: 'Name is required' });
    }

    const result = await run(
      'INSERT INTO items (name, description, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)',
      [name, description]
    );

    const createdItem = await get('SELECT * FROM items WHERE id = ?', [result.lastID]);

    return res.status(201).json(createdItem);
  } catch (error) {
    return next(error);
  }
});

app.put('/items/:id', async (req, res, next) => {
  try {
    const itemId = req.params.id;
    const existingItem = await get('SELECT * FROM items WHERE id = ?', [itemId]);

    if (!existingItem) {
      return res.status(404).json({ message: 'Item not found' });
    }

    const name = typeof req.body?.name === 'string' ? req.body.name.trim() : existingItem.name;
    const description = typeof req.body?.description === 'string' ? req.body.description.trim() : existingItem.description;

    if (!name) {
      return res.status(400).json({ message: 'Name is required' });
    }

    await run(
      'UPDATE items SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
      [name, description, itemId]
    );

    const updatedItem = await get('SELECT * FROM items WHERE id = ?', [itemId]);
    return res.json(updatedItem);
  } catch (error) {
    return next(error);
  }
});

app.delete('/items/:id', async (req, res, next) => {
  try {
    const item = await get('SELECT * FROM items WHERE id = ?', [req.params.id]);

    if (!item) {
      return res.status(404).json({ message: 'Item not found' });
    }

    await run('DELETE FROM items WHERE id = ?', [req.params.id]);
    return res.json({ message: 'Item deleted', id: Number(req.params.id) });
  } catch (error) {
    return next(error);
  }
});

app.use((error, req, res, next) => {
  console.error(error);
  res.status(500).json({ message: 'Internal server error' });
});

module.exports = app;
