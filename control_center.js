const express = require('express');
const { spawn } = require('child_process');
const { Pool } = require('pg');
const bodyParser = require('body-parser');

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

function runPythonScript(args) {
  return new Promise((resolve, reject) => {
    const pythonProcess = spawn('python', ['main.py', ...args]);
    let output = '';

    pythonProcess.stdout.on('data', (data) => {
      output += data.toString();
      console.log(`Python stdout: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
      console.error(`Python stderr: ${data}`);
    });

    pythonProcess.on('close', (code) => {
      if (code === 0) {
        resolve(output);
      } else {
        reject(`Python script exited with code ${code}`);
      }
    });
  });
}

// Run main post processing
app.post('/run-main', async (req, res) => {
  try {
    const output = await runPythonScript([]);
    res.json({ message: 'Main post processing completed', output });
  } catch (error) {
    console.error(`Error: ${error}`);
    res.status(500).json({ error: 'Failed to run main post processing' });
  }
});

// Run custom post processing
app.post('/run-custom', async (req, res) => {
  const { userIds } = req.body;
  if (!userIds || !Array.isArray(userIds)) {
    return res.status(400).json({ error: 'Invalid user IDs' });
  }

  try {
    const output = await runPythonScript(userIds);
    res.json({ message: 'Custom post processing completed', output });
  } catch (error) {
    console.error(`Error: ${error}`);
    res.status(500).json({ error: 'Failed to run custom post processing' });
  }
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
  ssl: true, // Add this line to indicate SSL is being used
  // Don't log the password for security reasons
});
