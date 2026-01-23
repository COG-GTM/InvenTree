"""Tests for the compliance module.

This module provides unit tests for compliance functionality including
audit logging, STIG compliance checks, and access control validation.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from compliance.models import (
    AccessControlViolation,
    AuditEventType,
    AuditLog,
    AuditSeverity,
    ComplianceCheckResult,
    ComplianceControl,
    ComplianceFramework,
    ComplianceStatus,
)
from compliance.stig import (
    STIGComplianceChecker,
    validate_email,
    validate_input,
    validate_username,
)


class AuditLogModelTest(TestCase):
    """Tests for the AuditLog model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='testpassword123'
        )

    def test_create_audit_log(self):
        """Test creating an audit log entry."""
        log = AuditLog.log_event(
            event_type=AuditEventType.AUTH_SUCCESS,
            user=self.user,
            severity=AuditSeverity.INFO,
            ip_address='192.168.1.1',
            action='LOGIN',
        )

        self.assertIsNotNone(log.pk)
        self.assertEqual(log.event_type, AuditEventType.AUTH_SUCCESS)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.ip_address, '192.168.1.1')
        self.assertEqual(log.action, 'LOGIN')
        self.assertTrue(log.success)

    def test_audit_log_with_content_object(self):
        """Test audit log with a generic foreign key."""
        log = AuditLog.log_event(
            event_type=AuditEventType.DATA_UPDATE,
            user=self.user,
            content_object=self.user,
            action='UPDATE',
            old_values={'email': 'old@example.com'},
            new_values={'email': 'new@example.com'},
        )

        self.assertIsNotNone(log.content_type)
        self.assertEqual(log.object_id, self.user.pk)
        self.assertEqual(log.old_values['email'], 'old@example.com')
        self.assertEqual(log.new_values['email'], 'new@example.com')

    def test_audit_log_failure(self):
        """Test logging a failed action."""
        log = AuditLog.log_event(
            event_type=AuditEventType.AUTH_FAILURE,
            severity=AuditSeverity.WARNING,
            ip_address='10.0.0.1',
            action='LOGIN_FAILED',
            success=False,
            error_message='Invalid credentials',
        )

        self.assertFalse(log.success)
        self.assertEqual(log.error_message, 'Invalid credentials')
        self.assertEqual(log.severity, AuditSeverity.WARNING)

    def test_audit_log_str(self):
        """Test string representation of audit log."""
        log = AuditLog.log_event(event_type=AuditEventType.AUTH_SUCCESS, user=self.user)

        str_repr = str(log)
        self.assertIn(AuditEventType.AUTH_SUCCESS, str_repr)


class ComplianceControlModelTest(TestCase):
    """Tests for the ComplianceControl model."""

    def test_create_compliance_control(self):
        """Test creating a compliance control."""
        control = ComplianceControl.objects.create(
            framework=ComplianceFramework.STIG,
            control_id='V-220629',
            title='Authentication Controls',
            description='Verify authentication mechanisms',
            category='Authentication',
            severity=AuditSeverity.CRITICAL,
        )

        self.assertIsNotNone(control.pk)
        self.assertEqual(control.framework, ComplianceFramework.STIG)
        self.assertEqual(control.control_id, 'V-220629')
        self.assertTrue(control.enabled)

    def test_compliance_control_str(self):
        """Test string representation of compliance control."""
        control = ComplianceControl.objects.create(
            framework=ComplianceFramework.STIG,
            control_id='V-220630',
            title='Session Management',
            description='Verify session controls',
        )

        str_repr = str(control)
        self.assertIn('STIG', str_repr)
        self.assertIn('V-220630', str_repr)


class ComplianceCheckResultModelTest(TestCase):
    """Tests for the ComplianceCheckResult model."""

    def setUp(self):
        """Set up test data."""
        self.control = ComplianceControl.objects.create(
            framework=ComplianceFramework.STIG,
            control_id='V-220635',
            title='Audit Logging',
            description='Verify audit logging',
        )
        self.user = User.objects.create_user(
            username='auditor', password='testpassword123'
        )

    def test_create_check_result(self):
        """Test creating a compliance check result."""
        result = ComplianceCheckResult.objects.create(
            control=self.control,
            status=ComplianceStatus.COMPLIANT,
            details='All audit logging requirements met',
            checked_by=self.user,
        )

        self.assertIsNotNone(result.pk)
        self.assertEqual(result.status, ComplianceStatus.COMPLIANT)
        self.assertEqual(result.control, self.control)

    def test_check_result_with_evidence(self):
        """Test check result with evidence data."""
        evidence = {'logging_configured': True, 'handler_count': 3, 'logger_count': 5}

        result = ComplianceCheckResult.objects.create(
            control=self.control,
            status=ComplianceStatus.COMPLIANT,
            details='Audit logging verified',
            evidence=evidence,
        )

        self.assertEqual(result.evidence['logging_configured'], True)
        self.assertEqual(result.evidence['handler_count'], 3)


