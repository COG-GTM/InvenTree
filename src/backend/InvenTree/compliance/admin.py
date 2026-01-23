"""Django admin configuration for the compliance module."""

from django.contrib import admin

from .models import (
    AccessControlViolation,
    AuditLog,
    ComplianceCheckResult,
    ComplianceControl,
)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin configuration for AuditLog model."""

    list_display = ['timestamp', 'event_type', 'severity', 'user', 'action', 'success']
    list_filter = ['event_type', 'severity', 'success', 'timestamp']
    search_fields = ['user__username', 'action', 'reason', 'error_message']
    readonly_fields = [
        'timestamp',
        'event_type',
        'severity',
        'user',
        'ip_address',
        'user_agent',
        'content_type',
        'object_id',
        'action',
        'old_values',
        'new_values',
        'reason',
        'session_id',
        'request_id',
        'success',
        'error_message',
    ]
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        """Prevent manual creation of audit logs."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent modification of audit logs."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of audit logs."""
        return False


@admin.register(ComplianceControl)
class ComplianceControlAdmin(admin.ModelAdmin):
    """Admin configuration for ComplianceControl model."""

    list_display = [
        'control_id',
        'framework',
        'title',
        'category',
        'severity',
        'enabled',
    ]
    list_filter = ['framework', 'category', 'severity', 'enabled']
    search_fields = ['control_id', 'title', 'description']
    ordering = ['framework', 'control_id']


@admin.register(ComplianceCheckResult)
class ComplianceCheckResultAdmin(admin.ModelAdmin):
    """Admin configuration for ComplianceCheckResult model."""

    list_display = ['timestamp', 'control', 'status', 'checked_by']
    list_filter = ['status', 'control__framework', 'timestamp']
    search_fields = ['control__control_id', 'details', 'remediation_notes']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'


@admin.register(AccessControlViolation)
class AccessControlViolationAdmin(admin.ModelAdmin):
    """Admin configuration for AccessControlViolation model."""

    list_display = ['timestamp', 'user', 'violation_type', 'resource', 'resolved']
    list_filter = ['violation_type', 'resolved', 'timestamp']
    search_fields = ['user__username', 'resource', 'action_attempted', 'details']
    date_hierarchy = 'timestamp'
