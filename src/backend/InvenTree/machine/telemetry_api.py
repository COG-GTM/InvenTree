"""REST API endpoints for Machine Telemetry System.

This module implements the REST API for the BEP MES machine telemetry system,
enabling Industry 4.0 equipment integration and real-time monitoring.

BEP MES Contract Alignment:
==========================
This API directly addresses the following BEP MES contract requirements:

1. MANUFACTURING TEAM FOCUS AREA:
   - Goal: "Integrate Industry 4.0 technologies - smart automation and advanced analytics"
   - Key Outcome: "Create new screen press connection to the BEP machine network"
   - This API provides the REST interface for equipment-to-MES communication

2. ENTERPRISE DATA & PERFORMANCE MANAGEMENT:
   - Goal: "Enable data-driven decisions"
   - Key Outcome: "Automated, controlled process that ingests, cleans, validates"
   - API endpoints include validation and threshold checking

3. DATA ANALYTICS FOCUS AREA:
   - Goal: "Deliver advanced insights"
   - Key Outcome: "Publish dashboards and predictive models"
   - Summary and status endpoints provide data for dashboards

4. AI AGILE TEAM FOCUS AREA:
   - Goal: "Drive innovation with AI"
   - Key Outcome: "AI model analyzed past runs and suggested changes"
   - Historical telemetry data enables AI/ML model training

API Endpoints:
=============
Machine Telemetry:
- GET  /api/machine/<pk>/telemetry/           - List telemetry data for a machine
- POST /api/machine/<pk>/telemetry/           - Submit telemetry data
- POST /api/machine/<pk>/telemetry/bulk/      - Bulk submit telemetry data
- GET  /api/machine/<pk>/telemetry/summary/   - Get telemetry summary statistics

Machine Alerts:
- GET  /api/machine/<pk>/alerts/              - List alerts for a machine
- GET  /api/machine/<pk>/alerts/<alert_pk>/   - Get alert details
- POST /api/machine/<pk>/alerts/<alert_pk>/acknowledge/ - Acknowledge alert
- POST /api/machine/<pk>/alerts/<alert_pk>/resolve/     - Resolve alert

Machine Thresholds:
- GET  /api/machine/<pk>/thresholds/          - List thresholds for a machine
- POST /api/machine/<pk>/thresholds/          - Create threshold
- GET  /api/machine/<pk>/thresholds/<th_pk>/  - Get threshold details
- PUT  /api/machine/<pk>/thresholds/<th_pk>/  - Update threshold
- DELETE /api/machine/<pk>/thresholds/<th_pk>/ - Delete threshold

Machine Status:
- GET  /api/machine/<pk>/status/              - Get comprehensive machine status
"""

from decimal import Decimal

from django.db.models import Avg, Count, Max, Min
from django.urls import include, path
from django.utils import timezone

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

import InvenTree.permissions
from InvenTree.mixins import ListCreateAPI, RetrieveUpdateDestroyAPI
from machine.api import get_machine
from machine.models import MachineConfig
from machine.telemetry_models import (
    AlertSeverity,
    AlertStatus,
    MachineAlert,
    MachineTelemetryData,
    MachineTelemetryThreshold,
    TelemetryDataType,
)
from machine.telemetry_serializers import (
    MachineAlertAcknowledgeSerializer,
    MachineAlertResolveSerializer,
    MachineAlertSerializer,
    MachineStatusSerializer,
    MachineTelemetryBulkCreateSerializer,
    MachineTelemetryDataCreateSerializer,
    MachineTelemetryDataSerializer,
    MachineTelemetrySummarySerializer,
    MachineTelemetryThresholdSerializer,
)


