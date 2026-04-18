"""
Retry Handler - Exponential backoff retry logic for API calls.

Provides @with_retry decorator for transient error recovery.
NEVER applies to financial/banking APIs (they require human approval).
"""

import asyncio
import functools
import json
import logging
import random
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Set, Type, Tuple

logger = logging.getLogger(__name__)

# Default transient errors that should be retried
DEFAULT_TRANSIENT_ERRORS: Tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)

# HTTP status codes that indicate transient errors
TRANSIENT_STATUS_CODES: Set[int] = {
    408,  # Request Timeout
    429,  # Too Many Requests (rate limit)
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}

# Keywords to identify financial/banking APIs - NEVER auto-retry
FINANCIAL_KEYWORDS: Set[str] = {
    "payment", "bank", "financial", "stripe", "paypal", "plaid",
    "transfer", "wallet", "transaction", "checkout", "invoice_payment",
    "odoofinancial", "billing", "credit", "debit", "balance",
}


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""
    pass


class FinancialAPIError(Exception):
    """Raised when a financial API call fails - requires human approval."""
    pass


def is_transient_error(error: Exception) -> bool:
    """
    Determine if an error is transient and should be retried.

    Args:
        error: The exception that occurred

    Returns:
        True if the error is transient and should be retried
    """
    # Check if it's a known transient error type
    if isinstance(error, DEFAULT_TRANSIENT_ERRORS):
        return True

    # Check for HTTP status codes in error message
    error_str = str(error).lower()
    for code in TRANSIENT_STATUS_CODES:
        if str(code) in error_str:
            return True

    # Check for common transient error messages
    transient_messages = [
        "timeout",
        "timed out",
        "connection refused",
        "connection reset",
        "connection closed",
        "network",
        "rate limit",
        "too many requests",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "temporarily unavailable",
        "try again",
        "retry",
    ]

    for msg in transient_messages:
        if msg in error_str:
            return True

    return False


def is_financial_api(func_name: str, args: tuple, kwargs: dict) -> bool:
    """
    Check if a function call is related to financial/banking APIs.

    Args:
        func_name: Name of the function being called
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        True if this appears to be a financial API call
    """
    # Check function name
    func_lower = func_name.lower()
    for keyword in FINANCIAL_KEYWORDS:
        if keyword in func_lower:
            return True

    # Check arguments for financial indicators
    for arg in args:
        if isinstance(arg, str):
            arg_lower = arg.lower()
            for keyword in FINANCIAL_KEYWORDS:
                if keyword in arg_lower:
                    return True
        elif isinstance(arg, dict):
            arg_str = str(arg).lower()
            for keyword in FINANCIAL_KEYWORDS:
                if keyword in arg_str:
                    return True

    # Check keyword arguments
    for key, value in kwargs.items():
        key_lower = key.lower()
        for keyword in FINANCIAL_KEYWORDS:
            if keyword in key_lower:
                return True
        if isinstance(value, str):
            value_lower = value.lower()
            for keyword in FINANCIAL_KEYWORDS:
                if keyword in value_lower:
                    return True

    return False


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True
) -> float:
    """
    Calculate exponential backoff delay.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Add random jitter to avoid thundering herd

    Returns:
        Delay in seconds
    """
    # Exponential backoff: base * 2^attempt
    delay = min(base_delay * (2 ** attempt), max_delay)

    if jitter:
        # Add up to 25% random jitter
        jitter_amount = delay * random.uniform(0, 0.25)
        delay += jitter_amount

    return delay


