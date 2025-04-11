#!/usr/bin/env python3
"""
Error Handling Module for SSB Build Server Web.

This module provides centralized error handling, standardized error formatting,
consistent logging, and recovery strategies for the application.

It defines common error types, decorators for robust function execution,
and utilities for consistent error presentation to users.
"""
import os
import sys
import time
import json
import traceback
import functools
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union, TypeVar

# Import configuration if available
try:
    from config import config
except ImportError:
    config = None

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('error_handler')

# Get error handling configuration
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', '3')) if not config else config.get_int('MAX_RETRIES', 3)
RETRY_DELAY = int(os.environ.get('RETRY_DELAY', '2')) if not config else config.get_int('RETRY_DELAY', 2)
ERROR_LOG_FILE = os.environ.get('ERROR_LOG_FILE', 'error.log') if not config else config.get('ERROR_LOG_FILE', 'error.log')

# Type variable for function return
T = TypeVar('T')

class AppError(Exception):
    """Base class for application-specific errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_error: Optional[Exception] = None):
        """
        Initialize a new application error.
        
        Args:
            message: Human-readable error message
            details: Additional details about the error (optional)
            original_error: The original exception that caused this error (optional)
        """
        self.message = message
        self.details = details or {}
        self.original_error = original_error
        
        # Include the original error class in the details if available
        if original_error is not None:
            self.details['original_error_type'] = original_error.__class__.__name__
            
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the error to a dictionary for JSON serialization."""
        error_dict = {
            'error': True,
            'error_type': self.__class__.__name__,
            'message': self.message
        }
        
        if self.details:
            error_dict['details'] = self.details
        
        return error_dict
    
    def log(self, log_level: int = logging.ERROR):
        """Log the error with appropriate level and details."""
        log_message = f"{self.__class__.__name__}: {self.message}"
        
        if self.original_error:
            log_message += f" (Original error: {self.original_error})"
            
        logger.log(log_level, log_message)
        
        if self.details:
            logger.log(log_level, f"Error details: {json.dumps(self.details, default=str)}")
        
        if self.original_error and hasattr(self.original_error, '__traceback__'):
            tb_str = ''.join(traceback.format_exception(
                type(self.original_error), 
                self.original_error, 
                self.original_error.__traceback__
            ))
            logger.log(log_level, f"Original traceback:\n{tb_str}")
            
        # Also log to file if configured
        self._log_to_file(log_message)
    
    def _log_to_file(self, message: str):
        """Log the error to a dedicated error log file."""
        try:
            if ERROR_LOG_FILE:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                with open(ERROR_LOG_FILE, 'a') as f:
                    f.write(f"[{timestamp}] {message}\n")
                    
                    # Add original traceback if available
                    if self.original_error and hasattr(self.original_error, '__traceback__'):
                        tb_str = ''.join(traceback.format_exception(
                            type(self.original_error), 
                            self.original_error, 
                            self.original_error.__traceback__
                        ))
                        f.write(f"Traceback:\n{tb_str}\n")
                        
                    f.write("-" * 80 + "\n")
        except Exception as e:
            # Don't raise more errors when handling errors
            logger.warning(f"Error writing to log file: {str(e)}")
            
    def __str__(self) -> str:
        """User-friendly string representation of the error."""
        return self.message

# Specific error types

class ConfigurationError(AppError):
    """Error related to configuration issues."""
    pass

class AuthenticationError(AppError):
    """Error related to authentication issues."""
    pass

class AuthorizationError(AppError):
    """Error related to authorization issues."""
    pass

class ValidationError(AppError):
    """Error related to data validation issues."""
    pass

class ResourceNotFoundError(AppError):
    """Error related to resource not found issues."""
    pass

class AtlantisError(AppError):
    """Error related to Atlantis API communication."""
    pass

class TerraformError(AppError):
    """Error related to Terraform execution."""
    pass

class VSphereError(AppError):
    """Error related to VMware vSphere communication."""
    pass

class NetBoxError(AppError):
    """Error related to NetBox communication."""
    pass

