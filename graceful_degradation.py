"""
Graceful Degradation - Protocols for maintaining functionality during failures.

Implements:
1. Storage Buffer - Fallback when vault is inaccessible
2. Financial Safety - Never auto-retry, requires human approval
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class FailureType(Enum):
    """Types of failures that can occur."""
    COMMS_FAILURE = "comms_failure"
    STORAGE_FAILURE = "storage_failure"
    FINANCIAL_TIMEOUT = "financial_timeout"
    LOGIC_ERROR = "logic_error"
    DATA_ERROR = "data_error"
    TOOL_FAILURE = "tool_failure"


class QueuePriority(Enum):
    """Priority levels for queued tasks."""
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class QueuedTask:
    """Represents a task in the outbox queue."""
    task_id: str
    task_type: str  # gmail, whatsapp, linkedin, x, facebook
    action: str  # send, publish, etc.
    payload: Dict[str, Any]
    created_at: str
    retry_count: int = 0
    max_retries: int = 10
    priority: int = 2  # MEDIUM
    last_error: Optional[str] = None
    last_attempt: Optional[str] = None
    requires_human_approval: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueuedTask":
        return cls(**data)


class GracefulDegradation:
    """
    Manages graceful degradation protocols for the Digital FTE.

    Handles:
    - Storage buffer when vault is inaccessible
    - Human review queue for uninterpretable content
    - Financial safety with human approval
    """

    def __init__(
        self,
        vault_path: Path,
        logs_path: Path,
        buffer_path: Optional[Path] = None,
        human_review_path: Optional[Path] = None,
    ):
        """
        Initialize graceful degradation manager.

        Args:
            vault_path: Path to AI_Employee_Vault
            logs_path: Path to logs directory
            buffer_path: Path to storage buffer (default: /tmp/AI_Employee_Buffer)
            human_review_path: Path to human review queue
        """
        self.vault_path = Path(vault_path)
        self.logs_path = Path(logs_path)

        # Set up paths with defaults
        self.buffer_path = buffer_path or Path(tempfile.gettempdir()) / "AI_Employee_Buffer"
        self.outbox_path = self.buffer_path / "outbox"
        self.human_review_path = human_review_path or self.vault_path / "Human_Review_Queue"

        # State tracking
        self._vault_available: bool = True
        self._comms_available: Dict[str, bool] = {}
        self._processing_queue: bool = False

    async def initialize(self) -> None:
        """Create all necessary directories."""
        for path in [
            self.buffer_path,
            self.logs_path,
            self.human_review_path,
        ]:
            path.mkdir(parents=True, exist_ok=True)

        logger.info("[GracefulDegradation] Initialized")

    # ==================== COMMS FAILURE PROTOCOL ====================

    def is_comms_available(self, channel: str) -> bool:
        """Check if a communication channel is available."""
        return self._comms_available.get(channel, True)

    def mark_comms_down(self, channel: str) -> None:
        """Mark a communication channel as down."""
        self._comms_available[channel] = False
        logger.warning(f"[GracefulDegradation] {channel} marked as DOWN")

    def mark_comms_up(self, channel: str) -> None:
        """Mark a communication channel as available."""
        self._comms_available[channel] = True
        logger.info(f"[GracefulDegradation] {channel} marked as UP")

    async def queue_outgoing_task(
        self,
        task_type: str,
        action: str,
        payload: Dict[str, Any],
        priority: QueuePriority = QueuePriority.MEDIUM,
        requires_human_approval: bool = False,
    ) -> str:
        """
        Queue an outgoing task for later processing.

        Args:
            task_type: Type of task (gmail, whatsapp, linkedin, etc.)
            action: Action to perform (send, publish, etc.)
            payload: Task payload/data
            priority: Task priority
            requires_human_approval: If True, task needs human approval before processing

        Returns:
            Task ID
        """
        # Generate unique task ID
        task_id = self._generate_task_id(task_type, action, payload)

        task = QueuedTask(
            task_id=task_id,
            task_type=task_type,
            action=action,
            payload=payload,
            created_at=datetime.now().isoformat(),
            priority=priority.value,
            requires_human_approval=requires_human_approval,
        )

        # Save to outbox queue
        task_file = self.outbox_path / f"{task_id}.json"
        task_file.write_text(json.dumps(task.to_dict(), indent=2), encoding="utf-8")

        logger.info(f"[GracefulDegradation] Queued task: {task_id} ({task_type}/{action})")

        # Log the queuing
        await self._log_action(
            action_type="task_queued",
            details={
                "task_id": task_id,
                "task_type": task_type,
                "action": action,
                "priority": priority.name,
                "requires_human_approval": requires_human_approval,
            }
        )

        return task_id

    async def process_outbox_queue(
        self,
        channel: str,
        processor: Callable[[QueuedTask], Any],
    ) -> Dict[str, Any]:
        """
        Process queued tasks for a specific channel.

        Args:
            channel: Communication channel to process
            processor: Async function to process each task

        Returns:
            Processing results
        """
        if self._processing_queue:
            return {"status": "already_processing"}

        self._processing_queue = True
        results = {"processed": 0, "failed": 0, "skipped": 0}

        try:
            # Find tasks for this channel
            task_files = list(self.outbox_path.glob(f"*_{channel}_*.json"))
            task_files.extend(self.outbox_path.glob(f"{channel}_*.json"))

            # Sort by priority (lower number = higher priority) and creation time
            tasks: List[QueuedTask] = []
            for tf in task_files:
                try:
                    data = json.loads(tf.read_text(encoding="utf-8"))
                    tasks.append(QueuedTask.from_dict(data))
                except Exception as e:
                    logger.error(f"[GracefulDegradation] Failed to load task {tf}: {e}")

            tasks.sort(key=lambda t: (t.priority, t.created_at))

            logger.info(f"[GracefulDegradation] Processing {len(tasks)} queued tasks for {channel}")

            for task in tasks:
                # Skip tasks requiring human approval
                if task.requires_human_approval:
                    results["skipped"] += 1
                    continue

                # Skip if max retries exceeded - move to human review
                if task.retry_count >= task.max_retries:
                    await self._move_to_human_review(task, "Max retries exceeded")
                    results["skipped"] += 1
                    continue

                try:
                    # Process the task
                    await processor(task)

                    # Success - remove from queue
                    task_file = self.outbox_path / f"{task.task_id}.json"
                    if task_file.exists():
                        task_file.unlink()

                    results["processed"] += 1
                    logger.info(f"[GracefulDegradation] Processed queued task: {task.task_id}")

                    await self._log_action(
                        action_type="queue_task_processed",
                        details={"task_id": task.task_id, "task_type": task.task_type}
                    )

                except Exception as e:
                    # Update task with error
                    task.retry_count += 1
                    task.last_error = str(e)
                    task.last_attempt = datetime.now().isoformat()

                    # Save updated task
                    task_file = self.outbox_path / f"{task.task_id}.json"
                    task_file.write_text(json.dumps(task.to_dict(), indent=2), encoding="utf-8")

                    results["failed"] += 1
                    logger.error(f"[GracefulDegradation] Failed to process task {task.task_id}: {e}")

                    await self._log_action(
                        action_type="queue_task_failed",
                        details={
                            "task_id": task.task_id,
                            "error": str(e),
                            "retry_count": task.retry_count
                        }
                    )

        finally:
            self._processing_queue = False

        return results

    # ==================== STORAGE FAILURE PROTOCOL ====================

    def is_vault_available(self) -> bool:
        """Check if the Obsidian vault is accessible."""
        try:
            # Try to write a test file
            test_file = self.vault_path / ".vault_available_test"
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink()
            self._vault_available = True
            return True
        except Exception:
            self._vault_available = False
            return False

    async def write_with_fallback(
        self,
        relative_path: str,
        content: str,
        encoding: str = "utf-8",
    ) -> Path:
        """
        Write content to vault with fallback to buffer if vault is inaccessible.

        Args:
            relative_path: Path relative to vault root
            content: Content to write
            encoding: File encoding

        Returns:
            Path where file was written
        """
        vault_file = self.vault_path / relative_path
        buffer_file = self.buffer_path / relative_path

        if self.is_vault_available():
            try:
                vault_file.parent.mkdir(parents=True, exist_ok=True)
                vault_file.write_text(content, encoding=encoding)
                logger.debug(f"[GracefulDegradation] Wrote to vault: {relative_path}")
                return vault_file
            except Exception as e:
                logger.warning(f"[GracefulDegradation] Vault write failed: {e}")

        # Fallback to buffer
        buffer_file.parent.mkdir(parents=True, exist_ok=True)
        buffer_file.write_text(content, encoding=encoding)

        # Create checksum for sync verification
        checksum = self._calculate_checksum(content)
        checksum_file = buffer_file.with_suffix(buffer_file.suffix + ".checksum")
        checksum_file.write_text(checksum, encoding="utf-8")

        logger.info(f"[GracefulDegradation] Wrote to buffer: {relative_path}")

        await self._log_action(
            action_type="storage_fallback",
            details={"path": relative_path, "checksum": checksum}
        )

        return buffer_file

    async def sync_buffer_to_vault(self) -> Dict[str, Any]:
        """
        Sync buffered files back to the vault.

        Returns:
            Sync results
        """
        if not self.is_vault_available():
            return {"status": "vault_unavailable"}

        results = {"synced": 0, "failed": 0, "skipped": 0}

        buffer_files = list(self.buffer_path.rglob("*"))
        buffer_files = [f for f in buffer_files if f.is_file() and not f.suffix == ".checksum"]

        for buffer_file in buffer_files:
            try:
                relative_path = buffer_file.relative_to(self.buffer_path)
                vault_file = self.vault_path / relative_path

                # Check checksum if available
                checksum_file = buffer_file.with_suffix(buffer_file.suffix + ".checksum")
                if checksum_file.exists():
                    expected_checksum = checksum_file.read_text().strip()
                    actual_checksum = self._calculate_checksum(buffer_file.read_text())

                    if expected_checksum != actual_checksum:
                        logger.error(f"[GracefulDegradation] Checksum mismatch: {relative_path}")
                        results["failed"] += 1
                        continue

                # Copy to vault
                vault_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(buffer_file, vault_file)

                # Remove buffer file and checksum
                buffer_file.unlink()
                if checksum_file.exists():
                    checksum_file.unlink()

                results["synced"] += 1
                logger.info(f"[GracefulDegradation] Synced: {relative_path}")

            except Exception as e:
                logger.error(f"[GracefulDegradation] Sync failed for {buffer_file}: {e}")
                results["failed"] += 1

        await self._log_action(
            action_type="buffer_sync",
            details=results
        )

        return results

    # ==================== FINANCIAL SAFETY PROTOCOL ====================

    async def handle_financial_failure(
        self,
        task_type: str,
        action: str,
        payload: Dict[str, Any],
        error: Exception,
    ) -> str:
        """
        Handle a financial API failure by moving to Needs_Action with human approval flag.

        NEVER auto-retries financial operations.

        Args:
            task_type: Type of task
            action: Action that failed
            payload: Task payload
            error: The error that occurred

        Returns:
            Task ID in Needs_Action
        """
        # Generate task ID
        task_id = self._generate_task_id(task_type, action, payload)

        # Create task requiring human approval
        task = QueuedTask(
            task_id=task_id,
            task_type=task_type,
            action=action,
            payload=payload,
            created_at=datetime.now().isoformat(),
            last_error=str(error),
            requires_human_approval=True,
        )

        # Move to Needs_Action with special marking
        needs_action_path = self.vault_path / "Needs_Action"
        needs_action_path.mkdir(parents=True, exist_ok=True)

        task_file = needs_action_path / f"financial_{task_id}.md"

        content = f"""# Financial Task - Requires Human Approval

