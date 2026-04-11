// PM2 Ecosystem Configuration for Digital FTE
// Run with: pm2 start ecosystem.config.js

module.exports = {
  apps: [
    {
      name: 'digital-fte',
      script: 'main.py',
      interpreter: 'python',
      cwd: __dirname,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
      },
      error_file: 'AI_Employee_Vault/Logs/pm2-error.log',
      out_file: 'AI_Employee_Vault/Logs/pm2-out.log',
      log_file: 'AI_Employee_Vault/Logs/pm2-combined.log',
      time: true,
      // Restart on crash with backoff
      restart_delay: 5000,
      max_restarts: 10,
      // Graceful shutdown
      kill_timeout: 10000,
      wait_ready: false,
    },
  ],
};
