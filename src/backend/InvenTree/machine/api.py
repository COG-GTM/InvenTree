"""JSON API for the machine app."""

from datetime import timedelta

from django.db.models import Max
from django.urls import include, path, re_path
from django.utils import timezone

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

import InvenTree.permissions
import machine.serializers as MachineSerializers
from InvenTree.filters import SEARCH_ORDER_FILTER
from InvenTree.mixins import ListCreateAPI, RetrieveUpdateAPI, RetrieveUpdateDestroyAPI
from machine import registry
from machine.models import (
    MachineConfig,
    MachineSetting,
    MachineTelemetry,
    TelemetryAlert,
    TelemetryThreshold,
)


class MachineList(ListCreateAPI):
    """API endpoint for list of Machine objects.

    - GET: Return a list of all Machine objects
    - POST: create a MachineConfig
    """

    queryset = MachineConfig.objects.all()
    serializer_class = MachineSerializers.MachineConfigSerializer

    def get_serializer_class(self):
        """Allow driver, machine_type fields on creation."""
        if self.request.method == 'POST':
            return MachineSerializers.MachineConfigCreateSerializer
        return super().get_serializer_class()

    filter_backends = SEARCH_ORDER_FILTER

    filterset_fields = ['machine_type', 'driver', 'active']

    ordering_fields = ['name', 'machine_type', 'driver', 'active']

    ordering = ['-active', 'machine_type']

    search_fields = ['name']


class MachineDetail(RetrieveUpdateDestroyAPI):
    """API detail endpoint for MachineConfig object.

    - GET: return a single MachineConfig
    - PUT: update a MachineConfig
    - PATCH: partial update a MachineConfig
    - DELETE: delete a MachineConfig
    """

    queryset = MachineConfig.objects.all()
    serializer_class = MachineSerializers.MachineConfigSerializer


def get_machine(machine_pk):
    """Get machine by pk.

    Raises:
        NotFound: If machine is not found

    Returns:
        BaseMachineType: The machine instance in the registry
    """
    machine = registry.get_machine(machine_pk)

    if machine is None:
        raise NotFound(detail=f"Machine '{machine_pk}' not found")

    return machine


class MachineSettingList(APIView):
    """List endpoint for all machine related settings.

    - GET: return all settings for a machine config
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        responses={200: MachineSerializers.MachineSettingSerializer(many=True)}
    )
    def get(self, request, pk):
        """Return all settings for a machine config."""
        machine = get_machine(pk)

        all_settings = []

        for settings, config_type in machine.setting_types:
            settings_dict = MachineSetting.all_settings(
                settings_definition=settings,
                machine_config=machine.machine_config,
                config_type=config_type,
            )
            all_settings.extend(list(settings_dict.values()))

        results = MachineSerializers.MachineSettingSerializer(
            all_settings, many=True
        ).data
        return Response(results)


class MachineSettingDetail(RetrieveUpdateAPI):
    """Detail endpoint for a machine-specific setting.

    - GET: Get machine setting detail
    - PUT: Update machine setting
    - PATCH: Update machine setting

    (Note that these cannot be created or deleted via API)
    """

    lookup_field = 'key'
    queryset = MachineSetting.objects.all()
    serializer_class = MachineSerializers.MachineSettingSerializer

    def get_object(self):
        """Lookup machine setting object, based on the URL."""
        pk = self.kwargs['pk']
        key = self.kwargs['key']
        config_type = MachineSetting.get_config_type(self.kwargs['config_type'])

        machine = get_machine(pk)

        setting_map = {d: s for s, d in machine.setting_types}
        if key.upper() not in setting_map[config_type]:
            raise NotFound(
                detail=f"Machine '{machine.name}' has no {config_type.name} setting matching '{key.upper()}'"
            )

        return MachineSetting.get_setting_object(
            key, machine_config=machine.machine_config, config_type=config_type
        )


class MachineRestart(APIView):
    """Endpoint for performing a machine restart.

    - POST: restart machine by pk
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        request=None, responses={200: MachineSerializers.MachineRestartSerializer()}
    )
    def post(self, request, pk):
        """Restart machine by pk."""
        machine = get_machine(pk)
        registry.restart_machine(machine)

        result = MachineSerializers.MachineRestartSerializer({'ok': True}).data
        return Response(result)


