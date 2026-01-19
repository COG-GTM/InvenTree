"""Supply Chain Enhancement serializers for BEP MES Contract.

This module provides REST API serializers for the supply chain enhancement
features, supporting the Bureau of Engraving and Printing (BEP)
Manufacturing Execution System (MES) contract requirements.

BEP MES Contract Alignment:
- Supply Chain Team: "Integrate automation, real-time tracking, and analytics"
- Enterprise Data: "trusted data products that users can rely on"
- Data Analytics: "transform raw data into actionable insights"
"""

from decimal import Decimal
from typing import Optional

from django.utils import timezone

from rest_framework import serializers

from stock.supply_chain_models import (
    InventoryReconciliation,
    ReconciliationLineItem,
    StockAlert,
    StockAlertThreshold,
)


class StockAlertThresholdSerializer(serializers.ModelSerializer):
    """Serializer for StockAlertThreshold model.

    This serializer handles the configuration of stock alert thresholds,
    enabling BEP supply chain managers to define monitoring rules.

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "real-time tracking" configuration
    - Enterprise Data: Supports "data validation rules"
    """

    class Meta:
        model = StockAlertThreshold
        fields = [
            'id',
            'part',
            'part_name',
            'location',
            'location_name',
            'minimum_stock',
            'critical_stock',
            'reorder_point',
            'maximum_stock',
            'alert_priority',
            'alert_priority_display',
            'notification_emails',
            'webhook_url',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'part_name',
            'location_name',
            'alert_priority_display',
        ]

    part_name = serializers.CharField(source='part.name', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    alert_priority_display = serializers.CharField(
        source='get_alert_priority_display', read_only=True
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        part = attrs.get('part')
        location = attrs.get('location')
        if not part and not location:
            raise serializers.ValidationError(
                {'part': 'Either part or location must be specified'}
            )
        minimum_stock = attrs.get('minimum_stock', Decimal('0'))
        critical_stock = attrs.get('critical_stock', Decimal('0'))
        if critical_stock > minimum_stock:
            raise serializers.ValidationError({
                'critical_stock': 'Critical stock level must be less than or equal to minimum stock level'
            })
        return attrs


class StockAlertSerializer(serializers.ModelSerializer):
    """Serializer for StockAlert model.

    This serializer handles the retrieval and management of stock alerts,
    supporting the BEP MES requirement for "proactive action."

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "real-time tracking" of inventory issues
    - Data Analytics: Supports "proactive action" through alert notifications
    """

    class Meta:
        model = StockAlert
        fields = [
            'id',
            'part',
            'part_name',
            'location',
            'location_name',
            'alert_type',
            'alert_type_display',
            'priority',
            'priority_display',
            'status',
            'status_display',
            'threshold',
            'current_stock',
            'threshold_value',
            'message',
            'created_at',
            'acknowledged_by',
            'acknowledged_by_username',
            'acknowledged_at',
            'resolved_by',
            'resolved_by_username',
            'resolved_at',
            'resolution_notes',
            'notification_sent',
            'duration',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'part_name',
            'location_name',
            'alert_type_display',
            'priority_display',
            'status_display',
            'acknowledged_by_username',
            'resolved_by_username',
            'duration',
        ]

    part_name = serializers.CharField(source='part.name', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    acknowledged_by_username = serializers.CharField(
        source='acknowledged_by.username', read_only=True, allow_null=True
    )
    resolved_by_username = serializers.CharField(
        source='resolved_by.username', read_only=True, allow_null=True
    )
    duration = serializers.SerializerMethodField()

    def get_duration(self, obj) -> Optional[str]:
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
        return f"{seconds}s"


class StockAlertCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating stock alerts.

    This serializer is used when manually creating alerts or when
    the system generates alerts based on threshold violations.
    """

    class Meta:
        model = StockAlert
        fields = [
            'part',
            'location',
            'alert_type',
            'priority',
            'current_stock',
            'threshold_value',
            'message',
            'threshold',
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get('part') and not attrs.get('location'):
            raise serializers.ValidationError(
                {'part': 'Either part or location must be specified'}
            )
        return attrs


class StockAlertAcknowledgeSerializer(serializers.Serializer):
    """Serializer for acknowledging a stock alert.

    Supports the BEP MES requirement for alert management workflows.
    """

    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
        help_text='Optional notes about the acknowledgment',
    )


class StockAlertResolveSerializer(serializers.Serializer):
    """Serializer for resolving a stock alert.

    Supports the BEP MES requirement for "continuous improvement"
    through resolution documentation.
    """

    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
        help_text='Notes about how the alert was resolved',
    )


class InventoryReconciliationSerializer(serializers.ModelSerializer):
    """Serializer for InventoryReconciliation model.

    This serializer handles inventory reconciliation records,
    supporting the BEP MES requirement for "automated reconciliation."

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "automated reconciliation"
    - Enterprise Data: Supports "trusted data products"
    """

    class Meta:
        model = InventoryReconciliation
        fields = [
            'id',
            'reference',
            'location',
            'location_name',
            'status',
            'status_display',
            'scheduled_date',
            'started_at',
            'completed_at',
            'performed_by',
            'performed_by_username',
            'approved_by',
            'approved_by_username',
            'approved_at',
            'notes',
            'total_items_counted',
            'total_discrepancies',
            'total_variance_value',
            'created_at',
            'created_by',
            'accuracy_rate',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'location_name',
            'status_display',
            'performed_by_username',
            'approved_by_username',
            'total_items_counted',
            'total_discrepancies',
            'accuracy_rate',
        ]

    location_name = serializers.CharField(source='location.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    performed_by_username = serializers.CharField(
        source='performed_by.username', read_only=True, allow_null=True
    )
    approved_by_username = serializers.CharField(
        source='approved_by.username', read_only=True, allow_null=True
    )
    accuracy_rate = serializers.SerializerMethodField()

    def get_accuracy_rate(self, obj) -> Optional[float]:
        if obj.total_items_counted == 0:
            return None
        accurate_items = obj.total_items_counted - obj.total_discrepancies
        return round((accurate_items / obj.total_items_counted) * 100, 2)


class InventoryReconciliationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating inventory reconciliation records."""

    class Meta:
        model = InventoryReconciliation
        fields = [
            'reference',
            'location',
            'scheduled_date',
            'notes',
        ]


class ReconciliationLineItemSerializer(serializers.ModelSerializer):
    """Serializer for ReconciliationLineItem model.

    This serializer handles individual line items in a reconciliation,
    supporting the BEP MES requirement for "inventory accuracy."

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "inventory accuracy" tracking
    - Enterprise Data: Supports "discrepancy reports"
    """

    class Meta:
        model = ReconciliationLineItem
        fields = [
            'id',
            'reconciliation',
            'stock_item',
            'part',
            'part_name',
            'system_quantity',
            'physical_quantity',
            'variance',
            'variance_percentage',
            'discrepancy_type',
            'discrepancy_type_display',
            'notes',
            'counted_by',
            'counted_by_username',
            'counted_at',
        ]
        read_only_fields = [
            'id',
            'variance',
            'variance_percentage',
            'part_name',
            'discrepancy_type_display',
            'counted_by_username',
            'counted_at',
        ]

    part_name = serializers.CharField(source='part.name', read_only=True)
    discrepancy_type_display = serializers.CharField(
        source='get_discrepancy_type_display', read_only=True, allow_null=True
    )
    counted_by_username = serializers.CharField(
        source='counted_by.username', read_only=True, allow_null=True
    )


class ReconciliationLineItemCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating reconciliation line items."""

    class Meta:
        model = ReconciliationLineItem
        fields = [
            'reconciliation',
            'stock_item',
            'part',
            'system_quantity',
            'physical_quantity',
            'notes',
        ]


class ReconciliationReportSerializer(serializers.Serializer):
    """Serializer for reconciliation report generation.

    This serializer supports the BEP MES requirement for generating
    "discrepancy reports comparing physical vs. system counts."

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "discrepancy reports"
    - Enterprise Data: Supports Treasury-compliant export formats
    """

    reconciliation_id = serializers.IntegerField()
    reference = serializers.CharField()
    location_name = serializers.CharField()
    status = serializers.CharField()
    performed_by = serializers.CharField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    total_items_counted = serializers.IntegerField()
    total_discrepancies = serializers.IntegerField()
    accuracy_rate = serializers.FloatField(allow_null=True)
    total_variance_value = serializers.DecimalField(max_digits=19, decimal_places=4)
    line_items = ReconciliationLineItemSerializer(many=True)


class StockLevelSummarySerializer(serializers.Serializer):
    """Serializer for stock level summary data.

    This serializer provides aggregated stock level information
    for dashboard display and analytics.

    BEP MES Contract Alignment:
    - Data Analytics: Supports "interactive dashboards"
    - Supply Chain Team: Enables "data-driven performance monitoring"
    """

    part_id = serializers.IntegerField()
    part_name = serializers.CharField()
    part_ipn = serializers.CharField(allow_null=True)
    total_stock = serializers.DecimalField(max_digits=15, decimal_places=5)
    available_stock = serializers.DecimalField(max_digits=15, decimal_places=5)
    allocated_stock = serializers.DecimalField(max_digits=15, decimal_places=5)
    minimum_stock = serializers.DecimalField(max_digits=15, decimal_places=5, allow_null=True)
    stock_status = serializers.CharField()
    locations_count = serializers.IntegerField()
    last_stocktake = serializers.DateTimeField(allow_null=True)
    active_alerts = serializers.IntegerField()


class SupplyChainDashboardSerializer(serializers.Serializer):
    """Serializer for supply chain dashboard data.

    This serializer provides comprehensive supply chain metrics
    for the BEP MES dashboard requirements.

    BEP MES Contract Alignment:
    - Data Analytics: "interactive dashboards" and "real-time KPIs"
    - Supply Chain Team: "data-driven performance monitoring"
    """

    total_parts_monitored = serializers.IntegerField()
    total_active_alerts = serializers.IntegerField()
    critical_alerts = serializers.IntegerField()
    high_priority_alerts = serializers.IntegerField()
    low_stock_items = serializers.IntegerField()
    out_of_stock_items = serializers.IntegerField()
    pending_reconciliations = serializers.IntegerField()
    completed_reconciliations_this_month = serializers.IntegerField()
    average_accuracy_rate = serializers.FloatField(allow_null=True)
    total_variance_value_this_month = serializers.DecimalField(
        max_digits=19, decimal_places=4
    )
    alerts_by_type = serializers.DictField(child=serializers.IntegerField())
    alerts_by_priority = serializers.DictField(child=serializers.IntegerField())
