const { spawn } = require('child_process');

console.log('Starting the Control Center...');
const controlCenter = spawn('npx', ['node', 'control_center.js']);

controlCenter.stdout.on('data', (data) => {
  console.log(`${data}`);
});

controlCenter.stderr.on('data', (data) => {
  console.error(`Control Center Error: ${data}`);
});

controlCenter.on('close', (code) => {
  console.log(`Control Center process exited with code ${code}`);
});
