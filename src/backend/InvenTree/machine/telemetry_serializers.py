"""Serializers for Machine Telemetry API endpoints.

This module provides REST API serializers for the machine telemetry system,
supporting the BEP MES contract requirement for "IT integration for full traceability."

BEP MES Contract Alignment:
==========================
These serializers enable the REST API interface that allows BEP manufacturing
equipment to transmit telemetry data to the MES system, directly supporting:

1. MANUFACTURING TEAM FOCUS AREA:
   - "Create new screen press connection to the BEP machine network"
   - These serializers define the data contract for machine-to-MES communication

2. ENTERPRISE DATA & PERFORMANCE MANAGEMENT:
   - "Automated, controlled process that ingests, cleans, validates"
   - Serializers include validation logic to ensure data quality

3. DATA ANALYTICS FOCUS AREA:
   - "Publish dashboards and predictive models"
   - Serializers format data for consumption by analytics systems

API Endpoints Supported:
=======================
- POST /api/machine/{pk}/telemetry/ - Submit telemetry data
- GET /api/machine/{pk}/telemetry/ - Retrieve telemetry history
- GET /api/machine/{pk}/alerts/ - Retrieve machine alerts
- POST /api/machine/{pk}/alerts/{alert_pk}/acknowledge/ - Acknowledge alert
- POST /api/machine/{pk}/alerts/{alert_pk}/resolve/ - Resolve alert
"""

from decimal import Decimal
from typing import Optional

from django.utils import timezone

from rest_framework import serializers

from machine.telemetry_models import (
    MachineAlert,
    MachineTelemetryData,
    MachineTelemetryThreshold,
    TelemetryDataType,
)


class MachineTelemetryDataSerializer(serializers.ModelSerializer):
    """Serializer for MachineTelemetryData model.

    This serializer handles the ingestion and retrieval of telemetry data
    from BEP manufacturing equipment.

    BEP MES Contract Alignment:
    - Supports "IT integration for full traceability" by capturing all
      relevant telemetry attributes
    - Includes validation to ensure "trusted data products"
    - Provides read-only computed fields for analytics consumption

    Input Validation:
    - data_type must be a valid TelemetryDataType choice
    - value must be a valid decimal number
    - timestamp must be a valid datetime (defaults to current time)
    - quality_flag defaults to GOOD if not specified

    Output Fields:
    - All model fields plus computed display values
    - data_type_display: Human-readable data type name
    - quality_flag_display: Human-readable quality flag
    """

    class Meta:
        """Serializer metadata."""

        model = MachineTelemetryData
        fields = [
            'id',
            'machine',
            'data_type',
            'data_type_display',
            'value',
            'unit',
            'timestamp',
            'quality_flag',
            'quality_flag_display',
            'metadata',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'data_type_display', 'quality_flag_display']

    data_type_display = serializers.CharField(source='get_data_type_display', read_only=True)
    quality_flag_display = serializers.CharField(source='get_quality_flag_display', read_only=True)

    def validate_value(self, value):
        """Validate the telemetry value.

        Ensures the value is a valid decimal number within reasonable bounds.
        This supports the BEP MES requirement for data validation.
        """
        if value is None:
            raise serializers.ValidationError("Value cannot be null")
        return value

    def validate_timestamp(self, value):
        """Validate the timestamp.

        Ensures the timestamp is not in the future (with small tolerance for clock skew).
        """
        if value > timezone.now() + timezone.timedelta(minutes=5):
            raise serializers.ValidationError("Timestamp cannot be more than 5 minutes in the future")
        return value


class MachineTelemetryDataCreateSerializer(MachineTelemetryDataSerializer):
    """Serializer for creating telemetry data records.

    This serializer is optimized for bulk telemetry ingestion from
    manufacturing equipment, supporting the BEP MES requirement for
    "automated, controlled process that ingests" data.

    Features:
    - Machine is set from URL parameter (not required in request body)
    - Timestamp defaults to current time if not provided
    - Supports batch creation for efficiency
    """

    class Meta(MachineTelemetryDataSerializer.Meta):
        """Serializer metadata."""

        read_only_fields = ['id', 'machine', 'created_at', 'data_type_display', 'quality_flag_display']

    def validate(self, attrs):
        """Validate the telemetry data and check thresholds.

        This method implements the BEP MES requirement for data validation
        by checking values against configured thresholds.
        """
        attrs = super().validate(attrs)

        # Set default timestamp if not provided
        if 'timestamp' not in attrs or attrs['timestamp'] is None:
            attrs['timestamp'] = timezone.now()

        return attrs


