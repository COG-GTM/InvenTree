"""REST API endpoints for the compliance module.

This module provides API endpoints for:
- Viewing audit logs
- Running compliance checks
- Managing compliance controls
- Viewing access control violations
"""

from django.utils.translation import gettext_lazy as _

from django_filters import rest_framework as django_filters
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from InvenTree.filters import SEARCH_ORDER_FILTER
from InvenTree.mixins import ListAPI, RetrieveAPI

from .models import (
    AccessControlViolation,
    AuditLog,
    ComplianceCheckResult,
    ComplianceControl,
)
from .serializers import (
    AccessControlViolationSerializer,
    AuditLogSerializer,
    ComplianceCheckResultSerializer,
    ComplianceControlSerializer,
)
from .stig import STIGComplianceChecker


class AuditLogFilter(django_filters.FilterSet):
    """Filter for AuditLog queryset."""

    timestamp_after = django_filters.DateTimeFilter(
        field_name='timestamp', lookup_expr='gte'
    )
    timestamp_before = django_filters.DateTimeFilter(
        field_name='timestamp', lookup_expr='lte'
    )

    class Meta:
        """Filter options."""

        model = AuditLog
        fields = ['event_type', 'severity', 'user', 'success']


class AuditLogList(ListAPI):
    """API endpoint for listing audit log entries.

    Provides read-only access to audit logs for compliance reporting.
    Only users with appropriate permissions can view audit logs.
    """

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    filterset_class = AuditLogFilter
    permission_classes = [permissions.IsAdminUser]

    filter_backends = SEARCH_ORDER_FILTER

    ordering_fields = ['timestamp', 'event_type', 'severity', 'user']
    ordering = '-timestamp'

    search_fields = ['event_type', 'action', 'reason', 'error_message']


class AuditLogDetail(RetrieveAPI):
    """API endpoint for retrieving a single audit log entry."""

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAdminUser]


class ComplianceControlFilter(django_filters.FilterSet):
    """Filter for ComplianceControl queryset."""

    class Meta:
        """Filter options."""

        model = ComplianceControl
        fields = ['framework', 'category', 'severity', 'enabled']


class ComplianceControlList(ListAPI):
    """API endpoint for listing compliance controls."""

    queryset = ComplianceControl.objects.all()
    serializer_class = ComplianceControlSerializer
    filterset_class = ComplianceControlFilter
    permission_classes = [permissions.IsAdminUser]

    filter_backends = SEARCH_ORDER_FILTER

    ordering_fields = ['framework', 'control_id', 'title', 'severity']
    ordering = ['framework', 'control_id']

    search_fields = ['control_id', 'title', 'description', 'category']


class ComplianceControlDetail(RetrieveAPI):
    """API endpoint for retrieving a single compliance control."""

    queryset = ComplianceControl.objects.all()
    serializer_class = ComplianceControlSerializer
    permission_classes = [permissions.IsAdminUser]


class ComplianceCheckResultFilter(django_filters.FilterSet):
    """Filter for ComplianceCheckResult queryset."""

    timestamp_after = django_filters.DateTimeFilter(
        field_name='timestamp', lookup_expr='gte'
    )
    timestamp_before = django_filters.DateTimeFilter(
        field_name='timestamp', lookup_expr='lte'
    )

    class Meta:
        """Filter options."""

        model = ComplianceCheckResult
        fields = ['control', 'status', 'checked_by']


class ComplianceCheckResultList(ListAPI):
    """API endpoint for listing compliance check results."""

    queryset = ComplianceCheckResult.objects.all()
    serializer_class = ComplianceCheckResultSerializer
    filterset_class = ComplianceCheckResultFilter
    permission_classes = [permissions.IsAdminUser]

    filter_backends = SEARCH_ORDER_FILTER

    ordering_fields = ['timestamp', 'status', 'control']
    ordering = '-timestamp'

    search_fields = ['details', 'remediation_notes']

    @action(detail=False, methods=['post'])
    def run_stig_checks(self, request):
        """Run all STIG compliance checks.

        This endpoint triggers a full STIG compliance assessment
        and stores the results in the database.
        """
        checker = STIGComplianceChecker()
        results = checker.run_all_checks(user=request.user)

        return Response(
            {
                'message': _('STIG compliance checks completed'),
                'results': [
                    {
                        'control_id': r.control_id,
                        'status': r.status,
                        'details': r.details,
                    }
                    for r in results
                ],
            },
            status=status.HTTP_200_OK,
        )


class ComplianceCheckResultDetail(RetrieveAPI):
    """API endpoint for retrieving a single compliance check result."""

    queryset = ComplianceCheckResult.objects.all()
    serializer_class = ComplianceCheckResultSerializer
    permission_classes = [permissions.IsAdminUser]


class AccessControlViolationFilter(django_filters.FilterSet):
    """Filter for AccessControlViolation queryset."""

    timestamp_after = django_filters.DateTimeFilter(
        field_name='timestamp', lookup_expr='gte'
    )
    timestamp_before = django_filters.DateTimeFilter(
        field_name='timestamp', lookup_expr='lte'
    )

    class Meta:
        """Filter options."""

        model = AccessControlViolation
        fields = ['violation_type', 'user', 'resolved']


class AccessControlViolationList(ListAPI):
    """API endpoint for listing access control violations."""

    queryset = AccessControlViolation.objects.all()
    serializer_class = AccessControlViolationSerializer
    filterset_class = AccessControlViolationFilter
    permission_classes = [permissions.IsAdminUser]

    filter_backends = SEARCH_ORDER_FILTER

    ordering_fields = ['timestamp', 'violation_type', 'user', 'resolved']
    ordering = '-timestamp'

    search_fields = ['resource', 'action_attempted', 'details']


class AccessControlViolationDetail(RetrieveAPI):
    """API endpoint for retrieving a single access control violation."""

    queryset = AccessControlViolation.objects.all()
    serializer_class = AccessControlViolationSerializer
    permission_classes = [permissions.IsAdminUser]