class MachineTypesList(APIView):
    """List API Endpoint for all discovered machine types.

    - GET: List all machine types
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(responses={200: MachineSerializers.MachineTypeSerializer(many=True)})
    def get(self, request):
        """List all machine types."""
        machine_types = list(registry.get_machine_types())
        results = MachineSerializers.MachineTypeSerializer(
            machine_types, many=True
        ).data
        return Response(results)


class MachineDriverList(APIView):
    """List API Endpoint for all discovered machine driver types."""

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        responses={200: MachineSerializers.MachineDriverSerializer(many=True)}
    )
    def get(self, request):
        """List all machine drivers."""
        machine_type = request.query_params.get('machine_type', None)

        drivers = registry.get_driver_types(machine_type)

        results = MachineSerializers.MachineDriverSerializer(
            list(drivers), many=True
        ).data
        return Response(results)


class RegistryStatusView(APIView):
    """Status API endpoint for the machine registry.

    - GET: Provide status data for the machine registry
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    serializer_class = MachineSerializers.MachineRegistryStatusSerializer

    @extend_schema(
        responses={200: MachineSerializers.MachineRegistryStatusSerializer()}
    )
    def get(self, request):
        """Provide status data for the machine registry."""
        result = MachineSerializers.MachineRegistryStatusSerializer({
            'registry_errors': [{'message': str(error)} for error in registry.errors]
        }).data

        return Response(result)


class MachineTelemetryList(ListCreateAPI):
    """API endpoint for machine telemetry data.

    - GET: Return a list of telemetry data with filtering
    - POST: Create a new telemetry data point
    """

    queryset = MachineTelemetry.objects.all()
    serializer_class = MachineSerializers.MachineTelemetrySerializer

    filter_backends = SEARCH_ORDER_FILTER

    filterset_fields = ['machine_config', 'metric_type', 'metric_name']

    ordering_fields = ['timestamp', 'metric_type', 'value', 'created']

    ordering = ['-timestamp']

    search_fields = ['metric_name']

    def get_queryset(self):
        """Filter queryset based on query parameters."""
        queryset = super().get_queryset()

        # Filter by machine_config UUID
        machine_pk = self.request.query_params.get('machine_config', None)
        if machine_pk:
            queryset = queryset.filter(machine_config__pk=machine_pk)

        # Filter by time range
        start_time = self.request.query_params.get('start_time', None)
        end_time = self.request.query_params.get('end_time', None)

        if start_time:
            queryset = queryset.filter(timestamp__gte=start_time)
        if end_time:
            queryset = queryset.filter(timestamp__lte=end_time)

        # Filter by last N hours
        last_hours = self.request.query_params.get('last_hours', None)
        if last_hours:
            try:
                hours = int(last_hours)
                threshold = timezone.now() - timedelta(hours=hours)
                queryset = queryset.filter(timestamp__gte=threshold)
            except (ValueError, TypeError):
                pass

        return queryset


class MachineTelemetryDetail(RetrieveUpdateDestroyAPI):
    """API detail endpoint for MachineTelemetry object.

    - GET: return a single telemetry data point
    - PUT: update a telemetry data point
    - PATCH: partial update a telemetry data point
    - DELETE: delete a telemetry data point
    """

    queryset = MachineTelemetry.objects.all()
    serializer_class = MachineSerializers.MachineTelemetrySerializer


