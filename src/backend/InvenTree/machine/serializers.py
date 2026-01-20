"""Serializers for the machine app."""

import re
from datetime import timedelta
from typing import Union

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from common.serializers import GenericReferencedSettingSerializer
from InvenTree.helpers_mixin import ClassProviderMixin
from machine import registry
from machine.models import (
    MachineConfig,
    MachineSetting,
    MachineTelemetry,
    TelemetryAlert,
    TelemetryThreshold,
)


class MachineConfigSerializer(serializers.ModelSerializer):
    """Serializer for a MachineConfig."""

    class Meta:
        """Meta for serializer."""

        model = MachineConfig
        fields = [
            'pk',
            'name',
            'machine_type',
            'driver',
            'initialized',
            'active',
            'status',
            'status_model',
            'status_text',
            'machine_errors',
            'is_driver_available',
            'restart_required',
        ]

        read_only_fields = ['machine_type', 'driver']

    initialized = serializers.SerializerMethodField('get_initialized')
    status = serializers.SerializerMethodField('get_status')
    status_model = serializers.SerializerMethodField('get_status_model')
    status_text = serializers.SerializerMethodField('get_status_text')
    machine_errors = serializers.SerializerMethodField('get_errors')
    is_driver_available = serializers.SerializerMethodField('get_is_driver_available')
    restart_required = serializers.SerializerMethodField('get_restart_required')

    def get_initialized(self, obj: MachineConfig) -> bool:
        """Serializer method for the initialized field."""
        return getattr(obj.machine, 'initialized', False)

    def get_status(self, obj: MachineConfig) -> int:
        """Serializer method for the status field."""
        status = getattr(obj.machine, 'status', None)
        if status is not None:
            return status.value
        return -1

    def get_status_model(self, obj: MachineConfig) -> Union[str, None]:
        """Serializer method for the status model field."""
        if obj.machine and obj.machine.MACHINE_STATUS:
            return obj.machine.MACHINE_STATUS.__name__

    def get_status_text(self, obj: MachineConfig) -> str:
        """Serializer method for the status text field."""
        return getattr(obj.machine, 'status_text', '')

    def get_errors(self, obj: MachineConfig) -> list[str]:
        """Serializer method for the errors field."""
        return [str(err) for err in obj.errors]

    def get_is_driver_available(self, obj: MachineConfig) -> bool:
        """Serializer method for the is_driver_available field."""
        return obj.is_driver_available()

    def get_restart_required(self, obj: MachineConfig) -> bool:
        """Serializer method for the restart_required field."""
        return getattr(obj.machine, 'restart_required', False)


class MachineConfigCreateSerializer(MachineConfigSerializer):
    """Serializer for creating a MachineConfig."""

    class Meta(MachineConfigSerializer.Meta):
        """Meta for serializer."""

        read_only_fields = list(
            set(MachineConfigSerializer.Meta.read_only_fields)
            - {'machine_type', 'driver'}
        )


class MachineSettingSerializer(GenericReferencedSettingSerializer):
    """Serializer for the MachineSetting model."""

    MODEL = MachineSetting
    EXTRA_FIELDS = ['config_type']

    def __init__(self, *args, **kwargs):
        """Custom init method to make the config_type field read only."""
        super().__init__(*args, **kwargs)

        self.Meta.read_only_fields = ['config_type']  # type: ignore


class BaseMachineClassSerializer(serializers.Serializer):
    """Serializer for a BaseClass."""

    class Meta:
        """Meta for a serializer."""

        fields = [
            'slug',
            'name',
            'description',
            'provider_file',
            'provider_plugin',
            'is_builtin',
        ]

        read_only_fields = fields

    slug = serializers.SlugField(source='SLUG')
    name = serializers.CharField(source='NAME')
    description = serializers.CharField(source='DESCRIPTION')
    provider_file = serializers.SerializerMethodField('get_provider_file')
    provider_plugin = serializers.SerializerMethodField('get_provider_plugin')
    is_builtin = serializers.SerializerMethodField('get_is_builtin')

    def get_provider_file(self, obj: ClassProviderMixin) -> str:
        """Serializer method for the provider_file field."""
        return obj.get_provider_file()

    def get_provider_plugin(self, obj: ClassProviderMixin) -> Union[dict, None]:
        """Serializer method for the provider_plugin field."""
        plugin = obj.get_provider_plugin()
        if plugin:
            return {
                'slug': plugin.slug,
                'name': plugin.human_name,
                'pk': getattr(plugin.plugin_config(), 'pk', None),
            }
        return None

    def get_is_builtin(self, obj: ClassProviderMixin) -> bool:
        """Serializer method for the is_builtin field."""
        return obj.get_is_builtin()