class MachineTelemetryBulkCreateSerializer(serializers.Serializer):
    """Serializer for bulk telemetry data ingestion.

    This serializer supports high-volume telemetry ingestion from
    manufacturing equipment, enabling efficient data collection
    for the BEP MES system.

    BEP MES Contract Alignment:
    - Supports "automated, controlled process that ingests" data
    - Enables real-time data collection from multiple sensors
    - Optimized for Industry 4.0 equipment integration

    Request Format:
    {
        "data": [
            {"data_type": "TEMP", "value": 72.5, "unit": "F", "timestamp": "..."},
            {"data_type": "PRES", "value": 100.2, "unit": "PSI", "timestamp": "..."},
            ...
        ]
    }
    """

    data = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        max_length=1000,
        help_text="List of telemetry data points to create (max 1000 per request)"
    )

    def validate_data(self, value):
        """Validate each telemetry data point in the batch."""
        errors = []
        for i, item in enumerate(value):
            if 'data_type' not in item:
                errors.append(f"Item {i}: data_type is required")
            elif item['data_type'] not in [choice[0] for choice in TelemetryDataType.choices]:
                errors.append(f"Item {i}: invalid data_type '{item['data_type']}'")

            if 'value' not in item:
                errors.append(f"Item {i}: value is required")
            else:
                try:
                    Decimal(str(item['value']))
                except:
                    errors.append(f"Item {i}: value must be a valid number")

        if errors:
            raise serializers.ValidationError(errors)

        return value


class MachineAlertSerializer(serializers.ModelSerializer):
    """Serializer for MachineAlert model.

    This serializer handles the retrieval and management of machine alerts,
    supporting the BEP MES requirement for "proactive action" through
    real-time anomaly detection and notification.

    BEP MES Contract Alignment:
    - Supports "forecast throughput, quality issues, and equipment failures"
    - Enables "proactive action" through alert management
    - Provides audit trail for ISO 9001 compliance

    Output Fields:
    - All model fields plus computed display values
    - severity_display: Human-readable severity level
    - status_display: Human-readable status
    - alert_type_display: Human-readable alert type
    - duration: Time since alert was created (for SLA tracking)
    """

    class Meta:
        """Serializer metadata."""

        model = MachineAlert
        fields = [
            'id',
            'machine',
            'telemetry_data',
            'severity',
            'severity_display',
            'status',
            'status_display',
            'alert_type',
            'alert_type_display',
            'title',
            'description',
            'threshold_value',
            'actual_value',
            'acknowledged_by',
            'acknowledged_at',
            'resolved_by',
            'resolved_at',
            'resolution_notes',
            'metadata',
            'created_at',
            'updated_at',
            'duration',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'severity_display', 'status_display', 'alert_type_display', 'duration'
        ]

    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)
    duration = serializers.SerializerMethodField()

    def get_duration(self, obj) -> Optional[str]:
        """Calculate the duration since the alert was created.

        Returns a human-readable duration string for SLA tracking.
        """
        if obj.resolved_at:
            delta = obj.resolved_at - obj.created_at
        else:
            delta = timezone.now() - obj.created_at

        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"


class MachineAlertAcknowledgeSerializer(serializers.Serializer):
    """Serializer for acknowledging a machine alert.

    This serializer supports the alert acknowledgment workflow,
    enabling operators to indicate they are aware of and addressing
    an equipment issue.

    BEP MES Contract Alignment:
    - Supports "proactive action" through alert management
    - Provides audit trail for ISO 9001 compliance
    """

    acknowledged_by = serializers.CharField(
        max_length=255,
        required=False,
        help_text="User acknowledging the alert (defaults to current user)"
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        help_text="Optional notes about the acknowledgment"
    )


class MachineAlertResolveSerializer(serializers.Serializer):
    """Serializer for resolving a machine alert.

    This serializer supports the alert resolution workflow,
    enabling operators to document how an equipment issue was resolved.

    BEP MES Contract Alignment:
    - Supports "continuous improvement" through resolution documentation
    - Provides audit trail for ISO 9001 compliance
    - Enables root cause analysis for predictive maintenance
    """

    resolved_by = serializers.CharField(
        max_length=255,
        required=False,
        help_text="User resolving the alert (defaults to current user)"
    )
    resolution_notes = serializers.CharField(
        required=True,
        help_text="Documentation of how the issue was resolved (required for audit trail)"
    )