class MachineTelemetryList(APIView):
    """API endpoint for machine telemetry data.

    GET: Retrieve telemetry data for a specific machine
    POST: Submit new telemetry data from equipment

    BEP MES Contract Alignment:
    - Manufacturing Team: Enables "IT integration for full traceability"
    - Enterprise Data: Supports "automated, controlled process that ingests" data
    - Data Analytics: Provides historical data for "predictive models"

    Query Parameters (GET):
    - data_type: Filter by telemetry data type (e.g., TEMP, PRES)
    - start_date: Filter records after this datetime
    - end_date: Filter records before this datetime
    - quality_flag: Filter by data quality (GOOD, UNC, BAD)
    - limit: Maximum number of records to return (default 100, max 1000)
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        parameters=[
            OpenApiParameter('data_type', str, description='Filter by telemetry data type'),
            OpenApiParameter('start_date', str, description='Filter records after this datetime (ISO 8601)'),
            OpenApiParameter('end_date', str, description='Filter records before this datetime (ISO 8601)'),
            OpenApiParameter('quality_flag', str, description='Filter by data quality (GOOD, UNC, BAD)'),
            OpenApiParameter('limit', int, description='Maximum records to return (default 100, max 1000)'),
        ],
        responses={200: MachineTelemetryDataSerializer(many=True)}
    )
    def get(self, request, pk):
        """Retrieve telemetry data for a machine.

        Returns historical telemetry data with optional filtering.
        Supports the BEP MES requirement for "data-driven decisions"
        by providing access to equipment operational data.
        """
        get_machine(pk)  # Validate machine exists

        # Build queryset with filters
        queryset = MachineTelemetryData.objects.filter(machine__pk=pk)

        # Filter by data type
        data_type = request.query_params.get('data_type')
        if data_type:
            queryset = queryset.filter(data_type=data_type)

        # Filter by date range
        start_date = request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)

        end_date = request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)

        # Filter by quality flag
        quality_flag = request.query_params.get('quality_flag')
        if quality_flag:
            queryset = queryset.filter(quality_flag=quality_flag)

        # Apply limit
        limit = min(int(request.query_params.get('limit', 100)), 1000)
        queryset = queryset[:limit]

        serializer = MachineTelemetryDataSerializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=MachineTelemetryDataCreateSerializer,
        responses={201: MachineTelemetryDataSerializer}
    )
    def post(self, request, pk):
        """Submit telemetry data from equipment.

        Accepts telemetry data from manufacturing equipment and stores it
        in the MES database. Automatically checks configured thresholds
        and generates alerts for violations.

        BEP MES Contract Alignment:
        - Manufacturing Team: "Create new screen press connection to the BEP machine network"
        - Enterprise Data: "Ingests, cleans, validates" data
        - Data Analytics: Enables "forecast throughput, quality issues, and equipment failures"

        Request Body:
        {
            "data_type": "TEMP",
            "value": 72.5,
            "unit": "F",
            "timestamp": "2024-01-15T10:30:00Z",  // optional, defaults to now
            "quality_flag": "GOOD",  // optional, defaults to GOOD
            "metadata": {"batch_id": "B001", "operator": "John"}  // optional
        }
        """
        # Get machine config
        try:
            machine_config = MachineConfig.objects.get(pk=pk)
        except MachineConfig.DoesNotExist:
            raise NotFound(detail=f"Machine '{pk}' not found")

        # Validate and create telemetry data
        serializer = MachineTelemetryDataCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create the telemetry record
        telemetry = MachineTelemetryData.objects.create(
            machine=machine_config,
            **serializer.validated_data
        )

        # Check thresholds and create alerts if needed
        self._check_thresholds(telemetry)

        # Return the created record
        response_serializer = MachineTelemetryDataSerializer(telemetry)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def _check_thresholds(self, telemetry: MachineTelemetryData) -> None:
        """Check telemetry value against configured thresholds.

        If a threshold violation is detected, creates a MachineAlert.
        This supports the BEP MES requirement for "proactive action"
        through automated anomaly detection.
        """
        try:
            threshold = MachineTelemetryThreshold.objects.get(
                machine=telemetry.machine,
                data_type=telemetry.data_type,
                enabled=True
            )
        except MachineTelemetryThreshold.DoesNotExist:
            return  # No threshold configured

        is_violation, message, severity = threshold.check_value(telemetry.value)

        if is_violation and message and severity:
            MachineAlert.objects.create(
                machine=telemetry.machine,
                telemetry_data=telemetry,
                severity=severity,
                alert_type=MachineAlert.AlertType.THRESHOLD,
                title=f"Threshold violation: {telemetry.get_data_type_display()}",
                description=message,
                threshold_value=threshold.max_value if telemetry.value > (threshold.max_value or Decimal('0')) else threshold.min_value,
                actual_value=telemetry.value,
            )


class MachineTelemetryBulkCreate(APIView):
    """API endpoint for bulk telemetry data ingestion.

    POST: Submit multiple telemetry data points in a single request

    BEP MES Contract Alignment:
    - Manufacturing Team: Enables high-volume data collection from equipment
    - Enterprise Data: Supports "automated, controlled process that ingests" data
    - Data Analytics: Enables real-time data collection for "predictive models"

    This endpoint is optimized for Industry 4.0 equipment that generates
    high-frequency telemetry data, supporting the BEP MES requirement for
    "smart automation and advanced analytics."
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        request=MachineTelemetryBulkCreateSerializer,
        responses={201: MachineTelemetryDataSerializer(many=True)}
    )
    def post(self, request, pk):
        """Bulk submit telemetry data from equipment.

        Accepts up to 1000 telemetry data points in a single request
        for efficient high-volume data ingestion.

        Request Body:
        {
            "data": [
                {"data_type": "TEMP", "value": 72.5, "unit": "F"},
                {"data_type": "PRES", "value": 100.2, "unit": "PSI"},
                ...
            ]
        }
        """
        # Get machine config
        try:
            machine_config = MachineConfig.objects.get(pk=pk)
        except MachineConfig.DoesNotExist:
            raise NotFound(detail=f"Machine '{pk}' not found")

        # Validate request
        serializer = MachineTelemetryBulkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create telemetry records
        created_records = []
        now = timezone.now()

        for item in serializer.validated_data['data']:
            telemetry = MachineTelemetryData.objects.create(
                machine=machine_config,
                data_type=item['data_type'],
                value=Decimal(str(item['value'])),
                unit=item.get('unit', ''),
                timestamp=item.get('timestamp', now),
                quality_flag=item.get('quality_flag', MachineTelemetryData.QualityFlag.GOOD),
                metadata=item.get('metadata', {}),
            )
            created_records.append(telemetry)

            # Check thresholds (simplified for bulk - could be optimized)
            self._check_threshold(telemetry)

        response_serializer = MachineTelemetryDataSerializer(created_records, many=True)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def _check_threshold(self, telemetry: MachineTelemetryData) -> None:
        """Check a single telemetry value against thresholds."""
        try:
            threshold = MachineTelemetryThreshold.objects.get(
                machine=telemetry.machine,
                data_type=telemetry.data_type,
                enabled=True
            )
        except MachineTelemetryThreshold.DoesNotExist:
            return

        is_violation, message, severity = threshold.check_value(telemetry.value)

        if is_violation and message and severity:
            MachineAlert.objects.create(
                machine=telemetry.machine,
                telemetry_data=telemetry,
                severity=severity,
                alert_type=MachineAlert.AlertType.THRESHOLD,
                title=f"Threshold violation: {telemetry.get_data_type_display()}",
                description=message,
                actual_value=telemetry.value,
            )


