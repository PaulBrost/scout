// SCOUT — Environments Routes
// CRUD for managing target environments (URL, auth, launcher config).

const router = require('express').Router();
const db = require('../../db');

// List all environments
router.get('/', async (req, res) => {
  const result = await db.query(`
    SELECT e.*, 
      (SELECT count(*) FROM assessments a WHERE a.environment_id = e.id) AS assessment_count
    FROM environments e ORDER BY e.is_default DESC, e.name
  `);
  res.render('environments', { environments: result.rows, success: req.query.success, error: req.query.error });
});

// New environment form
router.get('/new', (req, res) => {
  res.render('environment-edit', { env: null });
});

// Create environment
router.post('/', async (req, res) => {
  try {
    const { name, base_url, auth_type, notes, is_default,
            password, username, password_selector, submit_selector,
            launcher_selector, launcher_submit, intro_screens } = req.body;

    const credentials = {};
    if (auth_type === 'password_only' || auth_type === 'username_password') {
      credentials.password = password || '';
      credentials.password_selector = password_selector || '#_ctl0_Body_PasswordText';
      credentials.submit_selector = submit_selector || '#_ctl0_Body_SubmitButton';
    }
    if (auth_type === 'username_password') {
      credentials.username = username || '';
    }

    const launcher = {
      launcher_selector: launcher_selector || '#TheTest',
      submit_selector: launcher_submit || 'input[type="submit"]',
      intro_screens: parseInt(intro_screens) || 5,
    };

    // If setting as default, unset any existing default
    if (is_default) {
      await db.query("UPDATE environments SET is_default = false WHERE is_default = true");
    }

    await db.query(`
      INSERT INTO environments (name, base_url, auth_type, credentials, launcher_config, notes, is_default)
      VALUES ($1, $2, $3, $4, $5, $6, $7)
    `, [name, base_url, auth_type || 'password_only', JSON.stringify(credentials),
        JSON.stringify(launcher), notes || null, !!is_default]);

    res.redirect('/environments?success=created');
  } catch (err) {
    console.error('Create environment error:', err.message);
    res.redirect('/environments?error=' + encodeURIComponent(err.message));
  }
});

// Edit form
router.get('/:id/edit', async (req, res) => {
  const result = await db.query('SELECT * FROM environments WHERE id = $1', [req.params.id]);
  if (result.rows.length === 0) return res.status(404).render('error', { error: 'Environment not found' });
  res.render('environment-edit', { env: result.rows[0] });
});

// Update environment
router.post('/:id', async (req, res) => {
  try {
    const { name, base_url, auth_type, notes, is_default,
            password, username, password_selector, submit_selector,
            launcher_selector, launcher_submit, intro_screens } = req.body;

    const credentials = {};
    if (auth_type === 'password_only' || auth_type === 'username_password') {
      credentials.password = password || '';
      credentials.password_selector = password_selector || '#_ctl0_Body_PasswordText';
      credentials.submit_selector = submit_selector || '#_ctl0_Body_SubmitButton';
    }
    if (auth_type === 'username_password') {
      credentials.username = username || '';
    }

    const launcher = {
      launcher_selector: launcher_selector || '#TheTest',
      submit_selector: launcher_submit || 'input[type="submit"]',
      intro_screens: parseInt(intro_screens) || 5,
    };

    if (is_default) {
      await db.query("UPDATE environments SET is_default = false WHERE is_default = true");
    }

    await db.query(`
      UPDATE environments SET name=$1, base_url=$2, auth_type=$3, credentials=$4,
        launcher_config=$5, notes=$6, is_default=$7, updated_at=now()
      WHERE id=$8
    `, [name, base_url, auth_type || 'password_only', JSON.stringify(credentials),
        JSON.stringify(launcher), notes || null, !!is_default, req.params.id]);

    res.redirect('/environments?success=updated');
  } catch (err) {
    console.error('Update environment error:', err.message);
    res.redirect('/environments?error=' + encodeURIComponent(err.message));
  }
});

// Delete environment
router.post('/:id/delete', async (req, res) => {
  try {
    // Check for linked assessments
    const linked = await db.query('SELECT count(*) FROM assessments WHERE environment_id = $1', [req.params.id]);
    if (parseInt(linked.rows[0].count) > 0) {
      return res.redirect('/environments?error=' + encodeURIComponent('Cannot delete: environment has linked assessments. Remove them first.'));
    }
    await db.query('DELETE FROM environments WHERE id = $1', [req.params.id]);
    res.redirect('/environments?success=deleted');
  } catch (err) {
    console.error('Delete environment error:', err.message);
    res.redirect('/environments?error=' + encodeURIComponent(err.message));
  }
});

module.exports = router;
