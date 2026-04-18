"""
Watchdog - Process monitoring and auto-restart for Digital FTE.

Monitors critical processes:
- Orchestrator
- Gmail Watcher
- WhatsApp Watcher
- LinkedIn Watcher
- Social Post Watcher

Features:
- Heartbeat monitoring (each process writes heartbeat file)
- Auto-restart on crash (with exponential backoff)
- Logging of all recovery events
- PM2 integration commands
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# Heartbeat directory (in temp for cross-platform compatibility)
HEARTBEAT_DIR = Path(tempfile.gettempdir()) / "AI_Employee_Heartbeat"

# Process definitions: name -> (script_name, heartbeat_file)
PROCESS_CONFIGS = {
    "orchestrator": {
        "script": "main.py",
        "heartbeat": "orchestrator.heartbeat",
        "description": "Main orchestrator processing tasks",
    },
    "gmail_watcher": {
        "script": "main.py",  # Runs within main.py
        "heartbeat": "gmail_watcher.heartbeat",
        "description": "Gmail inbox monitor",
    },
    "whatsapp_watcher": {
        "script": "main.py",  # Runs within main.py
        "heartbeat": "whatsapp_watcher.heartbeat",
        "description": "WhatsApp Web monitor",
    },
    "linkedin_watcher": {
        "script": "main.py",  # Runs within main.py
        "heartbeat": "linkedin_watcher.heartbeat",
        "description": "LinkedIn post request monitor",
    },
    "social_watcher": {
        "script": "main.py",  # Runs within main.py
        "heartbeat": "social_watcher.heartbeat",
        "description": "X/Instagram/Facebook post monitor",
    },
}


class ProcessInfo:
    """Tracks information about a monitored process."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.last_heartbeat: Optional[datetime] = None
        self.consecutive_failures: int = 0
        self.total_restarts: int = 0
        self.last_restart: Optional[datetime] = None
        self.status: str = "unknown"

    def heartbeat_file(self) -> Path:
        return HEARTBEAT_DIR / self.config["heartbeat"]

    def check_heartbeat(self, timeout_seconds: int = 120) -> bool:
        """Check if heartbeat is recent."""
        heartbeat_path = self.heartbeat_file()

        if not heartbeat_path.exists():
            self.status = "no_heartbeat"
            return False

        try:
            data = json.loads(heartbeat_path.read_text())
            last_beat = datetime.fromisoformat(data.get("timestamp", ""))
            self.last_heartbeat = last_beat

            age = datetime.now() - last_beat
            if age.total_seconds() > timeout_seconds:
                self.status = "heartbeat_stale"
                return False

            self.status = "healthy"
            return True

        except Exception as e:
            logger.error(f"[Watchdog] Failed to read heartbeat for {self.name}: {e}")
            self.status = "heartbeat_error"
            return False

    def record_failure(self) -> None:
        """Record a failure for this process."""
        self.consecutive_failures += 1

    def reset_failures(self) -> None:
        """Reset failure counter on successful restart."""
        self.consecutive_failures = 0


