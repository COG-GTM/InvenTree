"""Supply Chain Enhancement API endpoints for BEP MES Contract.

This module provides REST API endpoints for the supply chain enhancement
features, supporting the Bureau of Engraving and Printing (BEP)
Manufacturing Execution System (MES) contract requirements.

BEP MES Contract Alignment:
- Supply Chain Team Focus Area: "Integrate automation, real-time tracking,
  and analytics into supply chain systems to improve transparency, efficiency,
  and risk management while enabling data-driven performance monitoring"
- Key Outcome: "A cross-functional Agile team improving inventory accuracy
  through real-time tracking and automated reconciliation"

API Endpoints:
- Stock Alert Thresholds: Configure monitoring rules for inventory levels
- Stock Alerts: Real-time alerts for supply chain issues
- Inventory Reconciliation: Automated stocktaking and discrepancy tracking
- Supply Chain Dashboard: Aggregated metrics for decision-making
"""

from decimal import Decimal

from django.db.models import Sum
from django.urls import path
from django.utils import timezone

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

import InvenTree.permissions
from InvenTree.filters import SEARCH_ORDER_FILTER
from InvenTree.mixins import ListCreateAPI, RetrieveUpdateDestroyAPI
from stock.supply_chain_models import (
    AlertPriority,
    AlertStatus,
    AlertType,
    InventoryReconciliation,
    ReconciliationLineItem,
    ReconciliationStatus,
    StockAlert,
    StockAlertThreshold,
)
from stock.supply_chain_serializers import (
    InventoryReconciliationCreateSerializer,
    InventoryReconciliationSerializer,
    ReconciliationLineItemCreateSerializer,
    ReconciliationLineItemSerializer,
    ReconciliationReportSerializer,
    StockAlertAcknowledgeSerializer,
    StockAlertCreateSerializer,
    StockAlertResolveSerializer,
    StockAlertSerializer,
    StockAlertThresholdSerializer,
    SupplyChainDashboardSerializer,
)


class StockAlertThresholdList(ListCreateAPI):
    """API endpoint for listing and creating stock alert thresholds.

    This endpoint supports the BEP MES requirement for configuring
    "real-time tracking" rules for inventory monitoring.

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables configuration of monitoring rules
    - Enterprise Data: Supports "data validation rules"

    GET: List all stock alert thresholds with optional filtering
    POST: Create a new stock alert threshold
    """

    queryset = StockAlertThreshold.objects.all()
    serializer_class = StockAlertThresholdSerializer
    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]
    filter_backends = SEARCH_ORDER_FILTER
    ordering_fields = ['created_at', 'minimum_stock', 'critical_stock', 'is_active']
    ordering = ['-created_at']
    search_fields = ['part__name', 'location__name']

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        part = params.get('part')
        if part:
            queryset = queryset.filter(part__pk=part)
        location = params.get('location')
        if location:
            queryset = queryset.filter(location__pk=location)
        is_active = params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class StockAlertThresholdDetail(RetrieveUpdateDestroyAPI):
    """API endpoint for retrieving, updating, and deleting a stock alert threshold.

    GET: Retrieve a specific threshold
    PUT/PATCH: Update a threshold
    DELETE: Delete a threshold
    """

    queryset = StockAlertThreshold.objects.all()
    serializer_class = StockAlertThresholdSerializer
    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]


class StockAlertList(ListCreateAPI):
    """API endpoint for listing and creating stock alerts.

    This endpoint supports the BEP MES requirement for "real-time tracking"
    of inventory issues and "proactive action" through notifications.

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "real-time tracking" of inventory issues
    - Data Analytics: Supports "proactive action" through alert notifications

    GET: List all stock alerts with optional filtering
    POST: Create a new stock alert (typically system-generated)
    """

    queryset = StockAlert.objects.all()
    serializer_class = StockAlertSerializer
    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]
    filter_backends = SEARCH_ORDER_FILTER
    ordering_fields = ['created_at', 'priority', 'status', 'alert_type']
    ordering = ['-created_at']
    search_fields = ['part__name', 'location__name', 'message']

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        part = params.get('part')
        if part:
            queryset = queryset.filter(part__pk=part)
        location = params.get('location')
        if location:
            queryset = queryset.filter(location__pk=location)
        alert_type = params.get('alert_type')
        if alert_type:
            queryset = queryset.filter(alert_type=alert_type)
        priority = params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        status_filter = params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        active_only = params.get('active_only')
        if active_only and active_only.lower() == 'true':
            queryset = queryset.filter(status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED])
        return queryset

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return StockAlertCreateSerializer
        return StockAlertSerializer