class FileOperationError(AppError):
    """Error related to file operations."""
    pass

class ConcurrencyError(AppError):
    """Error related to concurrency issues."""
    pass

# Decorators for robust function execution

def retry(max_retries: int = MAX_RETRIES, delay: int = RETRY_DELAY, 
          allowed_exceptions: Tuple[Type[Exception], ...] = (Exception,),
          retry_on_result: Optional[Callable[[Any], bool]] = None,
          retry_if: Optional[Callable[..., bool]] = None) -> Callable:
    """
    Retry decorator for robust function execution.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Delay between retries in seconds
        allowed_exceptions: Tuple of exception types to retry on
        retry_on_result: Function that takes the result and returns True if retry is needed
        retry_if: Function that takes the function args and returns True if retry is needed
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            retries = 0
            
            while True:
                try:
                    # Check if retry is needed based on function arguments
                    if retry_if and not retry_if(*args, **kwargs):
                        return func(*args, **kwargs)
                    
                    # Execute the function
                    result = func(*args, **kwargs)
                    
                    # Check if retry is needed based on result
                    if retry_on_result and retry_on_result(result):
                        if retries >= max_retries:
                            return result
                        retries += 1
                        logger.info(f"Retrying {func.__name__} (attempt {retries}/{max_retries}) due to result check")
                        time.sleep(delay)
                        continue
                    
                    # Success!
                    return result
                    
                except allowed_exceptions as e:
                    if retries >= max_retries:
                        if isinstance(e, AppError):
                            # Re-raise application errors directly
                            raise
                        else:
                            # Convert other exceptions to AppError
                            error_type = 'Unknown'
                            for error_class in [VSphereError, AtlantisError, TerraformError, NetBoxError]:
                                if error_class.__name__.lower() in func.__name__.lower():
                                    error_type = error_class.__name__
                                    break
                            
                            app_error = globals().get(error_type, AppError)(
                                message=f"Error in {func.__name__}: {str(e)}",
                                original_error=e
                            )
                            app_error.log()
                            raise app_error
                            
                    # Retry
                    retries += 1
                    logger.warning(f"Retrying {func.__name__} (attempt {retries}/{max_retries}) after error: {str(e)}")
                    time.sleep(delay)
        
        return wrapper
    
    return decorator

def robust_operation(error_type: Type[AppError] = AppError, error_message: str = "Operation failed",
                     default_return: Any = None) -> Callable:
    """
    Decorator for robust operation execution with customizable error handling.
    
    Args:
        error_type: Type of AppError to raise
        error_message: Error message to use
        default_return: Default value to return on error
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if isinstance(e, AppError):
                    # Re-raise application errors directly
                    raise
                
                # Convert other exceptions to specified AppError type
                app_error = error_type(
                    message=f"{error_message}: {str(e)}",
                    details={'function': func.__name__},
                    original_error=e
                )
                app_error.log()
                
                # Return default value if provided, otherwise raise the error
                if default_return is not None:
                    return default_return
                
                raise app_error
                
        return wrapper
    
    return decorator