class MachineTelemetrySummary(APIView):
    """API endpoint for telemetry summary statistics.

    GET: Retrieve aggregated telemetry statistics for a machine

    BEP MES Contract Alignment:
    - Data Analytics: Supports "publish dashboards" requirement
    - Enterprise Data: Enables "real-time KPIs" for performance management
    - AI Agile Team: Provides summary data for "predictive models"

    This endpoint provides the aggregated statistics needed for
    dashboard displays and analytics, supporting the BEP MES
    requirement for "interactive dashboards."
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        parameters=[
            OpenApiParameter('hours', int, description='Number of hours to include (default 24)'),
        ],
        responses={200: MachineTelemetrySummarySerializer(many=True)}
    )
    def get(self, request, pk):
        """Get telemetry summary statistics for a machine.

        Returns aggregated statistics (min, max, avg, count) for each
        telemetry data type, supporting dashboard displays and analytics.

        Query Parameters:
        - hours: Number of hours to include in summary (default 24)
        """
        machine = get_machine(pk)
        machine_config = machine.machine_config

        # Get time range
        hours = int(request.query_params.get('hours', 24))
        start_time = timezone.now() - timezone.timedelta(hours=hours)

        # Get summary for each data type
        summaries = []

        for data_type, data_type_display in TelemetryDataType.choices:
            queryset = MachineTelemetryData.objects.filter(
                machine=machine_config,
                data_type=data_type,
                timestamp__gte=start_time
            )

            if not queryset.exists():
                continue

            # Aggregate statistics
            stats = queryset.aggregate(
                count=Count('id'),
                min_value=Min('value'),
                max_value=Max('value'),
                avg_value=Avg('value'),
            )

            # Get latest value
            latest = queryset.order_by('-timestamp').first()

            # Count active alerts
            active_alerts = MachineAlert.objects.filter(
                machine=machine_config,
                status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED],
                telemetry_data__data_type=data_type
            ).count()

            summaries.append({
                'machine_id': machine_config.pk,
                'machine_name': machine_config.name,
                'data_type': data_type,
                'data_type_display': data_type_display,
                'count': stats['count'],
                'min_value': stats['min_value'],
                'max_value': stats['max_value'],
                'avg_value': stats['avg_value'],
                'latest_value': latest.value if latest else None,
                'latest_timestamp': latest.timestamp if latest else None,
                'unit': latest.unit if latest else '',
                'active_alerts': active_alerts,
            })

        serializer = MachineTelemetrySummarySerializer(summaries, many=True)
        return Response(serializer.data)


class MachineAlertList(APIView):
    """API endpoint for machine alerts.

    GET: Retrieve alerts for a specific machine

    BEP MES Contract Alignment:
    - Manufacturing Team: Enables "proactive action" through alert visibility
    - Quality Management: Supports "ISO 9001 compliance" through audit trail
    - Data Analytics: Enables "forecast equipment failures"

    Query Parameters:
    - status: Filter by alert status (ACTIVE, ACK, RESOLVED, SUPP)
    - severity: Filter by severity (CRIT, HIGH, MED, LOW, INFO)
    - alert_type: Filter by alert type (THRESH, ANOM, MAINT, QUAL, COMM, CUST)
    - limit: Maximum number of records to return (default 100, max 1000)
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        parameters=[
            OpenApiParameter('status', str, description='Filter by alert status'),
            OpenApiParameter('severity', str, description='Filter by severity'),
            OpenApiParameter('alert_type', str, description='Filter by alert type'),
            OpenApiParameter('limit', int, description='Maximum records to return'),
        ],
        responses={200: MachineAlertSerializer(many=True)}
    )
    def get(self, request, pk):
        """Retrieve alerts for a machine."""
        get_machine(pk)  # Validate machine exists

        queryset = MachineAlert.objects.filter(machine__pk=pk)

        # Apply filters
        alert_status = request.query_params.get('status')
        if alert_status:
            queryset = queryset.filter(status=alert_status)

        severity = request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)

        alert_type = request.query_params.get('alert_type')
        if alert_type:
            queryset = queryset.filter(alert_type=alert_type)

        # Apply limit
        limit = min(int(request.query_params.get('limit', 100)), 1000)
        queryset = queryset[:limit]

        serializer = MachineAlertSerializer(queryset, many=True)
        return Response(serializer.data)