class MachineTelemetryBatch(APIView):
    """API endpoint for batch telemetry data submission.

    - POST: Submit multiple telemetry data points in a single request
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        request=MachineSerializers.MachineTelemetryBatchSerializer,
        responses={201: MachineSerializers.MachineTelemetryBatchSerializer},
    )
    def post(self, request):
        """Submit batch telemetry data."""
        serializer = MachineSerializers.MachineTelemetryBatchSerializer(
            data=request.data
        )

        if serializer.is_valid():
            result = serializer.save()
            response_serializer = MachineSerializers.MachineTelemetryBatchSerializer(
                result
            )
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MachineTelemetryStatus(APIView):
    """API endpoint for machine telemetry status summary.

    - GET: Get telemetry status summary for a machine or all machines
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        responses={200: MachineSerializers.MachineTelemetryStatusSerializer(many=True)}
    )
    def get(self, request, pk=None):
        """Get telemetry status summary."""
        now = timezone.now()
        last_24h = now - timedelta(hours=24)

        if pk:
            # Get status for a specific machine
            try:
                machine_config = MachineConfig.objects.get(pk=pk)
            except MachineConfig.DoesNotExist:
                raise NotFound(detail=f"Machine '{pk}' not found")

            machines = [machine_config]
        else:
            # Get status for all active machines
            machines = MachineConfig.objects.filter(active=True)

        status_list = []
        for machine in machines:
            # Get latest telemetry for each metric type
            latest_telemetry = []
            for metric_type in MachineTelemetry.MetricType.values:
                latest = (
                    MachineTelemetry.objects.filter(
                        machine_config=machine, metric_type=metric_type
                    )
                    .order_by('-timestamp')
                    .first()
                )
                if latest:
                    latest_telemetry.append(latest)

            # Get alert counts
            active_alerts = TelemetryAlert.objects.filter(
                machine_config=machine
            ).count()

            unacknowledged_alerts = TelemetryAlert.objects.filter(
                machine_config=machine, acknowledged=False
            ).count()

            # Get last telemetry timestamp
            last_telemetry = MachineTelemetry.objects.filter(
                machine_config=machine
            ).aggregate(last_timestamp=Max('timestamp'))

            # Get telemetry count in last 24 hours
            telemetry_count_24h = MachineTelemetry.objects.filter(
                machine_config=machine, timestamp__gte=last_24h
            ).count()

            status_data = {
                'machine_config': machine.pk,
                'machine_name': machine.name,
                'latest_telemetry': latest_telemetry,
                'active_alerts_count': active_alerts,
                'unacknowledged_alerts_count': unacknowledged_alerts,
                'last_telemetry_timestamp': last_telemetry['last_timestamp'],
                'telemetry_count_24h': telemetry_count_24h,
            }
            status_list.append(status_data)

        serializer = MachineSerializers.MachineTelemetryStatusSerializer(
            status_list, many=True
        )
        return Response(serializer.data)


class TelemetryAlertList(ListCreateAPI):
    """API endpoint for telemetry alerts.

    - GET: Return a list of telemetry alerts with filtering
    - POST: Create a new telemetry alert
    """

    queryset = TelemetryAlert.objects.all()
    serializer_class = MachineSerializers.TelemetryAlertSerializer

    filter_backends = SEARCH_ORDER_FILTER

    filterset_fields = ['machine_config', 'alert_type', 'severity', 'acknowledged']

    ordering_fields = ['created', 'severity', 'alert_type']

    ordering = ['-created']

    search_fields = ['message', 'metric_name']

    def get_queryset(self):
        """Filter queryset based on query parameters."""
        queryset = super().get_queryset()

        # Filter by machine_config UUID
        machine_pk = self.request.query_params.get('machine_config', None)
        if machine_pk:
            queryset = queryset.filter(machine_config__pk=machine_pk)

        # Filter by unacknowledged only
        unacknowledged_only = self.request.query_params.get('unacknowledged_only', None)
        if unacknowledged_only and unacknowledged_only.lower() in ('true', '1', 'yes'):
            queryset = queryset.filter(acknowledged=False)

        # Filter by time range
        start_time = self.request.query_params.get('start_time', None)
        end_time = self.request.query_params.get('end_time', None)

        if start_time:
            queryset = queryset.filter(created__gte=start_time)
        if end_time:
            queryset = queryset.filter(created__lte=end_time)

        return queryset


class TelemetryAlertDetail(RetrieveUpdateDestroyAPI):
    """API detail endpoint for TelemetryAlert object.

    - GET: return a single alert
    - PUT: update an alert
    - PATCH: partial update an alert
    - DELETE: delete an alert
    """

    queryset = TelemetryAlert.objects.all()
    serializer_class = MachineSerializers.TelemetryAlertSerializer