def with_retry(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    transient_errors: Optional[Tuple[Type[Exception], ...]] = None,
    logs_path: Optional[Path] = None,
    on_final_failure: Optional[Callable[[Exception, dict], None]] = None,
):
    """
    Decorator that adds exponential backoff retry logic to async functions.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
        max_delay: Maximum delay in seconds
        jitter: Add random jitter to backoff
        transient_errors: Tuple of exception types to retry (default: connection/timeout errors)
        logs_path: Path to logs directory for audit logging
        on_final_failure: Callback when all retries are exhausted

    Returns:
        Decorated function with retry logic

    Usage:
        @with_retry(max_retries=5, base_delay=1.0, max_delay=60.0)
        async def api_call():
            ...

        # Financial APIs should NOT use this decorator, or mark with @financial_api
    """
    if transient_errors is None:
        transient_errors = DEFAULT_TRANSIENT_ERRORS

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            func_name = func.__name__

            # Check if this is a financial API - never auto-retry
            if is_financial_api(func_name, args, kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.error(
                        f"[RetryHandler] Financial API call failed (no auto-retry): "
                        f"{func_name}: {e}"
                    )
                    # Log for human approval
                    await _log_financial_failure(func_name, args, kwargs, e, logs_path)
                    raise FinancialAPIError(
                        f"Financial API call failed: {e}. Requires human approval."
                    ) from e

            last_error: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except transient_errors as e:
                    last_error = e

                    if attempt < max_retries:
                        delay = calculate_backoff(attempt, base_delay, max_delay, jitter)

                        logger.warning(
                            f"[RetryHandler] {func_name} failed (attempt {attempt + 1}/{max_retries + 1}): "
                            f"{type(e).__name__}: {e}. Retrying in {delay:.1f}s..."
                        )

                        # Log retry attempt
                        await _log_retry_attempt(
                            func_name, attempt, e, delay, logs_path
                        )

                        await asyncio.sleep(delay)
                    else:
                        # All retries exhausted
                        logger.error(
                            f"[RetryHandler] {func_name} failed after {max_retries + 1} attempts"
                        )

                except Exception as e:
                    # Check if this is a transient error we should retry
                    if is_transient_error(e):
                        last_error = e

                        if attempt < max_retries:
                            delay = calculate_backoff(attempt, base_delay, max_delay, jitter)

                            logger.warning(
                                f"[RetryHandler] {func_name} transient error "
                                f"(attempt {attempt + 1}/{max_retries + 1}): {e}. "
                                f"Retrying in {delay:.1f}s..."
                            )

                            await _log_retry_attempt(
                                func_name, attempt, e, delay, logs_path
                            )

                            await asyncio.sleep(delay)
                        else:
                            last_error = e
                    else:
                        # Non-transient error, don't retry
                        logger.error(
                            f"[RetryHandler] {func_name} failed with non-transient error: {e}"
                        )
                        raise

            # All retries exhausted
            error_info = {
                "function": func_name,
                "args": str(args)[:200],  # Truncate for logging
                "kwargs": str(kwargs)[:200],
                "error": str(last_error),
                "attempts": max_retries + 1,
            }

            # Log final failure
            await _log_final_failure(func_name, last_error, error_info, logs_path)

            # Call failure callback if provided
            if on_final_failure and last_error:
                try:
                    on_final_failure(last_error, error_info)
                except Exception as callback_error:
                    logger.error(f"[RetryHandler] Failure callback error: {callback_error}")

            raise RetryExhaustedError(
                f"{func_name} failed after {max_retries + 1} attempts: {last_error}"
            ) from last_error

        return wrapper
    return decorator


def financial_api(func: Callable) -> Callable:
    """
    Marker decorator for financial/banking API functions.

    These functions will NEVER auto-retry on failure.
    Instead, they require fresh human approval.

    Usage:
        @financial_api
        async def process_payment():
            ...
    """
    func._is_financial_api = True

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(
                f"[RetryHandler] Financial API failed (no auto-retry): "
                f"{func.__name__}: {e}"
            )
            raise

    return wrapper


async def _log_retry_attempt(
    func_name: str,
    attempt: int,
    error: Exception,
    delay: float,
    logs_path: Optional[Path]
) -> None:
    """Log a retry attempt to the audit log."""
    if not logs_path:
        return

    try:
        logs_path.mkdir(parents=True, exist_ok=True)
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": "retry_attempt",
            "function": func_name,
            "attempt": attempt + 1,
            "error_observed": f"{type(error).__name__}: {str(error)[:200]}",
            "delay_seconds": delay,
            "result": "retrying",
        }

        log_file = logs_path / f"recovery_audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        logger.error(f"[RetryHandler] Failed to log retry attempt: {e}")


async def _log_final_failure(
    func_name: str,
    error: Exception,
    error_info: dict,
    logs_path: Optional[Path]
) -> None:
    """Log a final failure to the audit log."""
    if not logs_path:
        return

    try:
        logs_path.mkdir(parents=True, exist_ok=True)
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": "retry_exhausted",
            "function": func_name,
            "error_observed": f"{type(error).__name__}: {str(error)[:500]}",
            "error_details": error_info,
            "result": "failed",
        }

        log_file = logs_path / f"recovery_audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        logger.error(f"[RetryHandler] Failed to log final failure: {e}")


async def _log_financial_failure(
    func_name: str,
    args: tuple,
    kwargs: dict,
    error: Exception,
    logs_path: Optional[Path]
) -> None:
    """Log a financial API failure requiring human approval."""
    if not logs_path:
        return

    try:
        logs_path.mkdir(parents=True, exist_ok=True)
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": "financial_api_failure",
            "function": func_name,
            "error_observed": f"{type(error).__name__}: {str(error)[:500]}",
            "requires_human_approval": True,
            "result": "pending_human_approval",
        }

        log_file = logs_path / f"recovery_audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        logger.error(f"[RetryHandler] Failed to log financial failure: {e}")


# Synchronous version for non-async functions
def with_retry_sync(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    transient_errors: Optional[Tuple[Type[Exception], ...]] = None,
    logs_path: Optional[Path] = None,
):
    """
    Synchronous version of with_retry decorator.

    Usage:
        @with_retry_sync(max_retries=3)
        def sync_api_call():
            ...
    """
    if transient_errors is None:
        transient_errors = DEFAULT_TRANSIENT_ERRORS

    import time

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            func_name = func.__name__

            # Check if this is a financial API
            if is_financial_api(func_name, args, kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.error(
                        f"[RetryHandler] Financial API call failed (no auto-retry): "
                        f"{func_name}: {e}"
                    )
                    raise FinancialAPIError(
                        f"Financial API call failed: {e}. Requires human approval."
                    ) from e

            last_error: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except transient_errors as e:
                    last_error = e

                    if attempt < max_retries:
                        delay = calculate_backoff(attempt, base_delay, max_delay, jitter)
                        logger.warning(
                            f"[RetryHandler] {func_name} failed (attempt {attempt + 1}/{max_retries + 1}): "
                            f"{e}. Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[RetryHandler] {func_name} failed after {max_retries + 1} attempts"
                        )

                except Exception as e:
                    if is_transient_error(e):
                        last_error = e
                        if attempt < max_retries:
                            delay = calculate_backoff(attempt, base_delay, max_delay, jitter)
                            logger.warning(
                                f"[RetryHandler] {func_name} transient error: {e}. "
                                f"Retrying in {delay:.1f}s..."
                            )
                            time.sleep(delay)
                        else:
                            last_error = e
                    else:
                        raise

            raise RetryExhaustedError(
                f"{func_name} failed after {max_retries + 1} attempts: {last_error}"
            ) from last_error

        return wrapper
    return decorator