class MachineAlertDetail(APIView):
    """API endpoint for a specific machine alert.

    GET: Retrieve alert details
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(responses={200: MachineAlertSerializer})
    def get(self, request, pk, alert_pk):
        """Retrieve alert details."""
        try:
            alert = MachineAlert.objects.get(pk=alert_pk, machine__pk=pk)
        except MachineAlert.DoesNotExist:
            raise NotFound(detail=f"Alert '{alert_pk}' not found for machine '{pk}'")

        serializer = MachineAlertSerializer(alert)
        return Response(serializer.data)


class MachineAlertAcknowledge(APIView):
    """API endpoint to acknowledge a machine alert.

    POST: Acknowledge an alert

    BEP MES Contract Alignment:
    - Manufacturing Team: Enables "proactive action" workflow
    - Quality Management: Provides audit trail for "ISO 9001 compliance"
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        request=MachineAlertAcknowledgeSerializer,
        responses={200: MachineAlertSerializer}
    )
    def post(self, request, pk, alert_pk):
        """Acknowledge an alert."""
        try:
            alert = MachineAlert.objects.get(pk=alert_pk, machine__pk=pk)
        except MachineAlert.DoesNotExist:
            raise NotFound(detail=f"Alert '{alert_pk}' not found for machine '{pk}'")

        if alert.status != AlertStatus.ACTIVE:
            raise ValidationError(detail="Only active alerts can be acknowledged")

        serializer = MachineAlertAcknowledgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data.get('acknowledged_by', str(request.user))
        alert.acknowledge(user)

        response_serializer = MachineAlertSerializer(alert)
        return Response(response_serializer.data)


