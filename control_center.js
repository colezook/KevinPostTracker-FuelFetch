const express = require('express');
const { spawn } = require('child_process');
const { Pool } = require('pg');
const bodyParser = require('body-parser');
const fs = require('fs');

const app = express();
const port = 3000;

app.use(bodyParser.json());
app.use(express.static('public'));

// PostgreSQL connection configuration
const dbConfig = {
  user: process.env.PGUSER,
  host: process.env.PGHOST,
  database: process.env.PGDATABASE,
  password: process.env.PGPASSWORD,
  port: process.env.PGPORT,
  ssl: {
    rejectUnauthorized: false,
    sslmode: 'require'
  }
};

const pool = new Pool(dbConfig);

// Test database connection
pool.query('SELECT NOW()', (err, res) => {
  if (err) {
    console.error('Error connecting to the database:', err);
  } else {
    console.log('Successfully connected to the database');
  }
});

// Clear 'posts' table
app.post('/clear-posts', async (req, res) => {
  const client = await pool.connect();
  try {
    await client.query('TRUNCATE TABLE posts');
    res.json({ success: true, message: 'Posts table cleared successfully' });
  } catch (error) {
    console.error('Error clearing posts table:', error);
    res.status(500).json({ success: false, error: 'Failed to clear posts table', details: error.message });
  } finally {
    client.release();
  }
});

async function addTimestampColumnToPosts() {
  const client = await pool.connect();
  try {
    await client.query('ALTER TABLE posts ADD COLUMN IF NOT EXISTS timestamp TIMESTAMP WITH TIME ZONE');
    console.log('Successfully added timestamp column to posts table');
    return { success: true, message: 'Successfully added timestamp column to posts table' };
  } catch (error) {
    console.error('Error adding timestamp column to posts table:', error);
    return { success: false, error: 'Failed to add timestamp column to posts table', details: error.message };
  } finally {
    client.release();
  }
}

// Add a new route to trigger the column addition
app.post('/add-timestamp-column', async (req, res) => {
  const result = await addTimestampColumnToPosts();
  res.json(result);
});

async function addUrlColumnToPosts() {
  const client = await pool.connect();
  try {
    await client.query('ALTER TABLE posts ADD COLUMN IF NOT EXISTS url TEXT');
    console.log('Successfully added url column to posts table');
    return { success: true, message: 'Successfully added url column to posts table' };
  } catch (error) {
    console.error('Error adding url column to posts table:', error);
    return { success: false, error: 'Failed to add url column to posts table', details: error.message };
  } finally {
    client.release();
  }
}

// Add a new route to trigger the column addition
app.post('/add-url-column', async (req, res) => {
  const result = await addUrlColumnToPosts();
  res.json(result);
});

function runPythonScript(args, res) {
  const pythonProcess = spawn('python', ['main.py', ...args]);

  function sendOutput(data, type = 'output') {
    const lines = data.toString().split('\n').filter(line => line.trim() !== '');
    lines.forEach(line => {
      res.write(`data: ${JSON.stringify({type, message: line})}\n\n`);
    });
  }

  pythonProcess.stdout.on('data', (data) => {
    sendOutput(data);
    console.log(`Python stdout: ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    sendOutput(data, 'error');
    console.error(`Python stderr: ${data}`);
  });

  pythonProcess.on('close', (code) => {
    sendOutput(`Process exited with code ${code}`, 'info');
    res.end();
  });
}

// Run main post processing
app.get('/run-main', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive'
  });
  runPythonScript([], res);
});

// Run custom post processing
app.get('/run-custom', (req, res) => {
  const customUserIds = req.query.userIds.split(',');
  const allowedUserIds = getAllowedUserIds(customUserIds);
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive'
  });
  runPythonScript(['--user_ids', allowedUserIds.join(',')], res);
});

// Capture console.log and console.error
const originalConsoleLog = console.log;
const originalConsoleError = console.error;

console.log = function() {
  sendToAllClients('output', Array.from(arguments).join(' '));
  originalConsoleLog.apply(console, arguments);
};

console.error = function() {
  sendToAllClients('error', Array.from(arguments).join(' '));
  originalConsoleError.apply(console, arguments);
};

// Store all connected clients
const clients = new Set();

function sendToAllClients(type, message) {
  clients.forEach(client => {
    client.res.write(`data: ${JSON.stringify({type, message})}\n\n`);
  });
}

// New route for SSE connection
app.get('/events', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive'
  });

  const client = { id: Date.now(), res };
  clients.add(client);

  req.on('close', () => {
    clients.delete(client);
  });
});

app.listen(port, () => {
  console.log(`Control center app listening at http://localhost:${port}`);
  console.log(`Open http://localhost:${port} in your browser to access the control center.`);
});

console.log('Database config:', {
  dbname: process.env.PGDATABASE,
  user: process.env.PGUSER,
  host: process.env.PGHOST,
  port: process.env.PGPORT,
  ssl: true,
});

function getAllowedUserIds(customUserIds) {
  const defaultUserIds = USER_IDS;
  return [...new Set([...defaultUserIds, ...customUserIds])];
}