class StockAlertDetail(RetrieveUpdateDestroyAPI):
    """API endpoint for retrieving, updating, and deleting a stock alert.

    GET: Retrieve a specific alert
    PUT/PATCH: Update an alert
    DELETE: Delete an alert
    """

    queryset = StockAlert.objects.all()
    serializer_class = StockAlertSerializer
    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]


class StockAlertAcknowledge(APIView):
    """API endpoint for acknowledging a stock alert.

    This endpoint supports the BEP MES requirement for alert management
    workflows, enabling operators to indicate awareness of issues.

    POST: Acknowledge an alert
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        request=StockAlertAcknowledgeSerializer,
        responses={200: StockAlertSerializer}
    )
    def post(self, request, pk):
        try:
            alert = StockAlert.objects.get(pk=pk)
        except StockAlert.DoesNotExist:
            raise NotFound('Stock alert not found')
        if alert.status not in [AlertStatus.ACTIVE]:
            raise ValidationError({'status': 'Alert cannot be acknowledged in current state'})
        serializer = StockAlertAcknowledgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get('notes', '')
        alert.acknowledge(request.user, notes)
        return Response(StockAlertSerializer(alert).data)


class StockAlertResolve(APIView):
    """API endpoint for resolving a stock alert.

    This endpoint supports the BEP MES requirement for "continuous improvement"
    through resolution documentation.

    POST: Resolve an alert
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        request=StockAlertResolveSerializer,
        responses={200: StockAlertSerializer}
    )
    def post(self, request, pk):
        try:
            alert = StockAlert.objects.get(pk=pk)
        except StockAlert.DoesNotExist:
            raise NotFound('Stock alert not found')
        if alert.status == AlertStatus.RESOLVED:
            raise ValidationError({'status': 'Alert is already resolved'})
        serializer = StockAlertResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get('notes', '')
        alert.resolve(request.user, notes)
        return Response(StockAlertSerializer(alert).data)


class InventoryReconciliationList(ListCreateAPI):
    """API endpoint for listing and creating inventory reconciliations.

    This endpoint supports the BEP MES requirement for "automated reconciliation"
    of inventory through systematic stocktaking.

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "automated reconciliation"
    - Enterprise Data: Supports "trusted data products"

    GET: List all reconciliations with optional filtering
    POST: Create a new reconciliation
    """

    queryset = InventoryReconciliation.objects.all()
    serializer_class = InventoryReconciliationSerializer
    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]
    filter_backends = SEARCH_ORDER_FILTER
    ordering_fields = ['created_at', 'scheduled_date', 'status', 'total_discrepancies']
    ordering = ['-created_at']
    search_fields = ['reference', 'location__name', 'notes']

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        location = params.get('location')
        if location:
            queryset = queryset.filter(location__pk=location)
        status_filter = params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        performed_by = params.get('performed_by')
        if performed_by:
            queryset = queryset.filter(performed_by__pk=performed_by)
        return queryset

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return InventoryReconciliationCreateSerializer
        return InventoryReconciliationSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class InventoryReconciliationDetail(RetrieveUpdateDestroyAPI):
    """API endpoint for retrieving, updating, and deleting a reconciliation.

    GET: Retrieve a specific reconciliation
    PUT/PATCH: Update a reconciliation
    DELETE: Delete a reconciliation
    """

    queryset = InventoryReconciliation.objects.all()
    serializer_class = InventoryReconciliationSerializer
    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]


class InventoryReconciliationStart(APIView):
    """API endpoint for starting an inventory reconciliation.

    POST: Start a reconciliation (changes status to IN_PROGRESS)
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(responses={200: InventoryReconciliationSerializer})
    def post(self, request, pk):
        try:
            reconciliation = InventoryReconciliation.objects.get(pk=pk)
        except InventoryReconciliation.DoesNotExist:
            raise NotFound('Reconciliation not found')
        if reconciliation.status != ReconciliationStatus.PENDING:
            raise ValidationError({'status': 'Reconciliation cannot be started in current state'})
        reconciliation.start(request.user)
        return Response(InventoryReconciliationSerializer(reconciliation).data)


class InventoryReconciliationComplete(APIView):
    """API endpoint for completing an inventory reconciliation.

    POST: Complete a reconciliation (changes status to COMPLETED)
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(responses={200: InventoryReconciliationSerializer})
    def post(self, request, pk):
        try:
            reconciliation = InventoryReconciliation.objects.get(pk=pk)
        except InventoryReconciliation.DoesNotExist:
            raise NotFound('Reconciliation not found')
        if reconciliation.status != ReconciliationStatus.IN_PROGRESS:
            raise ValidationError({'status': 'Reconciliation cannot be completed in current state'})
        reconciliation.complete()
        return Response(InventoryReconciliationSerializer(reconciliation).data)