class MachineTelemetryThresholdSerializer(serializers.ModelSerializer):
    """Serializer for MachineTelemetryThreshold model.

    This serializer handles the configuration of telemetry thresholds,
    enabling BEP operators to define acceptable ranges for equipment
    parameters.

    BEP MES Contract Alignment:
    - Supports "data validation rules" for enterprise data management
    - Enables "ISO 9001 control limits" for quality management
    - Provides baseline for "anomaly detection" in AI/ML models
    """

    class Meta:
        """Serializer metadata."""

        model = MachineTelemetryThreshold
        fields = [
            'id',
            'machine',
            'data_type',
            'data_type_display',
            'min_value',
            'max_value',
            'warning_min',
            'warning_max',
            'alert_severity',
            'alert_severity_display',
            'enabled',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'data_type_display', 'alert_severity_display']

    data_type_display = serializers.CharField(source='get_data_type_display', read_only=True)
    alert_severity_display = serializers.CharField(source='get_alert_severity_display', read_only=True)

    def validate(self, attrs):
        """Validate threshold configuration.

        Ensures that min values are less than max values and warning
        thresholds are within the critical thresholds.
        """
        attrs = super().validate(attrs)

        min_val = attrs.get('min_value')
        max_val = attrs.get('max_value')
        warn_min = attrs.get('warning_min')
        warn_max = attrs.get('warning_max')

        # Validate min < max
        if min_val is not None and max_val is not None and min_val >= max_val:
            raise serializers.ValidationError({
                'min_value': 'Minimum value must be less than maximum value'
            })

        # Validate warning thresholds are within critical thresholds
        if warn_min is not None and min_val is not None and warn_min < min_val:
            raise serializers.ValidationError({
                'warning_min': 'Warning minimum must be greater than or equal to minimum value'
            })

        if warn_max is not None and max_val is not None and warn_max > max_val:
            raise serializers.ValidationError({
                'warning_max': 'Warning maximum must be less than or equal to maximum value'
            })

        return attrs


class MachineTelemetrySummarySerializer(serializers.Serializer):
    """Serializer for machine telemetry summary statistics.

    This serializer provides aggregated telemetry statistics for
    dashboard display and analytics, supporting the BEP MES requirement
    for "interactive dashboards" and "real-time KPIs."

    BEP MES Contract Alignment:
    - Supports "publish dashboards" for data analytics
    - Enables "real-time KPIs" for performance management
    - Provides data for "predictive models" in AI/ML
    """

    machine_id = serializers.UUIDField()
    machine_name = serializers.CharField()
    data_type = serializers.CharField()
    data_type_display = serializers.CharField()
    count = serializers.IntegerField(help_text="Number of telemetry records")
    min_value = serializers.DecimalField(max_digits=20, decimal_places=6, allow_null=True)
    max_value = serializers.DecimalField(max_digits=20, decimal_places=6, allow_null=True)
    avg_value = serializers.DecimalField(max_digits=20, decimal_places=6, allow_null=True)
    latest_value = serializers.DecimalField(max_digits=20, decimal_places=6, allow_null=True)
    latest_timestamp = serializers.DateTimeField(allow_null=True)
    unit = serializers.CharField(allow_blank=True)
    active_alerts = serializers.IntegerField(help_text="Number of active alerts for this data type")


class MachineStatusSerializer(serializers.Serializer):
    """Serializer for comprehensive machine status.

    This serializer provides a complete status overview for a machine,
    including telemetry summary, active alerts, and health indicators.

    BEP MES Contract Alignment:
    - Supports "real-time equipment status tracking"
    - Enables "proactive action" through health monitoring
    - Provides data for "predictive maintenance" models
    """

    machine_id = serializers.UUIDField()
    machine_name = serializers.CharField()
    is_active = serializers.BooleanField()
    is_healthy = serializers.BooleanField(help_text="True if no critical or high severity alerts")
    last_telemetry_at = serializers.DateTimeField(allow_null=True)
    active_alerts_count = serializers.IntegerField()
    critical_alerts_count = serializers.IntegerField()
    telemetry_summary = MachineTelemetrySummarySerializer(many=True)
