"""Compliance models for federal security requirements.

This module implements audit logging and compliance tracking models
aligned with STIG and NIST 800-53 requirements.
"""

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

import structlog

logger = structlog.get_logger('inventree')


class AuditEventType(models.TextChoices):
    """Audit event types aligned with STIG V-220635 and NIST AU-2."""

    # Authentication events (STIG V-220629)
    AUTH_SUCCESS = 'auth_success', _('Authentication Success')
    AUTH_FAILURE = 'auth_failure', _('Authentication Failure')
    AUTH_LOGOUT = 'auth_logout', _('User Logout')
    AUTH_LOCKOUT = 'auth_lockout', _('Account Lockout')

    # Authorization events (STIG V-220630)
    AUTHZ_SUCCESS = 'authz_success', _('Authorization Success')
    AUTHZ_FAILURE = 'authz_failure', _('Authorization Failure')

    # Data access events (STIG V-220635)
    DATA_CREATE = 'data_create', _('Data Created')
    DATA_READ = 'data_read', _('Data Read')
    DATA_UPDATE = 'data_update', _('Data Updated')
    DATA_DELETE = 'data_delete', _('Data Deleted')

    # Administrative events
    ADMIN_ACTION = 'admin_action', _('Administrative Action')
    CONFIG_CHANGE = 'config_change', _('Configuration Change')
    PERMISSION_CHANGE = 'permission_change', _('Permission Change')

    # System events
    SYSTEM_START = 'system_start', _('System Start')
    SYSTEM_STOP = 'system_stop', _('System Stop')
    SYSTEM_ERROR = 'system_error', _('System Error')

    # Compliance events
    COMPLIANCE_CHECK = 'compliance_check', _('Compliance Check')
    COMPLIANCE_VIOLATION = 'compliance_violation', _('Compliance Violation')


class AuditSeverity(models.TextChoices):
    """Audit event severity levels."""

    INFO = 'info', _('Information')
    WARNING = 'warning', _('Warning')
    ERROR = 'error', _('Error')
    CRITICAL = 'critical', _('Critical')


class AuditLog(models.Model):
    """Comprehensive audit logging for federal compliance.

    Implements STIG V-220635 (AU-2, AU-3) requirements for audit logging.
    All data modifications, user actions, and system events are logged
    with sufficient detail for forensic analysis.

    Attributes:
        timestamp: When the event occurred (auto-generated)
        event_type: Type of audit event (from AuditEventType choices)
        severity: Severity level of the event
        user: User who performed the action (if applicable)
        ip_address: IP address of the client
        user_agent: Browser/client user agent string
        content_type: Django ContentType for the affected model
        object_id: Primary key of the affected object
        content_object: Generic foreign key to the affected object
        action: Specific action performed (CREATE, UPDATE, DELETE, VIEW)
        old_values: JSON snapshot of values before change
        new_values: JSON snapshot of values after change
        reason: Optional reason/justification for the action
        session_id: Session identifier for correlation
        request_id: Request identifier for correlation
        success: Whether the action was successful
        error_message: Error message if action failed
    """

    class Meta:
        """Model meta options."""

        verbose_name = _('Audit Log')
        verbose_name_plural = _('Audit Logs')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['event_type']),
            models.Index(fields=['user']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['session_id']),
        ]

    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Timestamp'),
        help_text=_('When the event occurred'),
        db_index=True,
    )

    event_type = models.CharField(
        max_length=50,
        choices=AuditEventType.choices,
        verbose_name=_('Event Type'),
        help_text=_('Type of audit event'),
    )

    severity = models.CharField(
        max_length=20,
        choices=AuditSeverity.choices,
        default=AuditSeverity.INFO,
        verbose_name=_('Severity'),
        help_text=_('Severity level of the event'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name=_('User'),
        help_text=_('User who performed the action'),
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_('IP Address'),
        help_text=_('Client IP address'),
    )

    user_agent = models.TextField(
        blank=True,
        default='',
        verbose_name=_('User Agent'),
        help_text=_('Client user agent string'),
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Content Type'),
        help_text=_('Type of the affected model'),
    )

    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Object ID'),
        help_text=_('Primary key of the affected object'),
    )

    content_object = GenericForeignKey('content_type', 'object_id')

    action = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name=_('Action'),
        help_text=_('Specific action performed'),
    )

    old_values = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Old Values'),
        help_text=_('Values before the change'),
    )

    new_values = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('New Values'),
        help_text=_('Values after the change'),
    )

    reason = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Reason'),
        help_text=_('Reason or justification for the action'),
    )

    session_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('Session ID'),
        help_text=_('Session identifier for correlation'),
    )

    request_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('Request ID'),
        help_text=_('Request identifier for correlation'),
    )

    success = models.BooleanField(
        default=True,
        verbose_name=_('Success'),
        help_text=_('Whether the action was successful'),
    )

    error_message = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Error Message'),
        help_text=_('Error message if action failed'),
    )

    def __str__(self):
        """String representation of the audit log entry."""
        return f'{self.timestamp} - {self.event_type} - {self.user}'

    @classmethod
    def log_event(
        cls,
        event_type: str,
        user: User | None = None,
        severity: str = AuditSeverity.INFO,
        ip_address: str | None = None,
        user_agent: str = '',
        content_object=None,
        action: str = '',
        old_values: dict | None = None,
        new_values: dict | None = None,
        reason: str = '',
        session_id: str = '',
        request_id: str = '',
        success: bool = True,
        error_message: str = '',
    ):
        """Create an audit log entry.

        This is the primary method for creating audit log entries.
        It handles all the complexity of setting up the generic foreign key
        and ensures consistent logging format.

        Args:
            event_type: Type of audit event (from AuditEventType)
            user: User who performed the action
            severity: Severity level (from AuditSeverity)
            ip_address: Client IP address
            user_agent: Client user agent string
            content_object: The affected model instance
            action: Specific action performed
            old_values: Dict of values before change
            new_values: Dict of values after change
            reason: Reason/justification for the action
            session_id: Session identifier
            request_id: Request identifier
            success: Whether the action succeeded
            error_message: Error message if failed

        Returns:
            AuditLog: The created audit log entry
        """
        content_type = None
        object_id = None

        if content_object is not None:
            content_type = ContentType.objects.get_for_model(content_object)
            object_id = content_object.pk

        log_entry = cls.objects.create(
            event_type=event_type,
            severity=severity,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            content_type=content_type,
            object_id=object_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            reason=reason,
            session_id=session_id,
            request_id=request_id,
            success=success,
            error_message=error_message,
        )

        # Also log to structured logger for external aggregation
        logger.info(
            'audit_event',
            event_type=event_type,
            severity=severity,
            user_id=user.pk if user else None,
            ip_address=ip_address,
            content_type=str(content_type) if content_type else None,
            object_id=object_id,
            action=action,
            success=success,
        )

        return log_entry


