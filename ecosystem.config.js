/**
 * PM2 Ecosystem Configuration for Digital FTE
 *
 * Commands:
 *   pm2 start ecosystem.config.js    # Start all processes
 *   pm2 save                          # Save process list
 *   pm2 startup                       # Generate startup script (run output command with admin)
 *   pm2 logs                          # View logs
 *   pm2 monit                         # Real-time monitoring
 *   pm2 restart all                   # Restart all processes
 *   pm2 stop all                      # Stop all processes
 *
 * Windows Auto-start:
 *   npm install -g pm2-windows-startup
 *   pm2-startup install
 *   pm2 start ecosystem.config.js
 *   pm2 save
 */

module.exports = {
  apps: [
    {
      name: 'fte-main',
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
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      // Restart on crash with exponential backoff
      restart_delay: 5000,
      exp_backoff_restart_delay: 100,
      max_restarts: 10,
      // Graceful shutdown
      kill_timeout: 10000,
      wait_ready: true,
      listen_timeout: 10000,
    },
    {
      name: 'fte-watchdog',
      script: 'watchdog_runner.py',
      interpreter: 'python',
      cwd: __dirname,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '200M',
      env: {
        PYTHONUNBUFFERED: '1',
      },
      error_file: 'AI_Employee_Vault/Logs/watchdog-error.log',
      out_file: 'AI_Employee_Vault/Logs/watchdog-out.log',
      time: true,
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      restart_delay: 10000,
      max_restarts: 5,
      kill_timeout: 5000,
    },
  ],
};
