// SCOUT — Items Routes
const router = require('express').Router();
const db = require('../../db');
const queries = require('../../db/queries');

// List all items
router.get('/', async (req, res) => {
  try {
    const result = await db.query('SELECT * FROM items ORDER BY id');
    res.render('items', { items: result.rows });
  } catch (err) {
    res.render('items', { items: [], error: err.message });
  }
});

// Item detail with history
router.get('/:id', async (req, res) => {
  try {
    const itemResult = await db.query('SELECT * FROM items WHERE id = $1', [req.params.id]);
    if (itemResult.rows.length === 0) {
      return res.status(404).render('error', { error: 'Item not found' });
    }
    const item = itemResult.rows[0];
    const history = await queries.getItemHistory(item.id);

    res.render('item-detail', { item, history });
  } catch (err) {
    res.status(500).render('error', { error: err.message });
  }
});

module.exports = router;
