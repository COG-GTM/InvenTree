"""Signal handlers for compliance audit logging.

This module provides automatic audit logging for model changes
by connecting to Django's post_save and post_delete signals.
"""

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from compliance.models import AuditEventType, AuditLog, AuditSeverity


def get_client_ip(request):
    """Extract client IP address from request.

    Handles X-Forwarded-For header for proxied requests.

    Args:
        request: Django HTTP request object

    Returns:
        str: Client IP address or None
    """
    if request is None:
        return None

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_user_agent(request):
    """Extract user agent from request.

    Args:
        request: Django HTTP request object

    Returns:
        str: User agent string or empty string
    """
    if request is None:
        return ''
    return request.META.get('HTTP_USER_AGENT', '')


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log successful user authentication.

    Implements STIG V-220629 requirement for authentication logging.
    """
    AuditLog.log_event(
        event_type=AuditEventType.AUTH_SUCCESS,
        user=user,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        action='LOGIN',
        session_id=request.session.session_key if request.session else '',
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log user logout.

    Implements STIG V-220629 requirement for authentication logging.
    """
    AuditLog.log_event(
        event_type=AuditEventType.AUTH_LOGOUT,
        user=user,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        action='LOGOUT',
        session_id=request.session.session_key if request.session else '',
    )


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    """Log failed authentication attempts.

    Implements STIG V-220629 requirement for authentication failure logging.
    This is critical for detecting brute force attacks and unauthorized access attempts.
    """
    AuditLog.log_event(
        event_type=AuditEventType.AUTH_FAILURE,
        severity=AuditSeverity.WARNING,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_user_agent(request) if request else '',
        action='LOGIN_FAILED',
        new_values={'username': credentials.get('username', 'unknown')},
        success=False,
        error_message='Authentication failed',
    )


class AuditLogMixin:
    """Mixin to add audit logging to model classes.

    Add this mixin to any model class to automatically log
    create, update, and delete operations.

    Example:
        class MyModel(AuditLogMixin, models.Model):
            name = models.CharField(max_length=100)

    The mixin will automatically log:
    - Object creation (DATA_CREATE)
    - Object updates (DATA_UPDATE) with old and new values
    - Object deletion (DATA_DELETE)
    """

    # Fields to exclude from audit logging (e.g., sensitive data)
    audit_exclude_fields = []

    # Fields to include in audit logging (if set, only these fields are logged)
    audit_include_fields = None

    def _get_audit_fields(self):
        """Get the list of fields to include in audit logging.

        Returns:
            list: Field names to include in audit logs
        """
        if self.audit_include_fields is not None:
            return self.audit_include_fields

        fields = []
        for field in self._meta.fields:
            if field.name not in self.audit_exclude_fields:
                if field.name not in ['id', 'pk']:
                    fields.append(field.name)
        return fields

    def _get_field_values(self):
        """Get current values of auditable fields.

        Returns:
            dict: Field name to value mapping
        """
        values = {}
        for field_name in self._get_audit_fields():
            try:
                value = getattr(self, field_name)
                # Convert non-serializable values to strings
                if hasattr(value, 'pk'):
                    value = value.pk
                elif hasattr(value, 'isoformat'):
                    value = value.isoformat()
                values[field_name] = value
            except AttributeError:
                pass
        return values

    def save(self, *args, **kwargs):
        """Override save to log create/update operations."""
        is_new = self.pk is None

        # Get old values for update comparison
        old_values = None
        if not is_new:
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
                old_values = old_instance._get_field_values()
            except self.__class__.DoesNotExist:
                is_new = True

        # Perform the actual save
        super().save(*args, **kwargs)

        # Get new values after save
        new_values = self._get_field_values()

        # Log the event
        if is_new:
            AuditLog.log_event(
                event_type=AuditEventType.DATA_CREATE,
                content_object=self,
                action='CREATE',
                new_values=new_values,
            )
        else:
            # Only log if values actually changed
            if old_values != new_values:
                AuditLog.log_event(
                    event_type=AuditEventType.DATA_UPDATE,
                    content_object=self,
                    action='UPDATE',
                    old_values=old_values,
                    new_values=new_values,
                )

    def delete(self, *args, **kwargs):
        """Override delete to log deletion operations."""
        old_values = self._get_field_values()

        AuditLog.log_event(
            event_type=AuditEventType.DATA_DELETE,
            content_object=self,
            action='DELETE',
            old_values=old_values,
        )

        super().delete(*args, **kwargs)