class MachineAlertResolve(APIView):
    """API endpoint to resolve a machine alert.

    POST: Resolve an alert with documentation

    BEP MES Contract Alignment:
    - Manufacturing Team: Completes "proactive action" workflow
    - Quality Management: Documents resolution for "ISO 9001 compliance"
    - AI Agile Team: Provides data for "continuous improvement"
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        request=MachineAlertResolveSerializer,
        responses={200: MachineAlertSerializer}
    )
    def post(self, request, pk, alert_pk):
        """Resolve an alert with documentation."""
        try:
            alert = MachineAlert.objects.get(pk=alert_pk, machine__pk=pk)
        except MachineAlert.DoesNotExist:
            raise NotFound(detail=f"Alert '{alert_pk}' not found for machine '{pk}'")

        if alert.status == AlertStatus.RESOLVED:
            raise ValidationError(detail="Alert is already resolved")

        serializer = MachineAlertResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data.get('resolved_by', str(request.user))
        notes = serializer.validated_data['resolution_notes']
        alert.resolve(user, notes)

        response_serializer = MachineAlertSerializer(alert)
        return Response(response_serializer.data)


class MachineTelemetryThresholdList(ListCreateAPI):
    """API endpoint for machine telemetry thresholds.

    GET: List thresholds for a machine
    POST: Create a new threshold

    BEP MES Contract Alignment:
    - Enterprise Data: Enables "data validation rules"
    - Quality Management: Supports "ISO 9001 control limits"
    - AI Agile Team: Provides baseline for "anomaly detection"
    """

    serializer_class = MachineTelemetryThresholdSerializer

    def get_queryset(self):
        """Filter thresholds by machine."""
        pk = self.kwargs.get('pk')
        return MachineTelemetryThreshold.objects.filter(machine__pk=pk)

    def perform_create(self, serializer):
        """Set machine from URL parameter."""
        pk = self.kwargs.get('pk')
        try:
            machine_config = MachineConfig.objects.get(pk=pk)
        except MachineConfig.DoesNotExist:
            raise NotFound(detail=f"Machine '{pk}' not found")

        serializer.save(machine=machine_config)


class MachineTelemetryThresholdDetail(RetrieveUpdateDestroyAPI):
    """API endpoint for a specific telemetry threshold.

    GET: Retrieve threshold details
    PUT/PATCH: Update threshold
    DELETE: Delete threshold
    """

    serializer_class = MachineTelemetryThresholdSerializer

    def get_queryset(self):
        """Filter thresholds by machine."""
        pk = self.kwargs.get('pk')
        return MachineTelemetryThreshold.objects.filter(machine__pk=pk)

    def get_object(self):
        """Get threshold by pk."""
        threshold_pk = self.kwargs.get('threshold_pk')
        try:
            return self.get_queryset().get(pk=threshold_pk)
        except MachineTelemetryThreshold.DoesNotExist:
            raise NotFound(detail=f"Threshold '{threshold_pk}' not found")


class MachineStatusView(APIView):
    """API endpoint for comprehensive machine status.

    GET: Retrieve complete machine status including telemetry and alerts

    BEP MES Contract Alignment:
    - Manufacturing Team: Provides "real-time equipment status tracking"
    - Data Analytics: Enables "interactive dashboards"
    - AI Agile Team: Supports "predictive maintenance" models

    This endpoint provides a complete status overview for a machine,
    supporting the BEP MES requirement for "proactive action" through
    comprehensive health monitoring.
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(responses={200: MachineStatusSerializer})
    def get(self, request, pk):
        """Get comprehensive machine status."""
        machine = get_machine(pk)
        machine_config = machine.machine_config

        # Get alert counts
        active_alerts = MachineAlert.objects.filter(
            machine=machine_config,
            status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]
        )

        critical_alerts = active_alerts.filter(severity=AlertSeverity.CRITICAL).count()
        high_alerts = active_alerts.filter(severity=AlertSeverity.HIGH).count()

        # Get last telemetry timestamp
        last_telemetry = MachineTelemetryData.objects.filter(
            machine=machine_config
        ).order_by('-timestamp').first()

        # Get telemetry summary (last 24 hours)
        hours = 24
        start_time = timezone.now() - timezone.timedelta(hours=hours)

        summaries = []
        for data_type, data_type_display in TelemetryDataType.choices:
            queryset = MachineTelemetryData.objects.filter(
                machine=machine_config,
                data_type=data_type,
                timestamp__gte=start_time
            )

            if not queryset.exists():
                continue

            stats = queryset.aggregate(
                count=Count('id'),
                min_value=Min('value'),
                max_value=Max('value'),
                avg_value=Avg('value'),
            )

            latest = queryset.order_by('-timestamp').first()

            type_alerts = MachineAlert.objects.filter(
                machine=machine_config,
                status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED],
                telemetry_data__data_type=data_type
            ).count()

            summaries.append({
                'machine_id': machine_config.pk,
                'machine_name': machine_config.name,
                'data_type': data_type,
                'data_type_display': data_type_display,
                'count': stats['count'],
                'min_value': stats['min_value'],
                'max_value': stats['max_value'],
                'avg_value': stats['avg_value'],
                'latest_value': latest.value if latest else None,
                'latest_timestamp': latest.timestamp if latest else None,
                'unit': latest.unit if latest else '',
                'active_alerts': type_alerts,
            })

        status_data = {
            'machine_id': machine_config.pk,
            'machine_name': machine_config.name,
            'is_active': machine_config.active,
            'is_healthy': critical_alerts == 0 and high_alerts == 0,
            'last_telemetry_at': last_telemetry.timestamp if last_telemetry else None,
            'active_alerts_count': active_alerts.count(),
            'critical_alerts_count': critical_alerts,
            'telemetry_summary': summaries,
        }

        serializer = MachineStatusSerializer(status_data)
        return Response(serializer.data)


