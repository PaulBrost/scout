// SCOUT — Auth Routes
const router = require('express').Router();

const DASHBOARD_USER = process.env.DASHBOARD_USER || 'scout';
const DASHBOARD_PASS = process.env.DASHBOARD_PASS || 'scout';

router.get('/login', (req, res) => {
  if (req.session?.authenticated) return res.redirect('/');
  res.render('login');
});

router.post('/login', (req, res) => {
  const { username, password } = req.body;
  if (username === DASHBOARD_USER && password === DASHBOARD_PASS) {
    req.session.authenticated = true;
    req.session.username = username;
    return res.redirect('/');
  }
  res.render('login', { error: 'Invalid credentials' });
});

router.get('/logout', (req, res) => {
  req.session.destroy();
  res.redirect('/login');
});

module.exports = router;