class InventoryReconciliationApprove(APIView):
    """API endpoint for approving an inventory reconciliation.

    POST: Approve a reconciliation (changes status to APPROVED)
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(responses={200: InventoryReconciliationSerializer})
    def post(self, request, pk):
        try:
            reconciliation = InventoryReconciliation.objects.get(pk=pk)
        except InventoryReconciliation.DoesNotExist:
            raise NotFound('Reconciliation not found')
        if reconciliation.status != ReconciliationStatus.COMPLETED:
            raise ValidationError({'status': 'Reconciliation cannot be approved in current state'})
        reconciliation.approve(request.user)
        return Response(InventoryReconciliationSerializer(reconciliation).data)


class ReconciliationLineItemList(ListCreateAPI):
    """API endpoint for listing and creating reconciliation line items.

    This endpoint supports the BEP MES requirement for "inventory accuracy"
    by tracking individual item counts.

    GET: List all line items for a reconciliation
    POST: Create a new line item
    """

    serializer_class = ReconciliationLineItemSerializer
    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    def get_queryset(self):
        reconciliation_pk = self.kwargs.get('reconciliation_pk')
        return ReconciliationLineItem.objects.filter(reconciliation__pk=reconciliation_pk)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ReconciliationLineItemCreateSerializer
        return ReconciliationLineItemSerializer

    def perform_create(self, serializer):
        reconciliation_pk = self.kwargs.get('reconciliation_pk')
        try:
            reconciliation = InventoryReconciliation.objects.get(pk=reconciliation_pk)
        except InventoryReconciliation.DoesNotExist:
            raise NotFound('Reconciliation not found')
        serializer.save(reconciliation=reconciliation, counted_by=self.request.user)


class ReconciliationLineItemDetail(RetrieveUpdateDestroyAPI):
    """API endpoint for retrieving, updating, and deleting a line item.

    GET: Retrieve a specific line item
    PUT/PATCH: Update a line item
    DELETE: Delete a line item
    """

    queryset = ReconciliationLineItem.objects.all()
    serializer_class = ReconciliationLineItemSerializer
    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]


class ReconciliationReportView(APIView):
    """API endpoint for generating reconciliation reports.

    This endpoint supports the BEP MES requirement for generating
    "discrepancy reports comparing physical vs. system counts."

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "discrepancy reports"
    - Enterprise Data: Supports Treasury-compliant export formats

    GET: Generate a reconciliation report
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='format',
                description='Export format (json, csv, xml)',
                required=False,
                type=str,
            ),
        ],
        responses={200: ReconciliationReportSerializer}
    )
    def get(self, request, pk):
        try:
            reconciliation = InventoryReconciliation.objects.get(pk=pk)
        except InventoryReconciliation.DoesNotExist:
            raise NotFound('Reconciliation not found')
        line_items = reconciliation.line_items.all()
        accuracy_rate = None
        if reconciliation.total_items_counted > 0:
            accurate_items = reconciliation.total_items_counted - reconciliation.total_discrepancies
            accuracy_rate = round((accurate_items / reconciliation.total_items_counted) * 100, 2)
        report_data = {
            'reconciliation_id': reconciliation.pk,
            'reference': reconciliation.reference,
            'location_name': reconciliation.location.name,
            'status': reconciliation.get_status_display(),
            'performed_by': reconciliation.performed_by.username if reconciliation.performed_by else None,
            'started_at': reconciliation.started_at,
            'completed_at': reconciliation.completed_at,
            'total_items_counted': reconciliation.total_items_counted,
            'total_discrepancies': reconciliation.total_discrepancies,
            'accuracy_rate': accuracy_rate,
            'total_variance_value': reconciliation.total_variance_value,
            'line_items': ReconciliationLineItemSerializer(line_items, many=True).data,
        }
        return Response(report_data)