# URL patterns for telemetry API
machine_telemetry_api_urls = [
    # Telemetry data endpoints
    path(
        'telemetry/',
        include([
            path('bulk/', MachineTelemetryBulkCreate.as_view(), name='api-machine-telemetry-bulk'),
            path('summary/', MachineTelemetrySummary.as_view(), name='api-machine-telemetry-summary'),
            path('', MachineTelemetryList.as_view(), name='api-machine-telemetry-list'),
        ]),
    ),
    # Alert endpoints
    path(
        'alerts/',
        include([
            path(
                '<uuid:alert_pk>/',
                include([
                    path('acknowledge/', MachineAlertAcknowledge.as_view(), name='api-machine-alert-acknowledge'),
                    path('resolve/', MachineAlertResolve.as_view(), name='api-machine-alert-resolve'),
                    path('', MachineAlertDetail.as_view(), name='api-machine-alert-detail'),
                ]),
            ),
            path('', MachineAlertList.as_view(), name='api-machine-alert-list'),
        ]),
    ),
    # Threshold endpoints
    path(
        'thresholds/',
        include([
            path('<uuid:threshold_pk>/', MachineTelemetryThresholdDetail.as_view(), name='api-machine-threshold-detail'),
            path('', MachineTelemetryThresholdList.as_view(), name='api-machine-threshold-list'),
        ]),
    ),
    # Status endpoint
    path('status/', MachineStatusView.as_view(), name='api-machine-status'),
]