def validate_inputs(**param_validators) -> Callable:
    """
    Decorator for input validation.
    
    Args:
        **param_validators: Dictionary of parameter names and validation functions
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Get function signature parameters
            func_name = func.__name__
            
            # Check positional arguments by parameter name
            # (this requires knowing the parameter names in order)
            # For class methods, skip 'self' or 'cls'
            param_names = list(param_validators.keys())
            start_idx = 1 if args and (func.__code__.co_varnames[0] in ('self', 'cls')) else 0
            
            # Validate positional args
            for i, arg in enumerate(args[start_idx:], start=start_idx):
                if i < len(func.__code__.co_varnames):
                    param_name = func.__code__.co_varnames[i]
                    if param_name in param_validators:
                        validator = param_validators[param_name]
                        if not validator(arg):
                            raise ValidationError(
                                f"Invalid value for parameter '{param_name}' in {func_name}",
                                {'parameter': param_name, 'value': arg}
                            )
            
            # Validate keyword args
            for param_name, arg in kwargs.items():
                if param_name in param_validators:
                    validator = param_validators[param_name]
                    if not validator(arg):
                        raise ValidationError(
                            f"Invalid value for parameter '{param_name}' in {func_name}",
                            {'parameter': param_name, 'value': arg}
                        )
            
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator

# Common validation functions

def is_non_empty_string(value):
    """Validate that a value is a non-empty string."""
    return isinstance(value, str) and len(value.strip()) > 0

def is_positive_int(value):
    """Validate that a value is a positive integer."""
    return isinstance(value, int) and value > 0

def is_valid_email(value):
    """Validate that a value is a valid email address."""
    import re
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    return isinstance(value, str) and bool(email_pattern.match(value))

def is_valid_ip(value):
    """Validate that a value is a valid IP address."""
    import ipaddress
    try:
        ipaddress.ip_address(value)
        return True
    except (ValueError, TypeError):
        return False

def is_within_range(min_val, max_val):
    """Create a validator for a value within a range."""
    def validator(value):
        return min_val <= value <= max_val
    return validator

def matches_pattern(pattern):
    """Create a validator for a string matching a regex pattern."""
    import re
    compiled_pattern = re.compile(pattern)
    def validator(value):
        return isinstance(value, str) and bool(compiled_pattern.match(value))
    return validator

def is_valid_uuid(value):
    """Validate that a value is a valid UUID."""
    import re
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
    return isinstance(value, str) and bool(uuid_pattern.match(value.lower()))

# Error response utility functions

def format_error_response(error: Union[AppError, Exception], include_traceback: bool = False) -> Dict[str, Any]:
    """
    Format an error for API response.
    
    Args:
        error: The error to format
        include_traceback: Whether to include the traceback in the response
        
    Returns:
        Dictionary with error information
    """
    if isinstance(error, AppError):
        response = error.to_dict()
    else:
        response = {
            'error': True,
            'error_type': error.__class__.__name__,
            'message': str(error)
        }
    
    if include_traceback:
        response['traceback'] = traceback.format_exc()
    
    return response

def create_flash_message(error: Union[AppError, Exception]) -> Tuple[str, str]:
    """
    Create a flash message for UI display from an error.
    
    Args:
        error: The error to format
        
    Returns:
        Tuple of (message, category)
    """
    if isinstance(error, ValidationError):
        return f"Validation error: {error.message}", "error"
    elif isinstance(error, AuthenticationError):
        return f"Authentication error: {error.message}", "error"
    elif isinstance(error, AuthorizationError):
        return f"Authorization error: {error.message}", "error"
    elif isinstance(error, ResourceNotFoundError):
        return f"Resource not found: {error.message}", "error"
    elif isinstance(error, AtlantisError):
        return f"Atlantis error: {error.message}", "error"
    elif isinstance(error, TerraformError):
        return f"Terraform error: {error.message}", "error"
    elif isinstance(error, VSphereError):
        return f"vSphere error: {error.message}", "error"
    elif isinstance(error, NetBoxError):
        return f"NetBox error: {error.message}", "error"
    elif isinstance(error, FileOperationError):
        return f"File operation error: {error.message}", "error"
    elif isinstance(error, ConfigurationError):
        return f"Configuration error: {error.message}", "error"
    else:
        return f"Error: {str(error)}", "error"

# Add context information to exceptions
class error_context:
    """Context manager for adding context to exceptions."""
    
    def __init__(self, context: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize the context manager.
        
        Args:
            context: Context description
            details: Additional details to include
        """
        self.context = context
        self.details = details or {}
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            if isinstance(exc_val, AppError):
                # Add context to existing app error
                exc_val.message = f"{self.context}: {exc_val.message}"
                exc_val.details.update(self.details)
            else:
                # Convert to AppError with context
                app_error = AppError(
                    message=f"{self.context}: {str(exc_val)}",
                    details=self.details,
                    original_error=exc_val
                )
                app_error.log()
                raise app_error from exc_val
            
            return False  # Don't suppress the exception
        
        return False  # Don't suppress any exceptions
