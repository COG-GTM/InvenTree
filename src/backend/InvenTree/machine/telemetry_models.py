"""Machine Telemetry Models for Industry 4.0 Integration.

This module implements machine telemetry data collection and monitoring capabilities
to support the Bureau of Engraving and Printing (BEP) Manufacturing Execution System (MES)
modernization initiative.

BEP MES Contract Alignment:
==========================
This implementation directly addresses the following BEP MES contract requirements:

1. MANUFACTURING TEAM FOCUS AREA:
   - Goal: "Integrate Industry 4.0 technologies - smart automation and advanced analytics"
   - Key Outcome: "Create new screen press connection to the BEP machine network and
     provide any IT support and workstation in the deployment"
   - This module provides the data model foundation for connecting manufacturing equipment
     to the BEP IT infrastructure, enabling full traceability of production operations.

2. ENTERPRISE DATA & PERFORMANCE MANAGEMENT:
   - Goal: "Enable data-driven decisions"
   - Key Outcome: "Build and operate an automated, controlled process that ingests, cleans,
     validates, and publishes trusted data products"
   - The MachineTelemetryData model captures validated, timestamped telemetry data that
     feeds into BEP's enterprise data lake for analytics and decision-making.

3. DATA ANALYTICS FOCUS AREA:
   - Goal: "Deliver advanced insights"
   - Key Outcome: "Publish dashboards and predictive models to forecast throughput,
     quality issues, and equipment failures for proactive action"
   - The MachineAlert model enables real-time anomaly detection and alerting,
     supporting predictive maintenance and quality control initiatives.

4. AI AGILE TEAM FOCUS AREA:
   - Goal: "Drive innovation with AI"
   - Key Outcome: "An AI model analyzed past runs and suggested small changes to
     the machine temperature settings"
   - The telemetry data collected by this module provides the training data foundation
     for AI/ML models that optimize production parameters.

Technical Implementation:
========================
- MachineTelemetryData: Stores time-series telemetry data from manufacturing equipment
- MachineAlert: Tracks equipment anomalies and alerts for proactive maintenance
- TelemetryDataType: Enumeration of supported telemetry data types (temperature, pressure, etc.)
- AlertSeverity: Enumeration of alert severity levels for prioritization

Compliance Notes:
================
- All data models include audit fields (created_at, updated_at) for traceability
- Data validation ensures integrity of telemetry readings
- Foreign key relationships maintain referential integrity with MachineConfig
"""

import uuid
from decimal import Decimal
from typing import Optional

from django.db import models
from django.utils.translation import gettext_lazy as _

from machine.models import MachineConfig


class TelemetryDataType(models.TextChoices):
    """Enumeration of telemetry data types supported by BEP manufacturing equipment.

    These data types align with Industry 4.0 standards and support the BEP MES
    requirement for "smart automation and advanced analytics" by capturing
    comprehensive machine operational parameters.

    BEP-Specific Applications:
    - TEMPERATURE: Monitor press heating elements, ink drying systems
    - PRESSURE: Track hydraulic systems, pneumatic controls
    - SPEED: Measure press speed, conveyor rates
    - VIBRATION: Detect bearing wear, alignment issues
    - POWER: Monitor energy consumption for efficiency optimization
    - HUMIDITY: Critical for paper handling and ink adhesion
    - COUNT: Track sheet counts, cycle counts for production metrics
    - QUALITY_SCORE: Automated quality inspection results
    - CUSTOM: Extensible for BEP-specific measurements
    """

    TEMPERATURE = 'TEMP', _('Temperature')
    PRESSURE = 'PRES', _('Pressure')
    SPEED = 'SPEED', _('Speed/RPM')
    VIBRATION = 'VIB', _('Vibration')
    POWER = 'PWR', _('Power Consumption')
    HUMIDITY = 'HUM', _('Humidity')
    COUNT = 'CNT', _('Count/Cycles')
    QUALITY_SCORE = 'QUAL', _('Quality Score')
    CUSTOM = 'CUST', _('Custom Measurement')


class AlertSeverity(models.TextChoices):
    """Alert severity levels for machine anomaly classification.

    Severity levels support the BEP MES requirement for "proactive action"
    by enabling prioritized response to equipment issues.

    Operational Guidelines:
    - CRITICAL: Immediate production stop required, safety risk
    - HIGH: Production impact imminent, urgent maintenance needed
    - MEDIUM: Degraded performance, schedule maintenance
    - LOW: Minor deviation, monitor and log
    - INFO: Informational alert, no action required
    """

    CRITICAL = 'CRIT', _('Critical - Immediate Action Required')
    HIGH = 'HIGH', _('High - Urgent Attention Needed')
    MEDIUM = 'MED', _('Medium - Schedule Maintenance')
    LOW = 'LOW', _('Low - Monitor')
    INFO = 'INFO', _('Informational')