## ⚠️ WARNING: Financial Operation Failed

This task requires **fresh human approval** before retry.

| Field | Value |
|-------|-------|
| **Task ID** | {task_id} |
| **Task Type** | {task_type} |
| **Action** | {action} |
| **Created** | {task.created_at} |
| **Error** | {error} |
| **Requires Approval** | YES |

---

## Original Payload

```json
{json.dumps(payload, indent=2)}
```

---

## Instructions

1. Review the original request and error
2. Verify this transaction should proceed
3. If approved, remove the "financial_" prefix from the filename
4. The orchestrator will process it normally

*Auto-retry is DISABLED for financial operations*
"""

        task_file.write_text(content, encoding="utf-8")

        logger.warning(
            f"[GracefulDegradation] Financial task moved to Needs_Action: {task_id}"
        )

        await self._log_action(
            action_type="financial_timeout",
            details={
                "task_id": task_id,
                "task_type": task_type,
                "action": action,
                "error_observed": str(error),
                "result": "moved_to_needs_action",
            }
        )

        return task_id

    # ==================== HUMAN REVIEW QUEUE ====================

    async def move_to_human_review(
        self,
        content: str,
        reason: str,
        source: str = "unknown",
        original_file: Optional[Path] = None,
    ) -> Path:
        """
        Move uninterpretable content to human review queue.

        Args:
            content: The content that couldn't be processed
            reason: Why it needs human review
            source: Where the content came from
            original_file: Original file path if available

        Returns:
            Path to the review file
        """
        self.human_review_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_review_{source}.md"

        review_content = f"""# Human Review Required