class AccessControlViolationModelTest(TestCase):
    """Tests for the AccessControlViolation model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='violator', password='testpassword123'
        )

    def test_create_violation(self):
        """Test creating an access control violation."""
        violation = AccessControlViolation.objects.create(
            user=self.user,
            violation_type='unauthorized',
            resource='/api/admin/users/',
            action_attempted='DELETE',
            details='User attempted to delete admin account',
        )

        self.assertIsNotNone(violation.pk)
        self.assertEqual(violation.violation_type, 'unauthorized')
        self.assertFalse(violation.resolved)

    def test_resolve_violation(self):
        """Test resolving a violation."""
        resolver = User.objects.create_user(
            username='admin', password='testpassword123'
        )

        violation = AccessControlViolation.objects.create(
            user=self.user,
            violation_type='sod',
            resource='Purchase Order Approval',
            action_attempted='APPROVE',
        )

        violation.resolved = True
        violation.resolved_by = resolver
        violation.resolution_notes = 'User permissions corrected'
        violation.save()

        violation.refresh_from_db()
        self.assertTrue(violation.resolved)
        self.assertEqual(violation.resolved_by, resolver)


class STIGComplianceCheckerTest(TestCase):
    """Tests for the STIG compliance checker."""

    def test_checker_initialization(self):
        """Test checker initializes correctly."""
        checker = STIGComplianceChecker()
        self.assertEqual(checker.results, [])

    @override_settings(
        AUTH_PASSWORD_VALIDATORS=[
            {
                'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
                'OPTIONS': {'min_length': 14},
            }
        ],
        PASSWORD_HASHERS=['django.contrib.auth.hashers.BCryptSHA256PasswordHasher'],
    )
    def test_check_v220629_compliant(self):
        """Test V-220629 check with compliant settings."""
        checker = STIGComplianceChecker()
        result = checker.check_v220629_authentication()

        self.assertEqual(result.control_id, 'V-220629')
        # Should be compliant or partial with these settings
        self.assertIn(
            result.status, [ComplianceStatus.COMPLIANT, ComplianceStatus.PARTIAL]
        )

    @override_settings(
        SESSION_COOKIE_AGE=900,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        CSRF_COOKIE_SECURE=True,
    )
    def test_check_v220630_compliant(self):
        """Test V-220630 check with compliant settings."""
        checker = STIGComplianceChecker()
        result = checker.check_v220630_session_management()

        self.assertEqual(result.control_id, 'V-220630')
        self.assertEqual(result.status, ComplianceStatus.COMPLIANT)

    def test_check_v220631_input_validation(self):
        """Test V-220631 input validation check."""
        checker = STIGComplianceChecker()
        result = checker.check_v220631_input_validation()

        self.assertEqual(result.control_id, 'V-220631')
        # Django provides built-in validation
        self.assertEqual(result.status, ComplianceStatus.COMPLIANT)

    def test_check_v220635_audit_logging(self):
        """Test V-220635 audit logging check."""
        checker = STIGComplianceChecker()
        result = checker.check_v220635_audit_logging()

        self.assertEqual(result.control_id, 'V-220635')
        # Compliance module provides audit logging
        self.assertEqual(result.status, ComplianceStatus.COMPLIANT)

    @override_settings(DEBUG=False)
    def test_check_v220641_debug_disabled(self):
        """Test V-220641 check with DEBUG disabled."""
        checker = STIGComplianceChecker()
        result = checker.check_v220641_error_handling()

        self.assertEqual(result.control_id, 'V-220641')
        # Should be more compliant with DEBUG=False
        self.assertIn(
            result.status, [ComplianceStatus.COMPLIANT, ComplianceStatus.PARTIAL]
        )


class InputValidationTest(TestCase):
    """Tests for input validation functions."""

    def test_validate_input_basic(self):
        """Test basic input validation."""
        result = validate_input('Hello World')
        self.assertEqual(result, 'Hello World')

    def test_validate_input_strips_whitespace(self):
        """Test that whitespace is stripped."""
        result = validate_input('  test  ')
        self.assertEqual(result, 'test')

    def test_validate_input_removes_dangerous_chars(self):
        """Test that dangerous characters are removed."""
        result = validate_input('test<script>alert(1)</script>')
        self.assertNotIn('<', result)
        self.assertNotIn('>', result)

    def test_validate_input_max_length(self):
        """Test max length enforcement."""
        with self.assertRaises(ValueError):
            validate_input('a' * 300, max_length=255)

    def test_validate_input_pattern(self):
        """Test pattern validation."""
        result = validate_input('abc123', pattern=r'^[a-z0-9]+$')
        self.assertEqual(result, 'abc123')

        with self.assertRaises(ValueError):
            validate_input('ABC', pattern=r'^[a-z]+$')

    def test_validate_email_valid(self):
        """Test valid email validation."""
        result = validate_email('test@example.com')
        self.assertEqual(result, 'test@example.com')

    def test_validate_email_invalid(self):
        """Test invalid email validation."""
        with self.assertRaises(ValueError):
            validate_email('not-an-email')

    def test_validate_username_valid(self):
        """Test valid username validation."""
        result = validate_username('test_user-123')
        self.assertEqual(result, 'test_user-123')

    def test_validate_username_invalid(self):
        """Test invalid username validation."""
        with self.assertRaises(ValueError):
            validate_username('test user')  # Contains space
