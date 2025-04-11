#!/usr/bin/env python3
"""
Enhanced Logging Module for SSB Build Server Web.

This module provides standardized logging configuration with the following features:
- Consistent log formatting across the application
- Log rotation for file-based logs
- Different log levels for different components
- Context-based logging for request tracking
- Performance metrics logging
- Color-coded console output for better readability
- JSON formatted logs for machine parsing

Usage:
    from logger import get_logger
    
    # Get a logger for a specific component
    logger = get_logger('component_name')
    
    # Log messages at different levels
    logger.debug('Debug message')
    logger.info('Info message')
    logger.warning('Warning message')
    logger.error('Error message')
    logger.critical('Critical message')
    
    # Log with extra context
    logger.info('User logged in', extra={'user_id': 123, 'ip_address': '192.168.1.1'})
    
    # Use performance timer
    with logger.timer('operation_name'):
        # Do something time-consuming
        time.sleep(1)
"""
import os
import sys
import time
import json
import logging
import logging.handlers
import threading
import traceback
import contextlib
from datetime import datetime
from typing import Any, Dict, Optional, Union, List

# Import configuration if available
try:
    from config import config
except ImportError:
    config = None

# Get logging configuration from environment variables or config
def get_config_value(key, default):
    """Get configuration value from config module or environment variables."""
    if config:
        return config.get(key, default)
    else:
        return os.environ.get(key, default)

# Logging configuration
LOG_LEVEL = get_config_value('LOG_LEVEL', 'INFO').upper()
LOG_FORMAT = get_config_value('LOG_FORMAT', 'standard')  # 'standard', 'json', or 'simple'
LOG_FILE = get_config_value('LOG_FILE', None)
LOG_MAX_SIZE = int(get_config_value('LOG_MAX_SIZE', 10 * 1024 * 1024))  # 10 MB
LOG_BACKUP_COUNT = int(get_config_value('LOG_BACKUP_COUNT', 5))
LOG_COLORS = get_config_value('LOG_COLORS', 'true').lower() in ('true', 'yes', 'y', '1')

# Thread-local storage for request context
_thread_local = threading.local()

# ANSI color codes for colored console output
COLORS = {
    'grey': '\033[90m',
    'blue': '\033[94m',
    'green': '\033[92m',
    'yellow': '\033[93m',
    'red': '\033[91m',
    'magenta': '\033[95m',
    'bold': '\033[1m',
    'underline': '\033[4m',
    'reset': '\033[0m'
}

# Map log levels to colors
LEVEL_COLORS = {
    'DEBUG': COLORS['grey'],
    'INFO': COLORS['green'],
    'WARNING': COLORS['yellow'],
    'ERROR': COLORS['red'],
    'CRITICAL': COLORS['red'] + COLORS['bold']
}

class ColorFormatter(logging.Formatter):
    """Formatter that adds colors to log messages in console output."""
    
    def __init__(self, fmt=None, datefmt=None, style='%', use_colors=True):
        super().__init__(fmt, datefmt, style)
        self.use_colors = use_colors
    
    def format(self, record):
        """Format log record with colors."""
        # Get the original formatted message
        msg = super().format(record)
        
        if self.use_colors and record.levelname in LEVEL_COLORS:
            # Add color codes
            level_color = LEVEL_COLORS[record.levelname]
            return f"{level_color}{msg}{COLORS['reset']}"
        
        return msg

