"""Models for the machine app."""

import re
import uuid
from datetime import timedelta
from typing import Literal, Optional

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.html import escape, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

import common.models
from machine import registry


class MachineConfig(models.Model):
    """A Machine objects represents a physical machine."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(
        unique=True,
        max_length=255,
        verbose_name=_('Name'),
        help_text=_('Name of machine'),
    )

    machine_type = models.CharField(
        max_length=255, verbose_name=_('Machine Type'), help_text=_('Type of machine')
    )

    driver = models.CharField(
        max_length=255,
        verbose_name=_('Driver'),
        help_text=_('Driver used for the machine'),
    )

    active = models.BooleanField(
        default=True, verbose_name=_('Active'), help_text=_('Machines can be disabled')
    )

    def __str__(self) -> str:
        """String representation of a machine."""
        return f'{self.name}'

    def save(self, *args, **kwargs) -> None:
        """Custom save function to capture creates/updates to notify the registry."""
        created = self._state.adding

        old_machine = None
        if (
            not created
            and self.pk
            and (old_machine := MachineConfig.objects.get(pk=self.pk))
        ):
            old_machine = old_machine.to_dict()

        super().save(*args, **kwargs)

        if created:
            # machine was created, add it to the machine registry
            registry.add_machine(self, initialize=True)
        elif old_machine:
            # machine was updated, invoke update hook
            # elif acts just as a type gate, old_machine should be defined always
            # if machine is not created now which is already handled above
            registry.update_machine(old_machine, self)

    def delete(self, *args, **kwargs):
        """Remove machine from registry first."""
        if self.machine:
            registry.remove_machine(self.machine)

        return super().delete(*args, **kwargs)

    def to_dict(self):
        """Serialize a machine config to a dict including setting."""
        machine = {f.name: f.value_to_string(self) for f in self._meta.fields}
        machine['settings'] = {
            (setting.config_type, setting.key): setting.value
            for setting in MachineSetting.objects.filter(machine_config=self)
        }
        return machine

    @property
    def machine(self):
        """Machine instance getter."""
        return registry.get_machine(self.pk)

    @property
    def errors(self):
        """Machine errors getter."""
        return getattr(self.machine, 'errors', [])

    @admin.display(boolean=True, description=_('Driver available'))
    def is_driver_available(self) -> bool:
        """Status if driver for machine is available."""
        return self.machine is not None and self.machine.driver is not None

    @admin.display(boolean=True, description=_('No errors'))
    def no_errors(self) -> bool:
        """Status if machine has errors."""
        return len(self.errors) == 0

    @admin.display(boolean=True, description=_('Initialized'))
    def initialized(self) -> bool:
        """Status if machine is initialized."""
        return getattr(self.machine, 'initialized', False)

    @admin.display(description=_('Errors'))
    def get_admin_errors(self):
        """Get machine errors for django admin interface."""
        return format_html_join(
            mark_safe('<br>'), '{}', ((str(error),) for error in self.errors)
        ) or mark_safe(f'<i>{_("No errors")}</i>')

    @admin.display(description=_('Machine status'))
    def get_machine_status(self):
        """Get machine status for django admin interface."""
        if self.machine is None:
            return None

        out = mark_safe(self.machine.status.render(self.machine.status))

        if self.machine.status_text:
            out += escape(f' ({self.machine.status_text})')

        return out


class MachineSetting(common.models.BaseInvenTreeSetting):
    """This models represents settings for individual machines."""

    typ = 'machine_config'
    extra_unique_fields = ['machine_config', 'config_type']

    class Meta:
        """Meta for MachineSetting."""

        unique_together = [('machine_config', 'config_type', 'key')]

    class ConfigType(models.TextChoices):
        """Machine setting config type enum."""

        MACHINE = 'M', _('Machine')
        DRIVER = 'D', _('Driver')

    def to_native_value(self):
        """Return the 'native' value of this setting."""
        return self.__class__.get_setting(
            self.key, machine_config=self.machine_config, config_type=self.config_type
        )

    machine_config = models.ForeignKey(
        MachineConfig,
        related_name='settings',
        verbose_name=_('Machine Config'),
        on_delete=models.CASCADE,
    )

    config_type = models.CharField(
        verbose_name=_('Config type'), max_length=1, choices=ConfigType.choices
    )

    def save(self, *args, **kwargs) -> None:
        """Custom save method to notify the registry on changes."""
        old_machine = self.machine_config.to_dict()

        super().save(*args, **kwargs)

        registry.update_machine(old_machine, self.machine_config)

    @classmethod
    def get_config_type(cls, config_type_str: Literal['M', 'D']):
        """Helper method to get the correct enum value for easier usage with literal strings."""
        if config_type_str == 'M':
            return cls.ConfigType.MACHINE
        elif config_type_str == 'D':
            return cls.ConfigType.DRIVER

    @classmethod
    def get_setting_definition(cls, key, **kwargs):
        """In the BaseInvenTreeSetting class, we have a class attribute named 'SETTINGS'.

        which is a dict object that fully defines all the setting parameters.

        Here, unlike the BaseInvenTreeSetting, we do not know the definitions of all settings
        'ahead of time' (as they are defined externally in the machine driver).

        Settings can be provided by the caller, as kwargs['settings'].

        If not provided, we'll look at the machine registry to see what settings this machine driver requires
        """
        if 'settings' not in kwargs:
            machine_config: Optional[MachineConfig] = kwargs.pop('machine_config', None)
            if machine_config and machine_config.machine:
                config_type = kwargs.get('config_type')
                if config_type == cls.ConfigType.DRIVER:
                    kwargs['settings'] = machine_config.machine.driver_settings
                elif config_type == cls.ConfigType.MACHINE:
                    kwargs['settings'] = machine_config.machine.machine_settings

        return super().get_setting_definition(key, **kwargs)


class MachineTelemetry(models.Model):
    """Model to store telemetry data from manufacturing equipment.

    This model captures real-time telemetry data points from machines,
    supporting Industry 4.0 integration for manufacturing execution systems.
    """

    # Regex pattern for validating metric names (alphanumeric, underscores, hyphens)
    METRIC_NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,99}$')

    # Maximum allowed timestamp offset from current time (in hours)
    MAX_TIMESTAMP_FUTURE_HOURS = 1
    MAX_TIMESTAMP_PAST_DAYS = 30

    class MetricType(models.TextChoices):
        """Predefined metric types for manufacturing equipment telemetry."""

        TEMPERATURE = 'temperature', _('Temperature')
        PRESSURE = 'pressure', _('Pressure')
        SPEED = 'speed', _('Speed')
        VIBRATION = 'vibration', _('Vibration')
        POWER = 'power', _('Power Consumption')
        CYCLE_COUNT = 'cycle_count', _('Cycle Count')
        RUNTIME = 'runtime', _('Runtime Hours')
        ERROR_COUNT = 'error_count', _('Error Count')
        THROUGHPUT = 'throughput', _('Throughput')
        EFFICIENCY = 'efficiency', _('Efficiency')
        HUMIDITY = 'humidity', _('Humidity')
        FORCE = 'force', _('Force')
        POSITION = 'position', _('Position')
        FLOW_RATE = 'flow_rate', _('Flow Rate')
        CUSTOM = 'custom', _('Custom Metric')

    class Meta:
        """Meta options for MachineTelemetry."""

        verbose_name = _('Machine Telemetry')
        verbose_name_plural = _('Machine Telemetry')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['machine_config', 'timestamp']),
            models.Index(fields=['machine_config', 'metric_type']),
            models.Index(fields=['timestamp']),
        ]

    id = models.BigAutoField(primary_key=True)

    machine_config = models.ForeignKey(
        MachineConfig,
        on_delete=models.CASCADE,
        related_name='telemetry_data',
        verbose_name=_('Machine'),
        help_text=_('The machine this telemetry data belongs to'),
    )

    timestamp = models.DateTimeField(
        verbose_name=_('Timestamp'),
        help_text=_('Timestamp when the telemetry data was recorded'),
        db_index=True,
    )

    metric_type = models.CharField(
        max_length=50,
        choices=MetricType.choices,
        verbose_name=_('Metric Type'),
        help_text=_('Type of metric being recorded'),
    )

    metric_name = models.CharField(
        max_length=100,
        verbose_name=_('Metric Name'),
        help_text=_('Specific name or identifier for the metric'),
    )

    value = models.FloatField(
        verbose_name=_('Value'),
        help_text=_('Numeric value of the telemetry reading'),
        validators=[MinValueValidator(-1e15), MaxValueValidator(1e15)],
    )

    unit = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name=_('Unit'),
        help_text=_('Unit of measurement (e.g., celsius, psi, rpm)'),
    )

    metadata = models.JSONField(
        blank=True,
        null=True,
        default=None,
        verbose_name=_('Metadata'),
        help_text=_('Additional metadata as JSON (e.g., sensor ID, location)'),
    )

    created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created'),
        help_text=_('Timestamp when this record was created in the database'),
    )

    def __str__(self) -> str:
        """String representation of telemetry data."""
        return (
            f'{self.machine_config.name} - {self.metric_name}: {self.value} {self.unit}'
        )

    def clean(self):
        """Validate telemetry data before saving."""
        super().clean()

        # Validate metric_name format (alphanumeric, underscores, hyphens only)
        if self.metric_name:
            # Sanitize: remove dangerous characters
            sanitized_name = re.sub(r'[<>"\';&|`$()]', '', self.metric_name.strip())
            if sanitized_name != self.metric_name:
                self.metric_name = sanitized_name

            if not self.METRIC_NAME_PATTERN.match(self.metric_name):
                raise ValidationError({
                    'metric_name': _(
                        'Metric name must start with a letter and contain only '
                        'alphanumeric characters, underscores, or hyphens (max 100 chars)'
                    )
                })

        # Validate timestamp is within acceptable range
        if self.timestamp:
            now = timezone.now()
            max_future = now + timedelta(hours=self.MAX_TIMESTAMP_FUTURE_HOURS)
            max_past = now - timedelta(days=self.MAX_TIMESTAMP_PAST_DAYS)

            if self.timestamp > max_future:
                raise ValidationError({
                    'timestamp': _(
                        'Timestamp cannot be more than %(hours)s hour(s) in the future'
                    )
                    % {'hours': self.MAX_TIMESTAMP_FUTURE_HOURS}
                })

            if self.timestamp < max_past:
                raise ValidationError({
                    'timestamp': _(
                        'Timestamp cannot be more than %(days)s day(s) in the past'
                    )
                    % {'days': self.MAX_TIMESTAMP_PAST_DAYS}
                })

        # Sanitize unit field
        if self.unit:
            self.unit = re.sub(r'[<>"\';&|`$()]', '', self.unit.strip())[:50]

        # Validate metadata if provided
        if self.metadata is not None:
            if not isinstance(self.metadata, dict):
                raise ValidationError({
                    'metadata': _('Metadata must be a JSON object (dictionary)')
                })

    def save(self, *args, **kwargs):
        """Save telemetry data with validation."""
        self.full_clean()
        super().save(*args, **kwargs)


class TelemetryAlert(models.Model):
    """Model to store alerts generated from telemetry anomaly detection.

    Alerts are generated when telemetry data exceeds configured thresholds
    or when anomalies are detected in the data patterns.
    """

    class AlertSeverity(models.TextChoices):
        """Alert severity levels."""

        INFO = 'info', _('Information')
        WARNING = 'warning', _('Warning')
        CRITICAL = 'critical', _('Critical')
        EMERGENCY = 'emergency', _('Emergency')

    class AlertType(models.TextChoices):
        """Types of alerts that can be generated."""

        THRESHOLD_HIGH = 'threshold_high', _('High Threshold Exceeded')
        THRESHOLD_LOW = 'threshold_low', _('Low Threshold Exceeded')
        RATE_OF_CHANGE = 'rate_of_change', _('Abnormal Rate of Change')
        MISSING_DATA = 'missing_data', _('Missing Data')
        PATTERN_ANOMALY = 'pattern_anomaly', _('Pattern Anomaly')
        EQUIPMENT_FAULT = 'equipment_fault', _('Equipment Fault')
        MAINTENANCE_DUE = 'maintenance_due', _('Maintenance Due')
        CUSTOM = 'custom', _('Custom Alert')

    class Meta:
        """Meta options for TelemetryAlert."""

        verbose_name = _('Telemetry Alert')
        verbose_name_plural = _('Telemetry Alerts')
        ordering = ['-created']
        indexes = [
            models.Index(fields=['machine_config', 'created']),
            models.Index(fields=['severity', 'acknowledged']),
            models.Index(fields=['created']),
        ]

    id = models.BigAutoField(primary_key=True)

    machine_config = models.ForeignKey(
        MachineConfig,
        on_delete=models.CASCADE,
        related_name='telemetry_alerts',
        verbose_name=_('Machine'),
        help_text=_('The machine this alert is associated with'),
    )

    alert_type = models.CharField(
        max_length=50,
        choices=AlertType.choices,
        verbose_name=_('Alert Type'),
        help_text=_('Type of alert'),
    )

    severity = models.CharField(
        max_length=20,
        choices=AlertSeverity.choices,
        default=AlertSeverity.WARNING,
        verbose_name=_('Severity'),
        help_text=_('Severity level of the alert'),
    )

    metric_type = models.CharField(
        max_length=50,
        choices=MachineTelemetry.MetricType.choices,
        blank=True,
        default='',
        verbose_name=_('Metric Type'),
        help_text=_('The metric type that triggered this alert'),
    )

    metric_name = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('Metric Name'),
        help_text=_('The specific metric that triggered this alert'),
    )

    message = models.TextField(
        verbose_name=_('Message'), help_text=_('Detailed alert message')
    )

    threshold_value = models.FloatField(
        blank=True,
        null=True,
        verbose_name=_('Threshold Value'),
        help_text=_('The threshold value that was exceeded'),
    )

    actual_value = models.FloatField(
        blank=True,
        null=True,
        verbose_name=_('Actual Value'),
        help_text=_('The actual value that triggered the alert'),
    )

    telemetry_data = models.ForeignKey(
        MachineTelemetry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name=_('Related Telemetry'),
        help_text=_('The telemetry data point that triggered this alert'),
    )

    acknowledged = models.BooleanField(
        default=False,
        verbose_name=_('Acknowledged'),
        help_text=_('Whether this alert has been acknowledged'),
    )

    acknowledged_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_telemetry_alerts',
        verbose_name=_('Acknowledged By'),
        help_text=_('User who acknowledged this alert'),
    )

    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Acknowledged At'),
        help_text=_('Timestamp when the alert was acknowledged'),
    )

    created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created'),
        help_text=_('Timestamp when this alert was created'),
    )

    metadata = models.JSONField(
        blank=True,
        null=True,
        default=None,
        verbose_name=_('Metadata'),
        help_text=_('Additional metadata about the alert'),
    )

    def __str__(self) -> str:
        """String representation of the alert."""
        return f'{self.machine_config.name} - {self.get_severity_display()}: {self.get_alert_type_display()}'

    def clean(self):
        """Validate alert data before saving."""
        super().clean()

        # Sanitize message field
        if self.message:
            self.message = re.sub(r'[<>"\';&|`$()]', '', self.message.strip())

        # Sanitize metric_name field
        if self.metric_name:
            self.metric_name = re.sub(r'[<>"\';&|`$()]', '', self.metric_name.strip())

        # Validate metadata if provided
        if self.metadata is not None:
            if not isinstance(self.metadata, dict):
                raise ValidationError({
                    'metadata': _('Metadata must be a JSON object (dictionary)')
                })

    def save(self, *args, **kwargs):
        """Save alert with validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def acknowledge(self, user):
        """Mark this alert as acknowledged by the given user."""
        self.acknowledged = True
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        self.save()