class TelemetryAlertAcknowledge(APIView):
    """API endpoint for acknowledging telemetry alerts.

    - POST: Acknowledge an alert
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        request=MachineSerializers.TelemetryAlertAcknowledgeSerializer,
        responses={200: MachineSerializers.TelemetryAlertSerializer},
    )
    def post(self, request, pk):
        """Acknowledge a telemetry alert."""
        try:
            alert = TelemetryAlert.objects.get(pk=pk)
        except TelemetryAlert.DoesNotExist:
            raise NotFound(detail=f"Alert '{pk}' not found")

        serializer = MachineSerializers.TelemetryAlertAcknowledgeSerializer(
            data=request.data
        )

        if serializer.is_valid():
            if serializer.validated_data.get('acknowledged', True):
                alert.acknowledge(request.user)
            else:
                # Un-acknowledge the alert
                alert.acknowledged = False
                alert.acknowledged_by = None
                alert.acknowledged_at = None
                alert.save()

            response_serializer = MachineSerializers.TelemetryAlertSerializer(alert)
            return Response(response_serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TelemetryThresholdList(ListCreateAPI):
    """API endpoint for telemetry thresholds.

    - GET: Return a list of telemetry thresholds
    - POST: Create a new telemetry threshold
    """

    queryset = TelemetryThreshold.objects.all()
    serializer_class = MachineSerializers.TelemetryThresholdSerializer

    filter_backends = SEARCH_ORDER_FILTER

    filterset_fields = ['machine_config', 'metric_type', 'enabled']

    ordering_fields = ['created', 'metric_type']

    ordering = ['-created']

    search_fields = ['metric_name']


class TelemetryThresholdDetail(RetrieveUpdateDestroyAPI):
    """API detail endpoint for TelemetryThreshold object.

    - GET: return a single threshold
    - PUT: update a threshold
    - PATCH: partial update a threshold
    - DELETE: delete a threshold
    """

    queryset = TelemetryThreshold.objects.all()
    serializer_class = MachineSerializers.TelemetryThresholdSerializer


machine_api_urls = [
    # machine types
    path('types/', MachineTypesList.as_view(), name='api-machine-types'),
    # machine drivers
    path('drivers/', MachineDriverList.as_view(), name='api-machine-drivers'),
    # registry status
    path('status/', RegistryStatusView.as_view(), name='api-machine-registry-status'),
    # telemetry endpoints
    path(
        'telemetry/',
        include([
            # batch submission
            path(
                'batch/',
                MachineTelemetryBatch.as_view(),
                name='api-machine-telemetry-batch',
            ),
            # status summary for all machines
            path(
                'status/',
                MachineTelemetryStatus.as_view(),
                name='api-machine-telemetry-status',
            ),
            # detail view for a single telemetry record
            path(
                '<int:pk>/',
                MachineTelemetryDetail.as_view(),
                name='api-machine-telemetry-detail',
            ),
            # list and create telemetry
            path('', MachineTelemetryList.as_view(), name='api-machine-telemetry-list'),
        ]),
    ),
    # telemetry alerts endpoints
    path(
        'alerts/',
        include([
            # acknowledge alert
            path(
                '<int:pk>/acknowledge/',
                TelemetryAlertAcknowledge.as_view(),
                name='api-telemetry-alert-acknowledge',
            ),
            # detail view for a single alert
            path(
                '<int:pk>/',
                TelemetryAlertDetail.as_view(),
                name='api-telemetry-alert-detail',
            ),
            # list and create alerts
            path('', TelemetryAlertList.as_view(), name='api-telemetry-alert-list'),
        ]),
    ),
    # telemetry thresholds endpoints
    path(
        'thresholds/',
        include([
            # detail view for a single threshold
            path(
                '<int:pk>/',
                TelemetryThresholdDetail.as_view(),
                name='api-telemetry-threshold-detail',
            ),
            # list and create thresholds
            path(
                '',
                TelemetryThresholdList.as_view(),
                name='api-telemetry-threshold-list',
            ),
        ]),
    ),
    # detail views for a single Machine
    path(
        '<uuid:pk>/',
        include([
            # settings
            path(
                'settings/',
                include([
                    re_path(
                        r'^(?P<config_type>M|D)/(?P<key>\w+)/',
                        MachineSettingDetail.as_view(),
                        name='api-machine-settings-detail',
                    ),
                    path('', MachineSettingList.as_view(), name='api-machine-settings'),
                ]),
            ),
            # telemetry status for specific machine
            path(
                'telemetry/status/',
                MachineTelemetryStatus.as_view(),
                name='api-machine-telemetry-status-detail',
            ),
            # restart
            path('restart/', MachineRestart.as_view(), name='api-machine-restart'),
            # detail
            path('', MachineDetail.as_view(), name='api-machine-detail'),
        ]),
    ),
    # machine list and create
    path('', MachineList.as_view(), name='api-machine-list'),
]