class AlertStatus(models.TextChoices):
    """Alert lifecycle status for tracking resolution workflow.

    Supports the BEP MES requirement for "continuous improvement" by
    enabling tracking of alert resolution and root cause analysis.
    """

    ACTIVE = 'ACTIVE', _('Active - Requires Attention')
    ACKNOWLEDGED = 'ACK', _('Acknowledged - Being Addressed')
    RESOLVED = 'RESOLVED', _('Resolved - Issue Fixed')
    SUPPRESSED = 'SUPP', _('Suppressed - Intentionally Ignored')


class MachineTelemetryData(models.Model):
    """Time-series telemetry data from BEP manufacturing equipment.

    This model captures real-time operational data from manufacturing equipment,
    supporting the BEP MES contract requirement for "full traceability" and
    "data-driven decisions."

    BEP MES Contract Alignment:
    - Manufacturing Team: Provides IT integration for equipment traceability
    - Enterprise Data: Feeds validated data into the enterprise data lake
    - Data Analytics: Enables predictive analytics and dashboards
    - AI Agile Team: Provides training data for production optimization models

    Data Flow:
    1. Equipment sends telemetry via REST API
    2. Data is validated against defined thresholds
    3. Anomalies trigger alerts via MachineAlert model
    4. Data is stored for historical analysis and AI/ML training

    Attributes:
        id: Unique identifier (UUID for distributed systems compatibility)
        machine: Foreign key to MachineConfig (the source equipment)
        data_type: Type of telemetry measurement (temperature, pressure, etc.)
        value: Numeric measurement value
        unit: Unit of measurement (e.g., "C", "PSI", "RPM")
        timestamp: When the measurement was taken (equipment time)
        quality_flag: Data quality indicator (GOOD, UNCERTAIN, BAD)
        metadata: JSON field for additional context (batch ID, operator, etc.)
        created_at: Server timestamp when record was created
    """

    class Meta:
        """Model metadata."""

        verbose_name = _('Machine Telemetry Data')
        verbose_name_plural = _('Machine Telemetry Data')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['machine', 'timestamp']),
            models.Index(fields=['machine', 'data_type', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]

    class QualityFlag(models.TextChoices):
        """Data quality indicators per OPC UA standard.

        Aligns with Industry 4.0 data quality standards for reliable analytics.
        """

        GOOD = 'GOOD', _('Good - Reliable Data')
        UNCERTAIN = 'UNC', _('Uncertain - Use with Caution')
        BAD = 'BAD', _('Bad - Do Not Use')

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Unique identifier for this telemetry record')
    )

    machine = models.ForeignKey(
        MachineConfig,
        on_delete=models.CASCADE,
        related_name='telemetry_data',
        verbose_name=_('Machine'),
        help_text=_('The machine that generated this telemetry data')
    )

    data_type = models.CharField(
        max_length=10,
        choices=TelemetryDataType.choices,
        verbose_name=_('Data Type'),
        help_text=_('Type of telemetry measurement')
    )

    value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        verbose_name=_('Value'),
        help_text=_('Numeric measurement value')
    )

    unit = models.CharField(
        max_length=20,
        verbose_name=_('Unit'),
        help_text=_('Unit of measurement (e.g., C, PSI, RPM)'),
        blank=True,
        default=''
    )

    timestamp = models.DateTimeField(
        verbose_name=_('Timestamp'),
        help_text=_('When the measurement was taken (equipment time)'),
        db_index=True
    )

    quality_flag = models.CharField(
        max_length=10,
        choices=QualityFlag.choices,
        default=QualityFlag.GOOD,
        verbose_name=_('Quality Flag'),
        help_text=_('Data quality indicator')
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Metadata'),
        help_text=_('Additional context (batch ID, operator, production run, etc.)')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At'),
        help_text=_('Server timestamp when record was created')
    )

    def __str__(self) -> str:
        """String representation of telemetry data."""
        return f'{self.machine.name} - {self.get_data_type_display()}: {self.value} {self.unit} @ {self.timestamp}'

    def is_within_threshold(self, min_value: Optional[Decimal] = None, max_value: Optional[Decimal] = None) -> bool:
        """Check if the telemetry value is within acceptable thresholds.

        Used for anomaly detection and alert generation.

        Args:
            min_value: Minimum acceptable value (optional)
            max_value: Maximum acceptable value (optional)

        Returns:
            True if value is within thresholds, False otherwise
        """
        if min_value is not None and self.value < min_value:
            return False
        if max_value is not None and self.value > max_value:
            return False
        return True