class ComplianceStatus(models.TextChoices):
    """Compliance check status values."""

    COMPLIANT = 'compliant', _('Compliant')
    NON_COMPLIANT = 'non_compliant', _('Non-Compliant')
    PARTIAL = 'partial', _('Partially Compliant')
    NOT_APPLICABLE = 'not_applicable', _('Not Applicable')
    UNKNOWN = 'unknown', _('Unknown')


class ComplianceFramework(models.TextChoices):
    """Supported compliance frameworks."""

    STIG = 'stig', _('STIG')
    NIST_800_53 = 'nist_800_53', _('NIST 800-53')
    ISO_9001 = 'iso_9001', _('ISO 9001')
    CUSTOM = 'custom', _('Custom')


class ComplianceControl(models.Model):
    """Compliance control definition.

    Represents a specific compliance control from a framework
    (e.g., STIG V-220629, NIST AC-7).

    Attributes:
        framework: The compliance framework this control belongs to
        control_id: Unique identifier within the framework
        title: Human-readable title
        description: Detailed description of the control
        category: Control category/family
        severity: Severity if non-compliant
        check_function: Python path to the check function
        remediation_guidance: How to fix non-compliance
        references: External references and documentation
        enabled: Whether this control is actively checked
    """

    class Meta:
        """Model meta options."""

        verbose_name = _('Compliance Control')
        verbose_name_plural = _('Compliance Controls')
        ordering = ['framework', 'control_id']
        unique_together = [['framework', 'control_id']]

    framework = models.CharField(
        max_length=50,
        choices=ComplianceFramework.choices,
        verbose_name=_('Framework'),
        help_text=_('Compliance framework'),
    )

    control_id = models.CharField(
        max_length=50,
        verbose_name=_('Control ID'),
        help_text=_('Unique identifier within the framework'),
    )

    title = models.CharField(
        max_length=200, verbose_name=_('Title'), help_text=_('Human-readable title')
    )

    description = models.TextField(
        verbose_name=_('Description'),
        help_text=_('Detailed description of the control'),
    )

    category = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('Category'),
        help_text=_('Control category or family'),
    )

    severity = models.CharField(
        max_length=20,
        choices=AuditSeverity.choices,
        default=AuditSeverity.WARNING,
        verbose_name=_('Severity'),
        help_text=_('Severity if non-compliant'),
    )

    check_function = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name=_('Check Function'),
        help_text=_('Python path to the compliance check function'),
    )

    remediation_guidance = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Remediation Guidance'),
        help_text=_('How to fix non-compliance'),
    )

    references = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('References'),
        help_text=_('External references and documentation'),
    )

    enabled = models.BooleanField(
        default=True,
        verbose_name=_('Enabled'),
        help_text=_('Whether this control is actively checked'),
    )

    def __str__(self):
        """String representation of the compliance control."""
        return f'{self.framework} - {self.control_id}: {self.title}'


