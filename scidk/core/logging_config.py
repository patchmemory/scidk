"""Centralized logging configuration for SciDK.

Provides structured logging with rotation to prevent disk exhaustion.
"""
import logging
import logging.handlers
import os
from pathlib import Path


def setup_logging(log_dir: str = 'logs', log_level: str = 'INFO'):
    """Configure structured logging for SciDK.

    Args:
        log_dir: Directory to store log files (default: 'logs')
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Get configuration from environment with defaults
    max_size_mb = int(os.environ.get('SCIDK_LOG_MAX_SIZE_MB', '50'))
    backup_count = int(os.environ.get('SCIDK_LOG_BACKUP_COUNT', '10'))

    # Rotating file handler (prevents unbounded growth)
    handler = logging.handlers.RotatingFileHandler(
        log_path / 'scidk.log',
        maxBytes=max_size_mb * 1024 * 1024,  # Convert MB to bytes
        backupCount=backup_count
    )

    # Structured format: [TIMESTAMP] [LEVEL] [SOURCE] MESSAGE
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Add file handler
    logger.addHandler(handler)

    # Also log to console for development/debugging
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    logger.info(f"Logging configured: level={log_level}, dir={log_dir}, max_size={max_size_mb}MB, backups={backup_count}")

    return logger
