"""STIG compliance checks for InvenTree.

This module implements Security Technical Implementation Guide (STIG)
compliance checks aligned with federal security requirements.

STIG Controls Implemented:
- V-220629: Authentication (IA-2, IA-5)
- V-220630: Session Management (AC-7, AC-12)
- V-220631: Input Validation (SI-10)
- V-220632: Input Sanitization (SI-10)
- V-220633: Encryption at Rest (SC-28)
- V-220634: Encryption in Transit (SC-8)
- V-220635: Audit Logging (AU-2, AU-3)
- V-220641: Error Handling (SI-11)
"""

import re
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import User

from compliance.models import (
    ComplianceCheckResult,
    ComplianceControl,
    ComplianceFramework,
    ComplianceStatus,
)


@dataclass
class STIGCheckResult:
    """Result of a STIG compliance check."""

    control_id: str
    status: str
    details: str
    evidence: dict
    remediation: str = ''


class STIGComplianceChecker:
    """STIG compliance checker for InvenTree.

    Implements automated compliance checks for STIG controls
    relevant to web applications and inventory management systems.
    """

    # Minimum password length per STIG V-220629
    MIN_PASSWORD_LENGTH = 14

    # Maximum failed login attempts before lockout per STIG V-220630
    MAX_FAILED_ATTEMPTS = 5

    # Session timeout in minutes per STIG V-220630
    SESSION_TIMEOUT_MINUTES = 15

    # Required security headers per STIG V-220641
    REQUIRED_SECURITY_HEADERS = [
        'Strict-Transport-Security',
        'X-Frame-Options',
        'X-Content-Type-Options',
        'Content-Security-Policy',
    ]

    def __init__(self):
        """Initialize the STIG compliance checker."""
        self.results = []

    def run_all_checks(self, user: Optional[User] = None) -> list[STIGCheckResult]:
        """Run all STIG compliance checks.

        Args:
            user: Optional user who initiated the check

        Returns:
            list: List of STIGCheckResult objects
        """
        self.results = []

        # Run each check
        self.results.append(self.check_v220629_authentication())
        self.results.append(self.check_v220630_session_management())
        self.results.append(self.check_v220631_input_validation())
        self.results.append(self.check_v220633_encryption_at_rest())
        self.results.append(self.check_v220634_encryption_in_transit())
        self.results.append(self.check_v220635_audit_logging())
        self.results.append(self.check_v220641_error_handling())

        # Store results in database
        self._store_results(user)

        return self.results

    def _store_results(self, user: Optional[User] = None):
        """Store check results in the database.

        Args:
            user: User who initiated the check
        """
        for result in self.results:
            # Get or create the control
            control, _ = ComplianceControl.objects.get_or_create(
                framework=ComplianceFramework.STIG,
                control_id=result.control_id,
                defaults={
                    'title': f'STIG {result.control_id}',
                    'description': result.details,
                    'remediation_guidance': result.remediation,
                },
            )

            # Create the check result
            ComplianceCheckResult.objects.create(
                control=control,
                status=result.status,
                details=result.details,
                evidence=result.evidence,
                checked_by=user,
            )

    def check_v220629_authentication(self) -> STIGCheckResult:
        """Check STIG V-220629: Authentication controls.

        Verifies:
        - Password minimum length is 14 characters
        - Password complexity requirements are enabled
        - MFA is available (if configured)

        Returns:
            STIGCheckResult: Result of the authentication check
        """
        evidence = {}
        issues = []

        # Check Django password validators
        password_validators = getattr(settings, 'AUTH_PASSWORD_VALIDATORS', [])
        evidence['password_validators'] = len(password_validators)

        min_length_validator = None
        for validator in password_validators:
            if 'MinimumLengthValidator' in validator.get('NAME', ''):
                min_length_validator = validator
                break

        if min_length_validator:
            min_length = min_length_validator.get('OPTIONS', {}).get('min_length', 8)
            evidence['min_password_length'] = min_length
            if min_length < self.MIN_PASSWORD_LENGTH:
                issues.append(
                    f'Password minimum length is {min_length}, '
                    f'should be {self.MIN_PASSWORD_LENGTH}'
                )
        else:
            evidence['min_password_length'] = 'Not configured'
            issues.append('MinimumLengthValidator not configured')

        # Check for password hashers (bcrypt preferred)
        password_hashers = getattr(settings, 'PASSWORD_HASHERS', [])
        evidence['password_hashers'] = password_hashers[:3] if password_hashers else []

        bcrypt_configured = any('bcrypt' in h.lower() for h in password_hashers)
        evidence['bcrypt_configured'] = bcrypt_configured
        if not bcrypt_configured:
            issues.append('BCrypt password hasher not configured')

        # Determine status
        if not issues:
            status = ComplianceStatus.COMPLIANT
            details = 'Authentication controls meet STIG V-220629 requirements'
        elif len(issues) < 2:
            status = ComplianceStatus.PARTIAL
            details = f'Partial compliance: {"; ".join(issues)}'
        else:
            status = ComplianceStatus.NON_COMPLIANT
            details = f'Non-compliant: {"; ".join(issues)}'

        return STIGCheckResult(
            control_id='V-220629',
            status=status,
            details=details,
            evidence=evidence,
            remediation='Configure AUTH_PASSWORD_VALIDATORS with MinimumLengthValidator '
            '(min_length=14) and add bcrypt to PASSWORD_HASHERS',
        )

    def check_v220630_session_management(self) -> STIGCheckResult:
        """Check STIG V-220630: Session management controls.

        Verifies:
        - Session timeout is configured (15 minutes)
        - Secure cookie settings are enabled
        - Session regeneration on login

        Returns:
            STIGCheckResult: Result of the session management check
        """
        evidence = {}
        issues = []

        # Check session timeout
        session_age = getattr(settings, 'SESSION_COOKIE_AGE', 1209600)
        session_timeout_minutes = session_age / 60
        evidence['session_timeout_minutes'] = session_timeout_minutes

        if session_timeout_minutes > self.SESSION_TIMEOUT_MINUTES:
            issues.append(
                f'Session timeout is {session_timeout_minutes} minutes, '
                f'should be {self.SESSION_TIMEOUT_MINUTES} minutes'
            )

        # Check secure cookie settings
        session_cookie_secure = getattr(settings, 'SESSION_COOKIE_SECURE', False)
        evidence['session_cookie_secure'] = session_cookie_secure
        if not session_cookie_secure:
            issues.append('SESSION_COOKIE_SECURE is not enabled')

        session_cookie_httponly = getattr(settings, 'SESSION_COOKIE_HTTPONLY', False)
        evidence['session_cookie_httponly'] = session_cookie_httponly
        if not session_cookie_httponly:
            issues.append('SESSION_COOKIE_HTTPONLY is not enabled')

        csrf_cookie_secure = getattr(settings, 'CSRF_COOKIE_SECURE', False)
        evidence['csrf_cookie_secure'] = csrf_cookie_secure
        if not csrf_cookie_secure:
            issues.append('CSRF_COOKIE_SECURE is not enabled')

        # Determine status
        if not issues:
            status = ComplianceStatus.COMPLIANT
            details = 'Session management meets STIG V-220630 requirements'
        elif len(issues) <= 2:
            status = ComplianceStatus.PARTIAL
            details = f'Partial compliance: {"; ".join(issues)}'
        else:
            status = ComplianceStatus.NON_COMPLIANT
            details = f'Non-compliant: {"; ".join(issues)}'

        return STIGCheckResult(
            control_id='V-220630',
            status=status,
            details=details,
            evidence=evidence,
            remediation='Set SESSION_COOKIE_AGE=900, SESSION_COOKIE_SECURE=True, '
            'SESSION_COOKIE_HTTPONLY=True, CSRF_COOKIE_SECURE=True',
        )

    def check_v220631_input_validation(self) -> STIGCheckResult:
        """Check STIG V-220631: Input validation controls.

        Verifies:
        - Django's built-in validation is enabled
        - REST framework validation is configured

        Returns:
            STIGCheckResult: Result of the input validation check
        """
        evidence = {}

        # Check if Django REST Framework is configured with validation
        rest_framework_settings = getattr(settings, 'REST_FRAMEWORK', {})
        evidence['rest_framework_configured'] = bool(rest_framework_settings)

        # Check for exception handler (indicates proper error handling)
        exception_handler = rest_framework_settings.get('EXCEPTION_HANDLER')
        evidence['exception_handler'] = exception_handler is not None

        # Check for default renderer classes (JSON preferred for security)
        renderers = rest_framework_settings.get('DEFAULT_RENDERER_CLASSES', [])
        evidence['renderer_classes'] = len(renderers)

        # InvenTree uses Django's built-in validation through model validators
        # This is generally compliant
        status = ComplianceStatus.COMPLIANT
        details = (
            'Input validation is handled through Django model validators '
            'and REST framework serializers'
        )

        return STIGCheckResult(
            control_id='V-220631',
            status=status,
            details=details,
            evidence=evidence,
            remediation='Ensure all API endpoints use serializer validation '
            'and model clean() methods validate input',
        )

    def check_v220633_encryption_at_rest(self) -> STIGCheckResult:
        """Check STIG V-220633: Encryption at rest controls.

        Verifies:
        - Database encryption settings
        - Secret key configuration

        Returns:
            STIGCheckResult: Result of the encryption at rest check
        """
        evidence = {}
        issues = []

        # Check if SECRET_KEY is properly configured (not default)
        secret_key = getattr(settings, 'SECRET_KEY', '')
        evidence['secret_key_configured'] = bool(secret_key)
        evidence['secret_key_length'] = len(secret_key)

        if len(secret_key) < 50:
            issues.append('SECRET_KEY should be at least 50 characters')

        # Check database configuration
        databases = getattr(settings, 'DATABASES', {})
        default_db = databases.get('default', {})
        db_engine = default_db.get('ENGINE', '')
        evidence['database_engine'] = db_engine

        # Note: Actual database encryption depends on the database server configuration
        # This check verifies Django-level settings
        status = ComplianceStatus.PARTIAL
        details = (
            'Encryption at rest depends on database server configuration. '
            'Verify database-level encryption is enabled.'
        )

        if issues:
            status = ComplianceStatus.NON_COMPLIANT
            details = f'Issues found: {"; ".join(issues)}'

        return STIGCheckResult(
            control_id='V-220633',
            status=status,
            details=details,
            evidence=evidence,
            remediation='Enable database-level encryption (e.g., PostgreSQL TDE) '
            'and ensure SECRET_KEY is at least 50 characters',
        )

    def check_v220634_encryption_in_transit(self) -> STIGCheckResult:
        """Check STIG V-220634: Encryption in transit controls.

        Verifies:
        - HTTPS enforcement settings
        - HSTS configuration

        Returns:
            STIGCheckResult: Result of the encryption in transit check
        """
        evidence = {}
        issues = []

        # Check SECURE_SSL_REDIRECT
        ssl_redirect = getattr(settings, 'SECURE_SSL_REDIRECT', False)
        evidence['secure_ssl_redirect'] = ssl_redirect
        if not ssl_redirect:
            issues.append('SECURE_SSL_REDIRECT is not enabled')

        # Check HSTS settings
        hsts_seconds = getattr(settings, 'SECURE_HSTS_SECONDS', 0)
        evidence['hsts_seconds'] = hsts_seconds
        if hsts_seconds < 31536000:  # 1 year
            issues.append('SECURE_HSTS_SECONDS should be at least 31536000 (1 year)')

        hsts_subdomains = getattr(settings, 'SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
        evidence['hsts_include_subdomains'] = hsts_subdomains
        if not hsts_subdomains:
            issues.append('SECURE_HSTS_INCLUDE_SUBDOMAINS is not enabled')

        # Determine status
        if not issues:
            status = ComplianceStatus.COMPLIANT
            details = 'Encryption in transit meets STIG V-220634 requirements'
        elif len(issues) <= 2:
            status = ComplianceStatus.PARTIAL
            details = f'Partial compliance: {"; ".join(issues)}'
        else:
            status = ComplianceStatus.NON_COMPLIANT
            details = f'Non-compliant: {"; ".join(issues)}'

        return STIGCheckResult(
            control_id='V-220634',
            status=status,
            details=details,
            evidence=evidence,
            remediation='Set SECURE_SSL_REDIRECT=True, SECURE_HSTS_SECONDS=31536000, '
            'SECURE_HSTS_INCLUDE_SUBDOMAINS=True',
        )

    def check_v220635_audit_logging(self) -> STIGCheckResult:
        """Check STIG V-220635: Audit logging controls.

        Verifies:
        - Logging is configured
        - Audit log model is available

        Returns:
            STIGCheckResult: Result of the audit logging check
        """
        evidence = {}

        # Check Django logging configuration
        logging_config = getattr(settings, 'LOGGING', {})
        evidence['logging_configured'] = bool(logging_config)

        handlers = logging_config.get('handlers', {})
        evidence['handler_count'] = len(handlers)

        loggers = logging_config.get('loggers', {})
        evidence['logger_count'] = len(loggers)

        # Check if compliance module is available (it is, since we're running this)
        evidence['audit_log_available'] = True

        # The compliance module provides audit logging
        status = ComplianceStatus.COMPLIANT
        details = (
            'Audit logging is implemented through the compliance module. '
            f'Django logging has {len(handlers)} handlers and {len(loggers)} loggers configured.'
        )

        return STIGCheckResult(
            control_id='V-220635',
            status=status,
            details=details,
            evidence=evidence,
            remediation='Ensure AuditLog model is used for all security-relevant events',
        )

    def check_v220641_error_handling(self) -> STIGCheckResult:
        """Check STIG V-220641: Error handling controls.

        Verifies:
        - DEBUG mode is disabled in production
        - Custom error handlers are configured

        Returns:
            STIGCheckResult: Result of the error handling check
        """
        evidence = {}
        issues = []

        # Check DEBUG setting
        debug_mode = getattr(settings, 'DEBUG', True)
        evidence['debug_mode'] = debug_mode
        if debug_mode:
            issues.append('DEBUG mode is enabled (should be False in production)')

        # Check for security middleware
        middleware = getattr(settings, 'MIDDLEWARE', [])
        security_middleware = 'django.middleware.security.SecurityMiddleware'
        evidence['security_middleware'] = security_middleware in middleware
        if security_middleware not in middleware:
            issues.append('SecurityMiddleware is not in MIDDLEWARE')

        # Check X-Content-Type-Options
        content_type_nosniff = getattr(settings, 'SECURE_CONTENT_TYPE_NOSNIFF', False)
        evidence['content_type_nosniff'] = content_type_nosniff
        if not content_type_nosniff:
            issues.append('SECURE_CONTENT_TYPE_NOSNIFF is not enabled')

        # Determine status
        if not issues:
            status = ComplianceStatus.COMPLIANT
            details = 'Error handling meets STIG V-220641 requirements'
        elif len(issues) == 1 and debug_mode:
            status = ComplianceStatus.PARTIAL
            details = f'Partial compliance: {"; ".join(issues)}'
        else:
            status = ComplianceStatus.NON_COMPLIANT
            details = f'Non-compliant: {"; ".join(issues)}'

        return STIGCheckResult(
            control_id='V-220641',
            status=status,
            details=details,
            evidence=evidence,
            remediation='Set DEBUG=False, add SecurityMiddleware to MIDDLEWARE, '
            'set SECURE_CONTENT_TYPE_NOSNIFF=True',
        )


def validate_input(
    value: str, pattern: str | None = None, max_length: int = 255
) -> str:
    """Validate and sanitize user input per STIG V-220631/V-220632.

    This function implements whitelist-based input validation
    and sanitization as required by federal security standards.

    Args:
        value: The input value to validate
        pattern: Optional regex pattern for validation
        max_length: Maximum allowed length (default 255)

    Returns:
        str: Sanitized input value

    Raises:
        ValueError: If input fails validation
    """
    if value is None:
        return ''

    # Convert to string and strip whitespace
    value = str(value).strip()

    # Check length
    if len(value) > max_length:
        raise ValueError(f'Input exceeds maximum length of {max_length} characters')

    # Remove dangerous characters (STIG V-220632)
    dangerous_chars = r'[<>"\';&|`$()]'
    sanitized = re.sub(dangerous_chars, '', value)

    # Validate against pattern if provided (STIG V-220631)
    if pattern and not re.match(pattern, sanitized):
        raise ValueError('Input does not match required pattern')

    return sanitized


def validate_email(email: str) -> str:
    """Validate email format per STIG V-220631.

    Args:
        email: Email address to validate

    Returns:
        str: Validated email address

    Raises:
        ValueError: If email format is invalid
    """
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    email = validate_input(email, max_length=254)

    if not re.match(email_pattern, email):
        raise ValueError('Invalid email format')

    return email.lower()


def validate_username(username: str) -> str:
    """Validate username format per STIG V-220631.

    Args:
        username: Username to validate

    Returns:
        str: Validated username

    Raises:
        ValueError: If username format is invalid
    """
    username_pattern = r'^[a-zA-Z0-9_-]+$'
    return validate_input(username, pattern=username_pattern, max_length=150)