class MachineAlert(models.Model):
    """Equipment anomaly alerts for proactive maintenance and quality control.

    This model supports the BEP MES contract requirement for "proactive action"
    by enabling real-time detection and notification of equipment issues.

    BEP MES Contract Alignment:
    - Manufacturing Team: Enables proactive maintenance to minimize downtime
    - Quality Management: Alerts on quality deviations for ISO 9001 compliance
    - Data Analytics: Provides data for predictive maintenance models
    - AI Agile Team: Supports AI-driven anomaly detection

    Alert Workflow:
    1. Telemetry data triggers threshold violation
    2. Alert is created with appropriate severity
    3. Notification sent to responsible personnel
    4. Alert is acknowledged and investigated
    5. Resolution is documented for continuous improvement

    Attributes:
        id: Unique identifier (UUID)
        machine: Foreign key to MachineConfig
        telemetry_data: Optional link to triggering telemetry record
        severity: Alert severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO)
        status: Alert lifecycle status (ACTIVE, ACKNOWLEDGED, RESOLVED, SUPPRESSED)
        alert_type: Category of alert (THRESHOLD, ANOMALY, MAINTENANCE, QUALITY)
        title: Brief description of the alert
        description: Detailed description and context
        threshold_value: The threshold that was violated (if applicable)
        actual_value: The actual value that triggered the alert
        acknowledged_by: User who acknowledged the alert
        acknowledged_at: Timestamp of acknowledgment
        resolved_by: User who resolved the alert
        resolved_at: Timestamp of resolution
        resolution_notes: Documentation of how the issue was resolved
        created_at: When the alert was created
        updated_at: Last update timestamp
    """

    class Meta:
        """Model metadata."""

        verbose_name = _('Machine Alert')
        verbose_name_plural = _('Machine Alerts')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['machine', 'status']),
            models.Index(fields=['severity', 'status']),
            models.Index(fields=['created_at']),
        ]

    class AlertType(models.TextChoices):
        """Categories of machine alerts.

        Supports classification for routing and reporting.
        """

        THRESHOLD = 'THRESH', _('Threshold Violation')
        ANOMALY = 'ANOM', _('Anomaly Detected')
        MAINTENANCE = 'MAINT', _('Maintenance Required')
        QUALITY = 'QUAL', _('Quality Issue')
        COMMUNICATION = 'COMM', _('Communication Failure')
        CUSTOM = 'CUST', _('Custom Alert')

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Unique identifier for this alert')
    )

    machine = models.ForeignKey(
        MachineConfig,
        on_delete=models.CASCADE,
        related_name='alerts',
        verbose_name=_('Machine'),
        help_text=_('The machine that generated this alert')
    )

    telemetry_data = models.ForeignKey(
        MachineTelemetryData,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name=_('Telemetry Data'),
        help_text=_('The telemetry record that triggered this alert (if applicable)')
    )

    severity = models.CharField(
        max_length=10,
        choices=AlertSeverity.choices,
        default=AlertSeverity.MEDIUM,
        verbose_name=_('Severity'),
        help_text=_('Alert severity level for prioritization')
    )

    status = models.CharField(
        max_length=10,
        choices=AlertStatus.choices,
        default=AlertStatus.ACTIVE,
        verbose_name=_('Status'),
        help_text=_('Current status in the alert lifecycle')
    )

    alert_type = models.CharField(
        max_length=10,
        choices=AlertType.choices,
        default=AlertType.THRESHOLD,
        verbose_name=_('Alert Type'),
        help_text=_('Category of alert for routing and reporting')
    )

    title = models.CharField(
        max_length=255,
        verbose_name=_('Title'),
        help_text=_('Brief description of the alert')
    )

    description = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Description'),
        help_text=_('Detailed description and context')
    )

    threshold_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_('Threshold Value'),
        help_text=_('The threshold that was violated (if applicable)')
    )

    actual_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_('Actual Value'),
        help_text=_('The actual value that triggered the alert')
    )

    acknowledged_by = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name=_('Acknowledged By'),
        help_text=_('User who acknowledged the alert')
    )

    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Acknowledged At'),
        help_text=_('Timestamp of acknowledgment')
    )

    resolved_by = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name=_('Resolved By'),
        help_text=_('User who resolved the alert')
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Resolved At'),
        help_text=_('Timestamp of resolution')
    )

    resolution_notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Resolution Notes'),
        help_text=_('Documentation of how the issue was resolved (for continuous improvement)')
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Metadata'),
        help_text=_('Additional context and data')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At'),
        help_text=_('When the alert was created')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At'),
        help_text=_('Last update timestamp')
    )

    def __str__(self) -> str:
        """String representation of alert."""
        return f'[{self.get_severity_display()}] {self.machine.name}: {self.title}'

    def acknowledge(self, user: str) -> None:
        """Mark the alert as acknowledged.

        Args:
            user: Username or identifier of the acknowledging user
        """
        from django.utils import timezone
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        self.save(update_fields=['status', 'acknowledged_by', 'acknowledged_at', 'updated_at'])

    def resolve(self, user: str, notes: str = '') -> None:
        """Mark the alert as resolved.

        Args:
            user: Username or identifier of the resolving user
            notes: Resolution notes for documentation
        """
        from django.utils import timezone
        self.status = AlertStatus.RESOLVED
        self.resolved_by = user
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.save(update_fields=['status', 'resolved_by', 'resolved_at', 'resolution_notes', 'updated_at'])