class MachineTypeSerializer(BaseMachineClassSerializer):
    """Serializer for a BaseMachineType class."""

    class Meta(BaseMachineClassSerializer.Meta):
        """Meta for a serializer."""

        fields = [*BaseMachineClassSerializer.Meta.fields]


class MachineDriverSerializer(BaseMachineClassSerializer):
    """Serializer for a BaseMachineDriver class."""

    class Meta(BaseMachineClassSerializer.Meta):
        """Meta for a serializer."""

        fields = [*BaseMachineClassSerializer.Meta.fields, 'machine_type', 'errors']

    machine_type = serializers.SlugField(read_only=True)

    driver_errors = serializers.SerializerMethodField('get_errors')

    def get_errors(self, obj) -> list[str]:
        """Serializer method for the errors field."""
        driver_instance = registry.get_driver_instance(obj.SLUG)

        if driver_instance is None:
            return []
        return [str(err) for err in driver_instance.errors]


class MachineRegistryErrorSerializer(serializers.Serializer):
    """Serializer for a machine registry error."""

    class Meta:
        """Meta for a serializer."""

        fields = ['message']

    message = serializers.CharField()


class MachineRegistryStatusSerializer(serializers.Serializer):
    """Serializer for machine registry status."""

    class Meta:
        """Meta for a serializer."""

        fields = ['registry_errors']

    registry_errors = serializers.ListField(child=MachineRegistryErrorSerializer())


class MachineRestartSerializer(serializers.Serializer):
    """Serializer for the machine restart response."""

    class Meta:
        """Meta for a serializer."""

        fields = ['ok']

    ok = serializers.BooleanField()


class MachineTelemetrySerializer(serializers.ModelSerializer):
    """Serializer for MachineTelemetry model."""

    class Meta:
        """Meta for serializer."""

        model = MachineTelemetry
        fields = [
            'pk',
            'machine_config',
            'timestamp',
            'metric_type',
            'metric_name',
            'value',
            'unit',
            'metadata',
            'created',
        ]
        read_only_fields = ['pk', 'created']

    def validate_metric_name(self, value):
        """Validate and sanitize metric_name field."""
        if not value:
            raise serializers.ValidationError(_('Metric name is required'))

        # Sanitize: remove dangerous characters
        sanitized = re.sub(r'[<>"\';&|`$()]', '', value.strip())

        # Validate format
        if not MachineTelemetry.METRIC_NAME_PATTERN.match(sanitized):
            raise serializers.ValidationError(
                _(
                    'Metric name must start with a letter and contain only '
                    'alphanumeric characters, underscores, or hyphens (max 100 chars)'
                )
            )

        return sanitized

    def validate_timestamp(self, value):
        """Validate timestamp is within acceptable range."""
        if not value:
            raise serializers.ValidationError(_('Timestamp is required'))

        now = timezone.now()
        max_future = now + timedelta(hours=MachineTelemetry.MAX_TIMESTAMP_FUTURE_HOURS)
        max_past = now - timedelta(days=MachineTelemetry.MAX_TIMESTAMP_PAST_DAYS)

        if value > max_future:
            raise serializers.ValidationError(
                _('Timestamp cannot be more than %(hours)s hour(s) in the future')
                % {'hours': MachineTelemetry.MAX_TIMESTAMP_FUTURE_HOURS}
            )

        if value < max_past:
            raise serializers.ValidationError(
                _('Timestamp cannot be more than %(days)s day(s) in the past')
                % {'days': MachineTelemetry.MAX_TIMESTAMP_PAST_DAYS}
            )

        return value

    def validate_unit(self, value):
        """Sanitize unit field."""
        if value:
            return re.sub(r'[<>"\';&|`$()]', '', value.strip())[:50]
        return value

    def validate_metadata(self, value):
        """Validate metadata is a dictionary if provided."""
        if value is not None and not isinstance(value, dict):
            raise serializers.ValidationError(
                _('Metadata must be a JSON object (dictionary)')
            )
        return value

    def validate_machine_config(self, value):
        """Validate machine exists and is active."""
        if not value.active:
            raise serializers.ValidationError(
                _('Cannot submit telemetry for inactive machine')
            )
        return value


