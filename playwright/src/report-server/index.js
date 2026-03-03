// SCOUT — Report Dashboard Server
// Express app serving the web dashboard for test results, diffs, and AI analysis.

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../../.env') });

const express = require('express');
const session = require('express-session');
const db = require('../db');

const app = express();
const PORT = process.env.PORT || 3000;

// View engine
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// Serve screenshots and test results as static files
app.use('/screenshots', express.static(path.resolve(__dirname, '../../baselines')));
app.use('/test-results', express.static(path.resolve(__dirname, '../../test-results')));

// Session (simple — for internal use only)
app.use(session({
  secret: process.env.SESSION_SECRET || 'scout-dev-secret',
  resave: false,
  saveUninitialized: false,
  cookie: { maxAge: 8 * 60 * 60 * 1000 }, // 8 hours
}));

// Auth middleware — skip for login page and API health
function requireAuth(req, res, next) {
  if (req.session?.authenticated || process.env.DASHBOARD_AUTH === 'false') {
    // Make username available to all templates
    res.locals.username = req.session?.username || 'scout';
    return next();
  }
  if (req.path === '/login' || req.path === '/api/health') {
    return next();
  }
  res.redirect('/login');
}

app.use(requireAuth);

// Routes
app.use('/', require('./routes/auth'));
app.use('/', require('./routes/dashboard'));
app.use('/runs', require('./routes/runs'));
app.use('/items', require('./routes/items-list'));
app.use('/assessments', require('./routes/assessments'));
app.use('/test-cases', require('./routes/test-cases'));
app.use('/suites', require('./routes/suites'));
app.use('/reviews', require('./routes/reviews'));
app.use('/environments', require('./routes/environments'));
app.use('/builder', require('./routes/builder'));
app.use('/admin', require('./routes/admin'));
app.use('/api', require('./routes/api'));

// Health check
app.get('/api/health', async (req, res) => {
  const dbHealth = await db.healthCheck();
  res.json({
    status: dbHealth.healthy ? 'ok' : 'degraded',
    database: dbHealth,
    uptime: process.uptime(),
  });
});

// Error handler
app.use((err, req, res, _next) => {
  const msg = (err && err.message) || 'Unknown error';
  console.error('SCOUT Dashboard Error:', msg);
  res.status(500).render('error', { error: msg });
});

// Start
app.listen(PORT, () => {
  console.log(`SCOUT Dashboard running on http://localhost:${PORT}`);
});

module.exports = app;