## Metadata

| Field | Value |
|-------|-------|
| **Source** | {source} |
| **Reason** | {reason} |
| **Created** | {datetime.now().isoformat()} |
| **Original File** | {original_file or 'N/A'} |

---

## Content

{content}

---

## Actions

- [ ] Review and interpret the content above
- [ ] Move to `Needs_Action` with clear instructions
- [ ] Or delete if not applicable

*This message was automatically moved here because it could not be processed.*
"""

        review_file = self.human_review_path / filename
        review_file.write_text(review_content, encoding="utf-8")

        logger.info(f"[GracefulDegradation] Moved to Human Review: {filename}")

        await self._log_action(
            action_type="human_review_queued",
            details={"file": filename, "reason": reason, "source": source}
        )

        return review_file

    async def _move_to_human_review(self, task: QueuedTask, reason: str) -> None:
        """Internal method to move a queued task to human review."""
        content = json.dumps(task.to_dict(), indent=2)
        await self.move_to_human_review(
            content=content,
            reason=reason,
            source=f"outbox_queue/{task.task_type}",
        )

        # Remove from queue
        task_file = self.outbox_path / f"{task.task_id}.json"
        if task_file.exists():
            task_file.unlink()


    # ==================== UTILITY METHODS ====================

    def _generate_task_id(self, task_type: str, action: str, payload: Dict) -> str:
        """Generate a unique task ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        content_hash = hashlib.md5(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:8]
        return f"{timestamp}_{task_type}_{action}_{content_hash}"

    def _calculate_checksum(self, content: str) -> str:
        """Calculate MD5 checksum for content."""
        return hashlib.md5(content.encode()).hexdigest()

    async def _log_action(self, action_type: str, details: Dict[str, Any]) -> None:
        """Log an action to the audit log."""
        try:
            self.logs_path.mkdir(parents=True, exist_ok=True)

            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "action_type": action_type,
                "error_observed": details.get("error", details.get("error_observed")),
                "result": details.get("result", "logged"),
                **details
            }

            log_file = self.logs_path / f"recovery_audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"[GracefulDegradation] Failed to log action: {e}")

    async def _update_dashboard_alert(
        self,
        alert_type: str,
        message: str,
        details: str = "",
    ) -> None:
        """Update Dashboard.md with an alert."""
        try:
            dashboard_path = self.vault_path / "Dashboard.md"

            if not dashboard_path.exists():
                return

            content = dashboard_path.read_text(encoding="utf-8")

            # Add alert to the top of the file
            alert = f"""
## ⚠️ Alert: {alert_type.title()}

**{message}**

{details}

*{datetime.now().isoformat()}*

---

"""
            # Insert after the header if present
            if content.startswith("# "):
                lines = content.split("\n")
                header_end = 0
                for i, line in enumerate(lines):
                    if line.startswith("# ") and i == 0:
                        continue
                    if line.strip() == "" or line.startswith("# "):
                        header_end = i
                        break
                content = "\n".join(lines[:header_end]) + "\n" + alert + "\n".join(lines[header_end:])
            else:
                content = alert + content

            dashboard_path.write_text(content, encoding="utf-8")

        except Exception as e:
            logger.error(f"[GracefulDegradation] Failed to update dashboard: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of graceful degradation systems."""
        return {
            "vault_available": self._vault_available,
            "comms_status": self._comms_available,
            "buffer_size": len(list(self.buffer_path.rglob("*"))),
            "human_review_size": len(list(self.human_review_path.glob("*.md"))),
        }