class MachineTelemetryBatchSerializer(serializers.Serializer):
    """Serializer for batch telemetry data submission."""

    class Meta:
        """Meta for serializer."""

        fields = ['telemetry_data']

    telemetry_data = MachineTelemetrySerializer(many=True)

    def validate_telemetry_data(self, value):
        """Validate batch telemetry data."""
        if not value:
            raise serializers.ValidationError(
                _('At least one telemetry data point is required')
            )

        if len(value) > 1000:
            raise serializers.ValidationError(
                _('Maximum of 1000 telemetry data points allowed per batch')
            )

        return value

    def create(self, validated_data):
        """Create multiple telemetry records."""
        telemetry_items = validated_data.get('telemetry_data', [])
        created_items = []

        for item_data in telemetry_items:
            telemetry = MachineTelemetry.objects.create(**item_data)
            created_items.append(telemetry)

        return {'telemetry_data': created_items}


class TelemetryAlertSerializer(serializers.ModelSerializer):
    """Serializer for TelemetryAlert model."""

    class Meta:
        """Meta for serializer."""

        model = TelemetryAlert
        fields = [
            'pk',
            'machine_config',
            'alert_type',
            'severity',
            'metric_type',
            'metric_name',
            'message',
            'threshold_value',
            'actual_value',
            'telemetry_data',
            'acknowledged',
            'acknowledged_by',
            'acknowledged_at',
            'created',
            'metadata',
        ]
        read_only_fields = ['pk', 'created', 'acknowledged_by', 'acknowledged_at']

    def validate_message(self, value):
        """Sanitize message field."""
        if value:
            return re.sub(r'[<>"\';&|`$()]', '', value.strip())
        return value

    def validate_metric_name(self, value):
        """Sanitize metric_name field."""
        if value:
            return re.sub(r'[<>"\';&|`$()]', '', value.strip())
        return value

    def validate_metadata(self, value):
        """Validate metadata is a dictionary if provided."""
        if value is not None and not isinstance(value, dict):
            raise serializers.ValidationError(
                _('Metadata must be a JSON object (dictionary)')
            )
        return value


class TelemetryAlertAcknowledgeSerializer(serializers.Serializer):
    """Serializer for acknowledging telemetry alerts."""

    class Meta:
        """Meta for serializer."""

        fields = ['acknowledged']

    acknowledged = serializers.BooleanField(default=True)


class TelemetryThresholdSerializer(serializers.ModelSerializer):
    """Serializer for TelemetryThreshold model."""

    class Meta:
        """Meta for serializer."""

        model = TelemetryThreshold
        fields = [
            'pk',
            'machine_config',
            'metric_type',
            'metric_name',
            'min_value',
            'max_value',
            'warning_min',
            'warning_max',
            'rate_of_change_threshold',
            'enabled',
            'created',
            'updated',
        ]
        read_only_fields = ['pk', 'created', 'updated']

    def validate_metric_name(self, value):
        """Sanitize metric_name field."""
        if value:
            return re.sub(r'[<>"\';&|`$()]', '', value.strip())
        return value

    def validate(self, data):
        """Validate threshold configuration."""
        # Validate that at least one threshold is set
        if (
            data.get('min_value') is None
            and data.get('max_value') is None
            and data.get('warning_min') is None
            and data.get('warning_max') is None
            and data.get('rate_of_change_threshold') is None
        ):
            raise serializers.ValidationError(
                _('At least one threshold value must be configured')
            )

        # Validate min/max relationship
        min_val = data.get('min_value')
        max_val = data.get('max_value')
        if min_val is not None and max_val is not None:
            if min_val >= max_val:
                raise serializers.ValidationError({
                    'min_value': _('Minimum value must be less than maximum value')
                })

        # Validate warning thresholds are within min/max
        warning_min = data.get('warning_min')
        warning_max = data.get('warning_max')

        if warning_min is not None and min_val is not None:
            if warning_min < min_val:
                raise serializers.ValidationError({
                    'warning_min': _('Warning minimum must be >= minimum value')
                })

        if warning_max is not None and max_val is not None:
            if warning_max > max_val:
                raise serializers.ValidationError({
                    'warning_max': _('Warning maximum must be <= maximum value')
                })

        return data


class MachineTelemetryStatusSerializer(serializers.Serializer):
    """Serializer for machine telemetry status summary."""

    class Meta:
        """Meta for serializer."""

        fields = [
            'machine_config',
            'machine_name',
            'latest_telemetry',
            'active_alerts_count',
            'unacknowledged_alerts_count',
            'last_telemetry_timestamp',
            'telemetry_count_24h',
        ]

    machine_config = serializers.UUIDField()
    machine_name = serializers.CharField()
    latest_telemetry = MachineTelemetrySerializer(many=True, read_only=True)
    active_alerts_count = serializers.IntegerField()
    unacknowledged_alerts_count = serializers.IntegerField()
    last_telemetry_timestamp = serializers.DateTimeField(allow_null=True)
    telemetry_count_24h = serializers.IntegerField()