class TelemetryThreshold(models.Model):
    """Model to configure thresholds for telemetry anomaly detection.

    Thresholds define the acceptable ranges for telemetry metrics.
    When values exceed these thresholds, alerts are generated.
    """

    class Meta:
        """Meta options for TelemetryThreshold."""

        verbose_name = _('Telemetry Threshold')
        verbose_name_plural = _('Telemetry Thresholds')
        unique_together = [('machine_config', 'metric_type', 'metric_name')]

    id = models.BigAutoField(primary_key=True)

    machine_config = models.ForeignKey(
        MachineConfig,
        on_delete=models.CASCADE,
        related_name='telemetry_thresholds',
        verbose_name=_('Machine'),
        help_text=_('The machine this threshold applies to'),
    )

    metric_type = models.CharField(
        max_length=50,
        choices=MachineTelemetry.MetricType.choices,
        verbose_name=_('Metric Type'),
        help_text=_('Type of metric this threshold applies to'),
    )

    metric_name = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('Metric Name'),
        help_text=_(
            'Specific metric name (leave blank to apply to all metrics of this type)'
        ),
    )

    min_value = models.FloatField(
        blank=True,
        null=True,
        verbose_name=_('Minimum Value'),
        help_text=_('Minimum acceptable value (alerts generated if below)'),
    )

    max_value = models.FloatField(
        blank=True,
        null=True,
        verbose_name=_('Maximum Value'),
        help_text=_('Maximum acceptable value (alerts generated if above)'),
    )

    warning_min = models.FloatField(
        blank=True,
        null=True,
        verbose_name=_('Warning Minimum'),
        help_text=_('Warning threshold for minimum value'),
    )

    warning_max = models.FloatField(
        blank=True,
        null=True,
        verbose_name=_('Warning Maximum'),
        help_text=_('Warning threshold for maximum value'),
    )

    rate_of_change_threshold = models.FloatField(
        blank=True,
        null=True,
        verbose_name=_('Rate of Change Threshold'),
        help_text=_('Maximum acceptable rate of change per minute'),
    )

    enabled = models.BooleanField(
        default=True,
        verbose_name=_('Enabled'),
        help_text=_('Whether this threshold is active'),
    )

    created = models.DateTimeField(auto_now_add=True, verbose_name=_('Created'))

    updated = models.DateTimeField(auto_now=True, verbose_name=_('Updated'))

    def __str__(self) -> str:
        """String representation of the threshold."""
        name = self.metric_name or self.get_metric_type_display()
        return f'{self.machine_config.name} - {name} threshold'

    def clean(self):
        """Validate threshold configuration."""
        super().clean()

        # Validate that at least one threshold is set
        if (
            self.min_value is None
            and self.max_value is None
            and self.warning_min is None
            and self.warning_max is None
            and self.rate_of_change_threshold is None
        ):
            raise ValidationError(_('At least one threshold value must be configured'))

        # Validate min/max relationship
        if self.min_value is not None and self.max_value is not None:
            if self.min_value >= self.max_value:
                raise ValidationError({
                    'min_value': _('Minimum value must be less than maximum value')
                })

        # Validate warning thresholds are within min/max
        if self.warning_min is not None and self.min_value is not None:
            if self.warning_min < self.min_value:
                raise ValidationError({
                    'warning_min': _('Warning minimum must be >= minimum value')
                })

        if self.warning_max is not None and self.max_value is not None:
            if self.warning_max > self.max_value:
                raise ValidationError({
                    'warning_max': _('Warning maximum must be <= maximum value')
                })

        # Sanitize metric_name
        if self.metric_name:
            self.metric_name = re.sub(r'[<>"\';&|`$()]', '', self.metric_name.strip())

    def save(self, *args, **kwargs):
        """Save threshold with validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    def check_value(self, value: float) -> tuple[bool, Optional[str], Optional[str]]:
        """Check if a value violates this threshold.

        Args:
            value: The telemetry value to check

        Returns:
            Tuple of (is_violation, alert_type, severity)
            Returns (False, None, None) if no violation
        """
        if not self.enabled:
            return (False, None, None)

        # Check critical thresholds first
        if self.max_value is not None and value > self.max_value:
            return (
                True,
                TelemetryAlert.AlertType.THRESHOLD_HIGH,
                TelemetryAlert.AlertSeverity.CRITICAL,
            )

        if self.min_value is not None and value < self.min_value:
            return (
                True,
                TelemetryAlert.AlertType.THRESHOLD_LOW,
                TelemetryAlert.AlertSeverity.CRITICAL,
            )

        # Check warning thresholds
        if self.warning_max is not None and value > self.warning_max:
            return (
                True,
                TelemetryAlert.AlertType.THRESHOLD_HIGH,
                TelemetryAlert.AlertSeverity.WARNING,
            )

        if self.warning_min is not None and value < self.warning_min:
            return (
                True,
                TelemetryAlert.AlertType.THRESHOLD_LOW,
                TelemetryAlert.AlertSeverity.WARNING,
            )

        return (False, None, None)