class ComplianceCheckResult(models.Model):
    """Result of a compliance check execution.

    Records the outcome of running a compliance check against
    the system at a specific point in time.

    Attributes:
        control: The compliance control that was checked
        timestamp: When the check was performed
        status: Result of the check
        details: Detailed findings
        evidence: Supporting evidence for the finding
        checked_by: User who initiated the check (if manual)
        remediation_notes: Notes on remediation actions taken
    """

    class Meta:
        """Model meta options."""

        verbose_name = _('Compliance Check Result')
        verbose_name_plural = _('Compliance Check Results')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['control', 'status']),
        ]

    control = models.ForeignKey(
        ComplianceControl,
        on_delete=models.CASCADE,
        related_name='check_results',
        verbose_name=_('Control'),
        help_text=_('The compliance control that was checked'),
    )

    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Timestamp'),
        help_text=_('When the check was performed'),
    )

    status = models.CharField(
        max_length=20,
        choices=ComplianceStatus.choices,
        verbose_name=_('Status'),
        help_text=_('Result of the compliance check'),
    )

    details = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Details'),
        help_text=_('Detailed findings from the check'),
    )

    evidence = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Evidence'),
        help_text=_('Supporting evidence for the finding'),
    )

    checked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='compliance_checks',
        verbose_name=_('Checked By'),
        help_text=_('User who initiated the check'),
    )

    remediation_notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Remediation Notes'),
        help_text=_('Notes on remediation actions taken'),
    )

    def __str__(self):
        """String representation of the compliance check result."""
        return f'{self.control.control_id} - {self.status} ({self.timestamp})'


class AccessControlViolation(models.Model):
    """Record of access control violations.

    Tracks segregation of duties violations and unauthorized
    access attempts for compliance reporting.

    Attributes:
        timestamp: When the violation occurred
        user: User involved in the violation
        violation_type: Type of access control violation
        resource: Resource that was accessed/attempted
        action_attempted: What action was attempted
        details: Additional details about the violation
        resolved: Whether the violation has been addressed
        resolution_notes: How the violation was resolved
        resolved_by: User who resolved the violation
        resolved_at: When the violation was resolved
    """

    class Meta:
        """Model meta options."""

        verbose_name = _('Access Control Violation')
        verbose_name_plural = _('Access Control Violations')
        ordering = ['-timestamp']

    VIOLATION_TYPES = [
        ('sod', _('Segregation of Duties')),
        ('unauthorized', _('Unauthorized Access')),
        ('privilege_escalation', _('Privilege Escalation')),
        ('excessive_permissions', _('Excessive Permissions')),
        ('other', _('Other')),
    ]

    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Timestamp'),
        help_text=_('When the violation occurred'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='access_violations',
        verbose_name=_('User'),
        help_text=_('User involved in the violation'),
    )

    violation_type = models.CharField(
        max_length=50,
        choices=VIOLATION_TYPES,
        verbose_name=_('Violation Type'),
        help_text=_('Type of access control violation'),
    )

    resource = models.CharField(
        max_length=255,
        verbose_name=_('Resource'),
        help_text=_('Resource that was accessed or attempted'),
    )

    action_attempted = models.CharField(
        max_length=100,
        verbose_name=_('Action Attempted'),
        help_text=_('What action was attempted'),
    )

    details = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Details'),
        help_text=_('Additional details about the violation'),
    )

    resolved = models.BooleanField(
        default=False,
        verbose_name=_('Resolved'),
        help_text=_('Whether the violation has been addressed'),
    )

    resolution_notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Resolution Notes'),
        help_text=_('How the violation was resolved'),
    )

    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_violations',
        verbose_name=_('Resolved By'),
        help_text=_('User who resolved the violation'),
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Resolved At'),
        help_text=_('When the violation was resolved'),
    )

    def __str__(self):
        """String representation of the access control violation."""
        return f'{self.violation_type} - {self.user} - {self.resource}'