class SupplyChainDashboardView(APIView):
    """API endpoint for supply chain dashboard data.

    This endpoint provides comprehensive supply chain metrics for the
    BEP MES dashboard requirements.

    BEP MES Contract Alignment:
    - Data Analytics: "interactive dashboards" and "real-time KPIs"
    - Supply Chain Team: "data-driven performance monitoring"

    GET: Retrieve dashboard metrics
    """

    permission_classes = [InvenTree.permissions.IsAuthenticatedOrReadScope]

    @extend_schema(responses={200: SupplyChainDashboardSerializer})
    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total_parts_monitored = StockAlertThreshold.objects.filter(is_active=True).count()
        active_alerts = StockAlert.objects.filter(
            status__in=[AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]
        )
        total_active_alerts = active_alerts.count()
        critical_alerts = active_alerts.filter(priority=AlertPriority.CRITICAL).count()
        high_priority_alerts = active_alerts.filter(priority=AlertPriority.HIGH).count()
        low_stock_items = active_alerts.filter(alert_type=AlertType.LOW_STOCK).count()
        out_of_stock_items = active_alerts.filter(alert_type=AlertType.OUT_OF_STOCK).count()
        pending_reconciliations = InventoryReconciliation.objects.filter(
            status__in=[ReconciliationStatus.PENDING, ReconciliationStatus.IN_PROGRESS]
        ).count()
        completed_reconciliations = InventoryReconciliation.objects.filter(
            status__in=[ReconciliationStatus.COMPLETED, ReconciliationStatus.APPROVED],
            completed_at__gte=month_start
        )
        completed_reconciliations_this_month = completed_reconciliations.count()
        avg_accuracy = None
        if completed_reconciliations_this_month > 0:
            total_items = completed_reconciliations.aggregate(
                total=Sum('total_items_counted'),
                discrepancies=Sum('total_discrepancies')
            )
            if total_items['total'] and total_items['total'] > 0:
                accurate = total_items['total'] - (total_items['discrepancies'] or 0)
                avg_accuracy = round((accurate / total_items['total']) * 100, 2)
        total_variance = completed_reconciliations.aggregate(
            total=Sum('total_variance_value')
        )['total'] or Decimal('0')
        alerts_by_type = {}
        for alert_type in AlertType.choices:
            count = active_alerts.filter(alert_type=alert_type[0]).count()
            if count > 0:
                alerts_by_type[alert_type[0]] = count
        alerts_by_priority = {}
        for priority in AlertPriority.choices:
            count = active_alerts.filter(priority=priority[0]).count()
            if count > 0:
                alerts_by_priority[priority[0]] = count
        dashboard_data = {
            'total_parts_monitored': total_parts_monitored,
            'total_active_alerts': total_active_alerts,
            'critical_alerts': critical_alerts,
            'high_priority_alerts': high_priority_alerts,
            'low_stock_items': low_stock_items,
            'out_of_stock_items': out_of_stock_items,
            'pending_reconciliations': pending_reconciliations,
            'completed_reconciliations_this_month': completed_reconciliations_this_month,
            'average_accuracy_rate': avg_accuracy,
            'total_variance_value_this_month': total_variance,
            'alerts_by_type': alerts_by_type,
            'alerts_by_priority': alerts_by_priority,
        }
        return Response(dashboard_data)


supply_chain_api_urls = [
    path(
        'supply-chain/thresholds/',
        StockAlertThresholdList.as_view(),
        name='api-stock-alert-threshold-list'
    ),
    path(
        'supply-chain/thresholds/<int:pk>/',
        StockAlertThresholdDetail.as_view(),
        name='api-stock-alert-threshold-detail'
    ),
    path(
        'supply-chain/alerts/',
        StockAlertList.as_view(),
        name='api-stock-alert-list'
    ),
    path(
        'supply-chain/alerts/<int:pk>/',
        StockAlertDetail.as_view(),
        name='api-stock-alert-detail'
    ),
    path(
        'supply-chain/alerts/<int:pk>/acknowledge/',
        StockAlertAcknowledge.as_view(),
        name='api-stock-alert-acknowledge'
    ),
    path(
        'supply-chain/alerts/<int:pk>/resolve/',
        StockAlertResolve.as_view(),
        name='api-stock-alert-resolve'
    ),
    path(
        'supply-chain/reconciliations/',
        InventoryReconciliationList.as_view(),
        name='api-inventory-reconciliation-list'
    ),
    path(
        'supply-chain/reconciliations/<int:pk>/',
        InventoryReconciliationDetail.as_view(),
        name='api-inventory-reconciliation-detail'
    ),
    path(
        'supply-chain/reconciliations/<int:pk>/start/',
        InventoryReconciliationStart.as_view(),
        name='api-inventory-reconciliation-start'
    ),
    path(
        'supply-chain/reconciliations/<int:pk>/complete/',
        InventoryReconciliationComplete.as_view(),
        name='api-inventory-reconciliation-complete'
    ),
    path(
        'supply-chain/reconciliations/<int:pk>/approve/',
        InventoryReconciliationApprove.as_view(),
        name='api-inventory-reconciliation-approve'
    ),
    path(
        'supply-chain/reconciliations/<int:pk>/report/',
        ReconciliationReportView.as_view(),
        name='api-reconciliation-report'
    ),
    path(
        'supply-chain/reconciliations/<int:reconciliation_pk>/items/',
        ReconciliationLineItemList.as_view(),
        name='api-reconciliation-line-item-list'
    ),
    path(
        'supply-chain/reconciliations/items/<int:pk>/',
        ReconciliationLineItemDetail.as_view(),
        name='api-reconciliation-line-item-detail'
    ),
    path(
        'supply-chain/dashboard/',
        SupplyChainDashboardView.as_view(),
        name='api-supply-chain-dashboard'
    ),
]