class Watchdog:
    """
    Process watchdog that monitors and restarts critical processes.
    """

    # Maximum restarts in time window before giving up
    MAX_RESTARTS = 3
    RESTART_WINDOW_MINUTES = 5

    # Heartbeat timeout (60 seconds as specified by user)
    HEARTBEAT_TIMEOUT = 60

    def __init__(
        self,
        vault_path: Path,
        logs_path: Path,
        check_interval: float = 60.0,  # 60 seconds as requested
        auto_restart: bool = True,
    ):
        """
        Initialize the watchdog.

        Args:
            vault_path: Path to AI_Employee_Vault
            logs_path: Path to logs directory
            check_interval: How often to check heartbeats (seconds)
            auto_restart: Whether to automatically restart crashed processes
        """
        self.vault_path = Path(vault_path)
        self.logs_path = Path(logs_path)
        self.check_interval = check_interval
        self.auto_restart = auto_restart

        # Initialize process trackers
        self.processes: Dict[str, ProcessInfo] = {}
        for name, config in PROCESS_CONFIGS.items():
            self.processes[name] = ProcessInfo(name, config)

        self._running = False
        self._start_times: Dict[str, datetime] = {}

    async def initialize(self) -> None:
        """Set up heartbeat directory."""
        HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"[Watchdog] Initialized (heartbeat dir: {HEARTBEAT_DIR})")

    async def run(self) -> None:
        """Main watchdog loop."""
        self._running = True
        logger.info("[Watchdog] Starting monitoring loop")

        try:
            while self._running:
                await self._check_all_processes()
                await asyncio.sleep(self.check_interval)

        except asyncio.CancelledError:
            logger.info("[Watchdog] Monitoring cancelled")
        finally:
            logger.info("[Watchdog] Stopped")

    def stop(self) -> None:
        """Stop the watchdog."""
        self._running = False
        logger.info("[Watchdog] Stop signal received")

    async def _check_all_processes(self) -> None:
        """Check all monitored processes."""
        for name, process in self.processes.items():
            try:
                healthy = process.check_heartbeat(self.HEARTBEAT_TIMEOUT)

                if healthy:
                    process.reset_failures()
                    logger.debug(f"[Watchdog] {name}: healthy")
                else:
                    logger.warning(
                        f"[Watchdog] {name}: unhealthy (status={process.status}, "
                        f"failures={process.consecutive_failures})"
                    )

                    if self.auto_restart:
                        await self._handle_unhealthy_process(name, process)

            except Exception as e:
                logger.error(f"[Watchdog] Error checking {name}: {e}")

    async def _handle_unhealthy_process(self, name: str, process: ProcessInfo) -> None:
        """Handle an unhealthy process."""
        now = datetime.now()

        # Check restart rate limiting
        recent_restarts = self._count_recent_restarts(name)
        if recent_restarts >= self.MAX_RESTARTS:
            logger.error(
                f"[Watchdog] {name}: Max restarts ({self.MAX_RESTARTS}) exceeded in "
                f"{self.RESTART_WINDOW_MINUTES} minutes. Requires manual intervention."
            )

            await self._log_recovery_attempt(
                process_name=name,
                action="restart_aborted",
                error_observed=f"Max restarts exceeded (status={process.status})",
                result="failed",
            )
            return

        # Calculate backoff
        backoff = self._calculate_backoff(process.consecutive_failures)

        logger.warning(
            f"[Watchdog] {name}: Attempting restart (backoff={backoff}s, "
            f"attempt={process.consecutive_failures + 1})"
        )

        await asyncio.sleep(backoff)

        # Attempt restart
        success = await self._restart_process(name, process)

        if success:
            process.record_restart()
            process.last_restart = now
            self._start_times[name] = now

            await self._log_recovery_attempt(
                process_name=name,
                action="process_restarted",
                error_observed=process.status,
                result="success",
            )
        else:
            process.record_failure()

            await self._log_recovery_attempt(
                process_name=name,
                action="restart_failed",
                error_observed=process.status,
                result="failed",
            )

    async def _restart_process(self, name: str, process: ProcessInfo) -> bool:
        """
        Restart a process.

        Note: For processes running within main.py, this will restart
        the entire main.py which includes all watchers.
        """
        script = process.config["script"]
        script_path = self.vault_path.parent / script

        try:
            # For PM2-managed processes, use PM2 to restart
            if self._is_pm2_managed(name):
                result = subprocess.run(
                    ["pm2", "restart", f"fte-{name}"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    logger.info(f"[Watchdog] {name}: Restarted via PM2")
                    return True
                else:
                    logger.error(f"[Watchdog] {name}: PM2 restart failed: {result.stderr}")
                    return False

            # Direct process restart (for standalone scripts)
            if sys.platform == "win32":
                # Windows: use pythonw to avoid console window
                subprocess.Popen(
                    [sys.executable, str(script_path)],
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    cwd=str(self.vault_path.parent),
                )
            else:
                # Unix: use nohup
                subprocess.Popen(
                    ["nohup", sys.executable, str(script_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    cwd=str(self.vault_path.parent),
                )

            logger.info(f"[Watchdog] {name}: Process restart initiated")
            return True

        except Exception as e:
            logger.error(f"[Watchdog] {name}: Restart error: {e}")
            return False

    def _is_pm2_managed(self, name: str) -> bool:
        """Check if process is managed by PM2."""
        try:
            result = subprocess.run(
                ["pm2", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return f"fte-{name}" in result.stdout
        except Exception:
            return False

    def _count_recent_restarts(self, name: str) -> int:
        """Count restarts in the time window."""
        cutoff = datetime.now() - timedelta(minutes=self.RESTART_WINDOW_MINUTES)

        # This is simplified - in production would query actual restart history
        process = self.processes.get(name)
        if process and process.last_restart:
            if process.last_restart > cutoff:
                return process.total_restarts
        return 0

    def _calculate_backoff(self, failures: int) -> float:
        """Calculate backoff time for restart attempts."""
        base = 5.0
        max_backoff = 60.0

        backoff = min(base * (2 ** failures), max_backoff)
        return backoff

    async def _log_recovery_attempt(
        self,
        process_name: str,
        action: str,
        error_observed: str,
        result: str,
    ) -> None:
        """Log recovery attempt to audit log."""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "action_type": action,
                "process_name": process_name,
                "error_observed": error_observed,
                "result": result,
            }

            log_file = self.logs_path / f"watchdog_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")

        except Exception as e:
            logger.error(f"[Watchdog] Failed to log recovery attempt: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get status of all monitored processes."""
        return {
            name: {
                "status": proc.status,
                "last_heartbeat": proc.last_heartbeat.isoformat() if proc.last_heartbeat else None,
                "consecutive_failures": proc.consecutive_failures,
                "total_restarts": proc.total_restarts,
            }
            for name, proc in self.processes.items()
        }


def write_heartbeat(process_name: str, additional_data: Optional[dict] = None) -> None:
    """
    Write a heartbeat file for a process.

    Call this periodically from your process (every 30 seconds recommended).

    Args:
        process_name: Name of the process (must match PROCESS_CONFIGS)
        additional_data: Optional additional data to include in heartbeat
    """
    HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)

    heartbeat_path = HEARTBEAT_DIR / f"{process_name}.heartbeat"

    data = {
        "process": process_name,
        "timestamp": datetime.now().isoformat(),
        "pid": os.getpid(),
    }

    if additional_data:
        data.update(additional_data)

    heartbeat_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def clear_heartbeat(process_name: str) -> None:
    """Clear heartbeat file (call on clean shutdown)."""
    heartbeat_path = HEARTBEAT_DIR / f"{process_name}.heartbeat"
    if heartbeat_path.exists():
        heartbeat_path.unlink()


# Context manager for heartbeat management
class HeartbeatContext:
    """Context manager that maintains heartbeat while process runs."""

    def __init__(self, process_name: str, interval: float = 30.0):
        self.process_name = process_name
        self.interval = interval
        self._task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        self._task = asyncio.create_task(self._heartbeat_loop())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        clear_heartbeat(self.process_name)

    async def _heartbeat_loop(self):
        """Continuously write heartbeat."""
        while True:
            write_heartbeat(self.process_name)
            await asyncio.sleep(self.interval)


# ==================== PM2 CONFIGURATION ====================

PM2_CONFIG = """
// PM2 ecosystem configuration for Digital FTE
// Save this as ecosystem.config.js in your project root

module.exports = {
  apps: [
    {
      name: 'fte-main',
      script: 'main.py',
      interpreter: 'python',
      cwd: './',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      restart_delay: 5000,
      exp_backoff_restart_delay: 100,
      max_restarts: 10,
      env: {
        NODE_ENV: 'production',
      },
      error_file: './AI_Employee_Vault/Logs/pm2-error.log',
      out_file: './AI_Employee_Vault/Logs/pm2-out.log',
      log_file: './AI_Employee_Vault/Logs/pm2-combined.log',
      time: true,
    },
    {
      name: 'fte-watchdog',
      script: 'watchdog_runner.py',
      interpreter: 'python',
      cwd: './',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '200M',
      restart_delay: 10000,
      max_restarts: 5,
      error_file: './AI_Employee_Vault/Logs/watchdog-error.log',
      out_file: './AI_Employee_Vault/Logs/watchdog-out.log',
      time: true,
    },
  ],
};
"""


def print_pm2_commands():
    """Print PM2 commands for daemonizing the FTE system."""
    commands = """
# ==================== PM2 COMMANDS FOR DIGITAL FTE ====================

# 1. Install PM2 globally (if not already installed)
npm install -g pm2

# 2. Generate ecosystem.config.js
# (Copy the config above to ecosystem.config.js in your project root)

# 3. Start all processes
pm2 start ecosystem.config.js

# 4. Save PM2 process list
pm2 save

# 5. Configure PM2 to start on system boot (run this command and follow instructions)
pm2 startup

# ================================================================

# MONITORING COMMANDS:

# View process status
pm2 status

# View logs (all processes)
pm2 logs

# View logs (specific process)
pm2 logs fte-main
pm2 logs fte-watchdog

# Real-time monitoring dashboard
pm2 monit

# ================================================================

# CONTROL COMMANDS:

# Restart all processes
pm2 restart all

# Restart specific process
pm2 restart fte-main

# Stop all processes
pm2 stop all

# Stop specific process
pm2 stop fte-main

# Delete all processes from PM2
pm2 delete all

# ================================================================

# MAINTENANCE COMMANDS:

# Flush logs
pm2 flush

# Reload logs (without restarting)
pm2 reloadLogs

# Show process details
pm2 show fte-main

# Show PM2 configuration
pm2 conf

# ================================================================

# AUTO-START ON BOOT:

# After running 'pm2 startup', you need to:
# 1. Copy and paste the command it outputs (requires sudo)
# 2. Run 'pm2 save' to save current processes
# 3. On next boot, PM2 will automatically start all saved processes

# Disable auto-start:
pm2 unstartup

# ================================================================

# WINDOWS SPECIFIC (pm2-windows-startup):

# For Windows, use pm2-windows-startup package:
npm install -g pm2-windows-startup
pm2-startup install
pm2 start ecosystem.config.js
pm2 save

# ================================================================
"""
    print(commands)


if __name__ == "__main__":
    print_pm2_commands()