class MachineTelemetryThreshold(models.Model):
    """Configurable thresholds for telemetry data validation and alerting.

    This model enables BEP operators to define acceptable ranges for each
    telemetry data type, supporting the contract requirement for "automated,
    controlled process that ingests, cleans, validates" data.

    BEP MES Contract Alignment:
    - Enterprise Data: Enables data validation rules
    - Quality Management: Supports ISO 9001 control limits
    - AI Agile Team: Provides baseline for anomaly detection

    Attributes:
        machine: The machine this threshold applies to
        data_type: The telemetry data type
        min_value: Minimum acceptable value (alert if below)
        max_value: Maximum acceptable value (alert if above)
        warning_min: Warning threshold (lower)
        warning_max: Warning threshold (upper)
        alert_severity: Severity of alerts generated when threshold is violated
        enabled: Whether this threshold is active
    """

    class Meta:
        """Model metadata."""

        verbose_name = _('Machine Telemetry Threshold')
        verbose_name_plural = _('Machine Telemetry Thresholds')
        unique_together = [['machine', 'data_type']]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    machine = models.ForeignKey(
        MachineConfig,
        on_delete=models.CASCADE,
        related_name='telemetry_thresholds',
        verbose_name=_('Machine'),
        help_text=_('The machine this threshold applies to')
    )

    data_type = models.CharField(
        max_length=10,
        choices=TelemetryDataType.choices,
        verbose_name=_('Data Type'),
        help_text=_('The telemetry data type this threshold applies to')
    )

    min_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_('Minimum Value'),
        help_text=_('Alert if value falls below this threshold')
    )

    max_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_('Maximum Value'),
        help_text=_('Alert if value exceeds this threshold')
    )

    warning_min = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_('Warning Minimum'),
        help_text=_('Warning threshold (lower)')
    )

    warning_max = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_('Warning Maximum'),
        help_text=_('Warning threshold (upper)')
    )

    alert_severity = models.CharField(
        max_length=10,
        choices=AlertSeverity.choices,
        default=AlertSeverity.HIGH,
        verbose_name=_('Alert Severity'),
        help_text=_('Severity of alerts generated when threshold is violated')
    )

    enabled = models.BooleanField(
        default=True,
        verbose_name=_('Enabled'),
        help_text=_('Whether this threshold is active')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    def __str__(self) -> str:
        """String representation of threshold."""
        return f'{self.machine.name} - {self.get_data_type_display()} Threshold'

    def check_value(self, value: Decimal) -> tuple[bool, Optional[str], Optional[AlertSeverity]]:
        """Check if a value violates this threshold.

        Args:
            value: The telemetry value to check

        Returns:
            Tuple of (is_violation, violation_message, severity)
        """
        if not self.enabled:
            return (False, None, None)

        # Check critical thresholds
        if self.min_value is not None and value < self.min_value:
            return (True, f'Value {value} below minimum threshold {self.min_value}', self.alert_severity)
        if self.max_value is not None and value > self.max_value:
            return (True, f'Value {value} above maximum threshold {self.max_value}', self.alert_severity)

        # Check warning thresholds
        if self.warning_min is not None and value < self.warning_min:
            return (True, f'Value {value} below warning threshold {self.warning_min}', AlertSeverity.LOW)
        if self.warning_max is not None and value > self.warning_max:
            return (True, f'Value {value} above warning threshold {self.warning_max}', AlertSeverity.LOW)

        return (False, None, None)