class JsonFormatter(logging.Formatter):
    """Formatter that outputs log records as JSON."""
    
    def format(self, record):
        """Format log record as JSON."""
        # Create a JSON object with standard fields
        json_record = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add thread and process IDs if available
        if hasattr(record, 'thread'):
            json_record['thread'] = record.thread
        if hasattr(record, 'process'):
            json_record['process'] = record.process
        
        # Add traceback information if available
        if record.exc_info:
            json_record['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields from the record
        if hasattr(record, 'context'):
            json_record['context'] = record.context
        
        # Add any other custom attributes
        for key, value in record.__dict__.items():
            if key not in ('args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
                          'funcName', 'id', 'levelname', 'levelno', 'lineno',
                          'module', 'msecs', 'message', 'msg', 'name', 'pathname',
                          'process', 'processName', 'relativeCreated', 'stack_info',
                          'thread', 'threadName', 'context'):
                json_record[key] = value
        
        return json.dumps(json_record)

class ContextAdapter(logging.LoggerAdapter):
    """Logger adapter that adds context information to log records."""
    
    def process(self, msg, kwargs):
        """Process log message to add context."""
        # Get extra dict from kwargs or create a new one
        kwargs.setdefault('extra', {})
        
        # Add context from thread local storage
        context = getattr(_thread_local, 'context', {})
        kwargs['extra']['context'] = context
        
        return msg, kwargs
    
    @contextlib.contextmanager
    def timer(self, operation_name):
        """Context manager for timing operations and logging the duration."""
        start_time = time.time()
        try:
            yield
        finally:
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            self.info(f"{operation_name} completed in {duration_ms:.2f}ms",
                    extra={'duration_ms': duration_ms, 'operation': operation_name})

def setup_logging():
    """Set up logging configuration."""
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set log level
    log_level = getattr(logging, LOG_LEVEL, logging.INFO)
    root_logger.setLevel(log_level)
    
    # Define formatters based on the selected format
    format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    if LOG_FORMAT == 'simple':
        format_string = '%(levelname)s: %(message)s'
    
    # Create and configure console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    if LOG_FORMAT == 'json':
        console_formatter = JsonFormatter()
    else:
        console_formatter = ColorFormatter(format_string, use_colors=LOG_COLORS)
    
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Create and configure file handler if LOG_FILE is specified
    if LOG_FILE:
        try:
            # Create directory for log file if it doesn't exist
            log_dir = os.path.dirname(LOG_FILE)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            # Use a rotating file handler to prevent logs from growing too large
            file_handler = logging.handlers.RotatingFileHandler(
                LOG_FILE,
                maxBytes=LOG_MAX_SIZE,
                backupCount=LOG_BACKUP_COUNT
            )
            file_handler.setLevel(log_level)
            
            if LOG_FORMAT == 'json':
                file_formatter = JsonFormatter()
            else:
                file_formatter = logging.Formatter(format_string)
            
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
            
        except Exception as e:
            # Log to console if file handler setup fails
            console_handler.setLevel(logging.WARNING)
            root_logger.warning(f"Failed to set up file logging: {str(e)}")
    
    # Silence noisy loggers
    for logger_name in ['urllib3', 'requests', 'werkzeug']:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    return root_logger

# Set up logging when the module is imported
setup_logging()

def get_logger(name):
    """
    Get a logger with the specified name.
    
    Args:
        name: Name of the logger (typically the module name)
        
    Returns:
        Logger with context adapter
    """
    logger = logging.getLogger(name)
    return ContextAdapter(logger, {})

def set_context(**kwargs):
    """
    Set context attributes for the current thread.
    
    Args:
        **kwargs: Context attributes to set
    """
    if not hasattr(_thread_local, 'context'):
        _thread_local.context = {}
    
    _thread_local.context.update(kwargs)

def clear_context():
    """Clear all context attributes for the current thread."""
    _thread_local.context = {}

def get_context():
    """Get the current context dictionary."""
    if not hasattr(_thread_local, 'context'):
        _thread_local.context = {}
    
    return _thread_local.context.copy()

@contextlib.contextmanager
def context(**kwargs):
    """
    Context manager for temporarily setting context attributes.
    
    Args:
        **kwargs: Context attributes to set
    """
    old_context = get_context()
    try:
        set_context(**kwargs)
        yield
    finally:
        # Restore old context
        clear_context()
        set_context(**old_context)

@contextlib.contextmanager
def log_errors(logger, error_message="An error occurred", log_level=logging.ERROR, reraise=True):
    """
    Context manager for logging exceptions.
    
    Args:
        logger: Logger to use
        error_message: Message to log when an error occurs
        log_level: Level to log at
        reraise: Whether to re-raise the exception after logging
    """
    try:
        yield
    except Exception as e:
        exc_info = sys.exc_info()
        logger.log(log_level, f"{error_message}: {str(e)}", exc_info=exc_info)
        if reraise:
            raise

def log_function_call(logger):
    """
    Decorator for logging function calls.
    
    Args:
        logger: Logger to use
        
    Returns:
        Decorator function
    """
    def decorator(func):
        @contextlib.wraps(func)
        def wrapper(*args, **kwargs):
            # Log function call
            arg_str = ', '.join([repr(a) for a in args] + [f"{k}={repr(v)}" for k, v in kwargs.items()])
            logger.debug(f"Calling {func.__name__}({arg_str})")
            
            # Time the function call
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000
                
                # Log result
                logger.debug(f"{func.__name__} returned {repr(result)} in {duration_ms:.2f}ms")
                return result
            except Exception as e:
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000
                
                # Log exception
                logger.error(f"{func.__name__} raised {type(e).__name__}: {str(e)} after {duration_ms:.2f}ms",
                           exc_info=True)
                raise
                
        return wrapper
    
    return decorator

# Create a default application logger
app_logger = get_logger('app')
