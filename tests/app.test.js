const test = require('node:test');
const assert = require('node:assert/strict');
const request = require('supertest');

const app = require('../src/app');
const { run, all, initializeDatabase } = require('../src/db');

async function resetItemsTable() {
  await run('DELETE FROM items');
}

test.before(async () => {
  await initializeDatabase();
  await resetItemsTable();
});

test.afterEach(async () => {
  await resetItemsTable();
});

test('GET /health returns service status', async () => {
  const response = await request(app).get('/health');

  assert.equal(response.status, 200);
  assert.deepEqual(response.body, { status: 'ok' });
});

test('creates, lists, updates and deletes an item', async () => {
  const createdResponse = await request(app)
    .post('/items')
    .send({ name: 'Sample item', description: 'First item' });

  assert.equal(createdResponse.status, 201);
  assert.equal(createdResponse.body.name, 'Sample item');
  assert.equal(createdResponse.body.description, 'First item');

  const listResponse = await request(app).get('/items');
  assert.equal(listResponse.status, 200);
  assert.equal(listResponse.body.length, 1);
  assert.equal(listResponse.body[0].name, 'Sample item');

  const itemId = createdResponse.body.id;

  const updateResponse = await request(app)
    .put(`/items/${itemId}`)
    .send({ name: 'Updated item', description: 'Updated description' });

  assert.equal(updateResponse.status, 200);
  assert.equal(updateResponse.body.name, 'Updated item');
  assert.equal(updateResponse.body.description, 'Updated description');

  const readResponse = await request(app).get(`/items/${itemId}`);
  assert.equal(readResponse.status, 200);
  assert.equal(readResponse.body.name, 'Updated item');

  const deleteResponse = await request(app).delete(`/items/${itemId}`);
  assert.equal(deleteResponse.status, 200);
  assert.equal(deleteResponse.body.message, 'Item deleted');

  const remainingItems = await all('SELECT * FROM items');
  assert.equal(remainingItems.length, 0);
});

test('returns 400 when creating an item without a name', async () => {
  const response = await request(app)
    .post('/items')
    .send({ description: 'Missing name' });

  assert.equal(response.status, 400);
  assert.equal(response.body.message, 'Name is required');
});

test('returns 404 when updating a missing item', async () => {
  const response = await request(app)
    .put('/items/99999')
    .send({ name: 'No item', description: 'Not here' });

  assert.equal(response.status, 404);
  assert.equal(response.body.message, 'Item not found');
});
