"""Serializers for the compliance module.

This module provides DRF serializers for compliance-related models.
"""

from rest_framework import serializers

from .models import (
    AccessControlViolation,
    AuditLog,
    ComplianceCheckResult,
    ComplianceControl,
)


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer for AuditLog model."""

    user_display = serializers.SerializerMethodField()
    content_type_display = serializers.SerializerMethodField()

    class Meta:
        """Serializer options."""

        model = AuditLog
        fields = [
            'id',
            'timestamp',
            'event_type',
            'severity',
            'user',
            'user_display',
            'ip_address',
            'user_agent',
            'content_type',
            'content_type_display',
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
        read_only_fields = fields

    def get_user_display(self, obj):
        """Get display name for the user."""
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return None

    def get_content_type_display(self, obj):
        """Get display name for the content type."""
        if obj.content_type:
            return f'{obj.content_type.app_label}.{obj.content_type.model}'
        return None


class ComplianceControlSerializer(serializers.ModelSerializer):
    """Serializer for ComplianceControl model."""

    latest_check_status = serializers.SerializerMethodField()

    class Meta:
        """Serializer options."""

        model = ComplianceControl
        fields = [
            'id',
            'framework',
            'control_id',
            'title',
            'description',
            'category',
            'severity',
            'check_function',
            'remediation_guidance',
            'references',
            'enabled',
            'latest_check_status',
        ]
        read_only_fields = ['id', 'latest_check_status']

    def get_latest_check_status(self, obj):
        """Get the status from the most recent compliance check."""
        latest = obj.check_results.order_by('-timestamp').first()
        if latest:
            return {
                'status': latest.status,
                'timestamp': latest.timestamp,
                'details': latest.details,
            }
        return None


class ComplianceCheckResultSerializer(serializers.ModelSerializer):
    """Serializer for ComplianceCheckResult model."""

    control_display = serializers.SerializerMethodField()
    checked_by_display = serializers.SerializerMethodField()

    class Meta:
        """Serializer options."""

        model = ComplianceCheckResult
        fields = [
            'id',
            'control',
            'control_display',
            'timestamp',
            'status',
            'details',
            'evidence',
            'checked_by',
            'checked_by_display',
            'remediation_notes',
        ]
        read_only_fields = ['id', 'timestamp', 'control_display', 'checked_by_display']

    def get_control_display(self, obj):
        """Get display name for the control."""
        return (
            f'{obj.control.framework} - {obj.control.control_id}: {obj.control.title}'
        )

    def get_checked_by_display(self, obj):
        """Get display name for the user who ran the check."""
        if obj.checked_by:
            return obj.checked_by.get_full_name() or obj.checked_by.username
        return 'System'


class AccessControlViolationSerializer(serializers.ModelSerializer):
    """Serializer for AccessControlViolation model."""

    user_display = serializers.SerializerMethodField()
    resolved_by_display = serializers.SerializerMethodField()

    class Meta:
        """Serializer options."""

        model = AccessControlViolation
        fields = [
            'id',
            'timestamp',
            'user',
            'user_display',
            'violation_type',
            'resource',
            'action_attempted',
            'details',
            'resolved',
            'resolution_notes',
            'resolved_by',
            'resolved_by_display',
            'resolved_at',
        ]
        read_only_fields = ['id', 'timestamp', 'user_display', 'resolved_by_display']

    def get_user_display(self, obj):
        """Get display name for the user."""
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return None

    def get_resolved_by_display(self, obj):
        """Get display name for the user who resolved the violation."""
        if obj.resolved_by:
            return obj.resolved_by.get_full_name() or obj.resolved_by.username
        return None
