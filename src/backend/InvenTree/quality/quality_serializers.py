"""Quality Management System Serializers for BEP MES Contract.

This module implements REST API serializers for the quality management system
to support the Bureau of Engraving and Printing (BEP) Manufacturing Execution
System (MES) contract requirements.

BEP MES Contract Alignment:
---------------------------
Focus Area: Quality Management
Goal: ISO 9001 compliance
Key Outcomes:
- "Implement advanced IT solutions to modernize quality management"
- "Developing Quality dashboards with real-time KPIs"
- "Export quality reports for ISO audits"

These serializers enable:
1. RESTful CRUD operations for quality inspections, defects, and holds
2. Dashboard data aggregation for real-time KPI display
3. Report generation for ISO 9001 audit compliance
4. Comprehensive validation for data integrity
"""

from django.utils import timezone

from rest_framework import serializers

from part.models import Part
from quality.quality_models import (
    HoldStatus,
    QualityChecklistResult,
    QualityChecklistTemplate,
    QualityDefect,
    QualityHold,
    QualityInspection,
    QualityMetric,
)


class QualityInspectionSerializer(serializers.ModelSerializer):
    """Serializer for QualityInspection model.

    BEP MES Alignment: Provides comprehensive inspection data serialization
    for tracking quality inspections with full traceability as required
    for ISO 9001 compliance.
    """

    part_name = serializers.CharField(source='part.name', read_only=True)
    stock_item_serial = serializers.CharField(
        source='stock_item.serial', read_only=True, allow_null=True
    )
    inspector_name = serializers.CharField(
        source='inspector.name', read_only=True, allow_null=True
    )
    pass_rate = serializers.FloatField(read_only=True)
    is_passed = serializers.BooleanField(read_only=True)
    defect_count = serializers.SerializerMethodField()

    class Meta:
        model = QualityInspection
        fields = [
            'pk',
            'inspection_number',
            'inspection_type',
            'part',
            'part_name',
            'stock_item',
            'stock_item_serial',
            'build_order',
            'location',
            'inspection_date',
            'inspector',
            'inspector_name',
            'result',
            'quantity_inspected',
            'quantity_passed',
            'quantity_failed',
            'sampling_plan',
            'specification_reference',
            'notes',
            'attachments',
            'pass_rate',
            'is_passed',
            'defect_count',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['pk', 'created_at', 'updated_at']

    def get_defect_count(self, obj):
        """Get count of defects associated with this inspection."""
        return obj.defects.count()

    def validate(self, data):
        """Validate inspection data."""
        quantity_inspected = data.get('quantity_inspected', 0)
        quantity_passed = data.get('quantity_passed', 0)
        quantity_failed = data.get('quantity_failed', 0)

        if quantity_passed + quantity_failed > quantity_inspected:
            raise serializers.ValidationError(
                "Sum of passed and failed quantities cannot exceed total inspected quantity"
            )

        return data


class QualityInspectionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating QualityInspection records.

    BEP MES Alignment: Enables creation of inspection records with
    automatic inspection number generation and validation.
    """

    class Meta:
        model = QualityInspection
        fields = [
            'inspection_type',
            'part',
            'stock_item',
            'build_order',
            'location',
            'inspection_date',
            'inspector',
            'result',
            'quantity_inspected',
            'quantity_passed',
            'quantity_failed',
            'sampling_plan',
            'specification_reference',
            'notes',
            'attachments',
        ]

    def create(self, validated_data):
        """Create inspection with auto-generated inspection number."""
        import uuid
        validated_data['inspection_number'] = f"INS-{uuid.uuid4().hex[:8].upper()}"
        validated_data['created_by'] = self.context.get('request').user.pk if self.context.get('request') else None
        return super().create(validated_data)


class QualityDefectSerializer(serializers.ModelSerializer):
    """Serializer for QualityDefect model.

    BEP MES Alignment: Provides comprehensive defect data serialization
    with root cause analysis fields for continuous improvement tracking.
    """

    part_name = serializers.CharField(source='part.name', read_only=True)
    inspection_number = serializers.CharField(
        source='inspection.inspection_number', read_only=True
    )
    detected_by_name = serializers.CharField(
        source='detected_by.name', read_only=True, allow_null=True
    )
    resolved_by_name = serializers.CharField(
        source='resolved_by.name', read_only=True, allow_null=True
    )
    category_display = serializers.CharField(
        source='get_category_display', read_only=True
    )
    severity_display = serializers.CharField(
        source='get_severity_display', read_only=True
    )
    root_cause_category_display = serializers.CharField(
        source='get_root_cause_category_display', read_only=True
    )

    class Meta:
        model = QualityDefect
        fields = [
            'pk',
            'defect_number',
            'inspection',
            'inspection_number',
            'part',
            'part_name',
            'stock_item',
            'category',
            'category_display',
            'severity',
            'severity_display',
            'description',
            'detected_date',
            'detected_by',
            'detected_by_name',
            'quantity_affected',
            'root_cause_category',
            'root_cause_category_display',
            'root_cause_description',
            'corrective_action',
            'preventive_action',
            'disposition',
            'is_resolved',
            'resolved_date',
            'resolved_by',
            'resolved_by_name',
            'attachments',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['pk', 'created_at', 'updated_at']


class QualityDefectCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating QualityDefect records.

    BEP MES Alignment: Enables creation of defect records with
    automatic defect number generation.
    """

    class Meta:
        model = QualityDefect
        fields = [
            'inspection',
            'part',
            'stock_item',
            'category',
            'severity',
            'description',
            'detected_date',
            'detected_by',
            'quantity_affected',
            'root_cause_category',
            'root_cause_description',
            'corrective_action',
            'preventive_action',
            'disposition',
        ]

    def create(self, validated_data):
        """Create defect with auto-generated defect number."""
        import uuid
        validated_data['defect_number'] = f"DEF-{uuid.uuid4().hex[:8].upper()}"
        return super().create(validated_data)


class QualityDefectResolveSerializer(serializers.Serializer):
    """Serializer for resolving a defect.

    BEP MES Alignment: Enables defect resolution workflow with
    corrective action documentation.
    """

    corrective_action = serializers.CharField(required=False, allow_blank=True)
    preventive_action = serializers.CharField(required=False, allow_blank=True)
    disposition = serializers.CharField(required=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class QualityHoldSerializer(serializers.ModelSerializer):
    """Serializer for QualityHold model.

    BEP MES Alignment: Provides comprehensive hold data serialization
    for quality hold/release workflow management.
    """

    part_name = serializers.CharField(source='part.name', read_only=True)
    status_display = serializers.CharField(
        source='get_status_display', read_only=True
    )
    initiated_by_name = serializers.CharField(
        source='initiated_by.name', read_only=True, allow_null=True
    )
    reviewed_by_name = serializers.CharField(
        source='reviewed_by.name', read_only=True, allow_null=True
    )
    released_by_name = serializers.CharField(
        source='released_by.name', read_only=True, allow_null=True
    )
    is_active = serializers.BooleanField(read_only=True)
    is_released = serializers.BooleanField(read_only=True)
    hold_duration_hours = serializers.SerializerMethodField()

    class Meta:
        model = QualityHold
        fields = [
            'pk',
            'hold_number',
            'status',
            'status_display',
            'part',
            'part_name',
            'stock_item',
            'location',
            'defect',
            'inspection',
            'hold_date',
            'hold_reason',
            'quantity_held',
            'initiated_by',
            'initiated_by_name',
            'review_notes',
            'reviewed_by',
            'reviewed_by_name',
            'reviewed_date',
            'disposition_decision',
            'release_conditions',
            'released_date',
            'released_by',
            'released_by_name',
            'is_active',
            'is_released',
            'hold_duration_hours',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['pk', 'created_at', 'updated_at']

    def get_hold_duration_hours(self, obj):
        """Calculate hold duration in hours."""
        if obj.released_date:
            delta = obj.released_date - obj.hold_date
        else:
            delta = timezone.now() - obj.hold_date
        return round(delta.total_seconds() / 3600, 2)


class QualityHoldCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating QualityHold records.

    BEP MES Alignment: Enables creation of quality holds with
    automatic hold number generation.
    """

    class Meta:
        model = QualityHold
        fields = [
            'part',
            'stock_item',
            'location',
            'defect',
            'inspection',
            'hold_date',
            'hold_reason',
            'quantity_held',
            'initiated_by',
        ]

    def create(self, validated_data):
        """Create hold with auto-generated hold number."""
        import uuid
        validated_data['hold_number'] = f"HOLD-{uuid.uuid4().hex[:8].upper()}"
        validated_data['status'] = HoldStatus.ACTIVE
        return super().create(validated_data)


class QualityHoldReviewSerializer(serializers.Serializer):
    """Serializer for reviewing a quality hold.

    BEP MES Alignment: Enables hold review workflow with
    disposition decision documentation.
    """

    review_notes = serializers.CharField(required=True)
    disposition_decision = serializers.CharField(required=True)
    status = serializers.ChoiceField(
        choices=[
            (HoldStatus.PENDING_REVIEW, 'Pending Review'),
            (HoldStatus.APPROVED_RELEASE, 'Approved for Release'),
            (HoldStatus.REJECTED, 'Rejected'),
            (HoldStatus.CONDITIONALLY_RELEASED, 'Conditionally Released'),
        ],
        required=True
    )
    release_conditions = serializers.CharField(required=False, allow_blank=True)


class QualityHoldReleaseSerializer(serializers.Serializer):
    """Serializer for releasing a quality hold.

    BEP MES Alignment: Enables hold release workflow with
    release authorization documentation.
    """

    release_notes = serializers.CharField(required=False, allow_blank=True)


class QualityMetricSerializer(serializers.ModelSerializer):
    """Serializer for QualityMetric model.

    BEP MES Alignment: Provides quality metric data serialization
    for dashboard display and trend analysis.
    """

    part_name = serializers.CharField(
        source='part.name', read_only=True, allow_null=True
    )
    metric_type_display = serializers.CharField(
        source='get_metric_type_display', read_only=True
    )
    is_on_target = serializers.BooleanField(read_only=True)
    variance_from_target = serializers.FloatField(read_only=True)

    class Meta:
        model = QualityMetric
        fields = [
            'pk',
            'metric_type',
            'metric_type_display',
            'part',
            'part_name',
            'period_start',
            'period_end',
            'value',
            'target_value',
            'unit',
            'sample_size',
            'notes',
            'is_on_target',
            'variance_from_target',
            'calculated_at',
        ]
        read_only_fields = ['pk', 'calculated_at']


class QualityChecklistTemplateSerializer(serializers.ModelSerializer):
    """Serializer for QualityChecklistTemplate model.

    BEP MES Alignment: Provides checklist template serialization
    for standardized inspection procedures.
    """

    part_name = serializers.CharField(
        source='part.name', read_only=True, allow_null=True
    )
    inspection_type_display = serializers.CharField(
        source='get_inspection_type_display', read_only=True
    )
    created_by_name = serializers.CharField(
        source='created_by.name', read_only=True, allow_null=True
    )
    approved_by_name = serializers.CharField(
        source='approved_by.name', read_only=True, allow_null=True
    )
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = QualityChecklistTemplate
        fields = [
            'pk',
            'name',
            'description',
            'inspection_type',
            'inspection_type_display',
            'part',
            'part_name',
            'checklist_items',
            'revision',
            'is_active',
            'created_by',
            'created_by_name',
            'approved_by',
            'approved_by_name',
            'approved_date',
            'item_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['pk', 'created_at', 'updated_at']

    def get_item_count(self, obj):
        """Get count of checklist items."""
        if isinstance(obj.checklist_items, list):
            return len(obj.checklist_items)
        return 0


class QualityChecklistResultSerializer(serializers.ModelSerializer):
    """Serializer for QualityChecklistResult model.

    BEP MES Alignment: Provides checklist result serialization
    for completed inspection records.
    """

    inspection_number = serializers.CharField(
        source='inspection.inspection_number', read_only=True
    )
    template_name = serializers.CharField(
        source='template.name', read_only=True, allow_null=True
    )
    completed_by_name = serializers.CharField(
        source='completed_by.name', read_only=True, allow_null=True
    )
    overall_result_display = serializers.CharField(
        source='get_overall_result_display', read_only=True
    )
    passed_items = serializers.SerializerMethodField()
    failed_items = serializers.SerializerMethodField()

    class Meta:
        model = QualityChecklistResult
        fields = [
            'pk',
            'inspection',
            'inspection_number',
            'template',
            'template_name',
            'item_results',
            'overall_result',
            'overall_result_display',
            'completed_by',
            'completed_by_name',
            'completed_at',
            'notes',
            'passed_items',
            'failed_items',
            'created_at',
        ]
        read_only_fields = ['pk', 'created_at']

    def get_passed_items(self, obj):
        """Count passed checklist items."""
        if isinstance(obj.item_results, list):
            return sum(1 for item in obj.item_results if item.get('result') == 'PASS')
        return 0

    def get_failed_items(self, obj):
        """Count failed checklist items."""
        if isinstance(obj.item_results, list):
            return sum(1 for item in obj.item_results if item.get('result') == 'FAIL')
        return 0


class QualityDashboardSerializer(serializers.Serializer):
    """Serializer for Quality Dashboard data aggregation.

    BEP MES Contract Alignment:
    - "Developing Quality dashboards with real-time KPIs"
    - "Display defect rates, first-pass yield, and quality trends"

    This serializer aggregates quality data for dashboard display,
    providing real-time visibility into quality performance metrics.
    """

    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()

    total_inspections = serializers.IntegerField()
    passed_inspections = serializers.IntegerField()
    failed_inspections = serializers.IntegerField()
    inspection_pass_rate = serializers.FloatField()

    total_defects = serializers.IntegerField()
    critical_defects = serializers.IntegerField()
    major_defects = serializers.IntegerField()
    minor_defects = serializers.IntegerField()
    defect_rate = serializers.FloatField()

    first_pass_yield = serializers.FloatField()

    active_holds = serializers.IntegerField()
    pending_review_holds = serializers.IntegerField()
    average_hold_duration_hours = serializers.FloatField()

    defects_by_category = serializers.DictField()
    defects_by_root_cause = serializers.DictField()
    inspections_by_type = serializers.DictField()

    trend_data = serializers.ListField()


class QualityReportSerializer(serializers.Serializer):
    """Serializer for Quality Report generation.

    BEP MES Contract Alignment:
    - "Export quality reports for ISO audits"
    - "ISO 9001 compliance, digitalized processes"

    This serializer structures quality data for ISO 9001 audit reports,
    including all required traceability and compliance information.
    """

    report_type = serializers.ChoiceField(
        choices=[
            ('INSPECTION_SUMMARY', 'Inspection Summary Report'),
            ('DEFECT_ANALYSIS', 'Defect Analysis Report'),
            ('HOLD_STATUS', 'Hold Status Report'),
            ('FIRST_PASS_YIELD', 'First Pass Yield Report'),
            ('CORRECTIVE_ACTION', 'Corrective Action Report'),
            ('AUDIT_TRAIL', 'Audit Trail Report'),
        ]
    )
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    part = serializers.PrimaryKeyRelatedField(
        queryset=Part.objects.all(),
        required=False,
        allow_null=True
    )
    include_details = serializers.BooleanField(default=True)
    format = serializers.ChoiceField(
        choices=[
            ('JSON', 'JSON'),
            ('CSV', 'CSV'),
            ('PDF', 'PDF'),
        ],
        default='JSON'
    )


class DefectParetoSerializer(serializers.Serializer):
    """Serializer for Defect Pareto analysis.

    BEP MES Alignment: Supports continuous improvement through
    Pareto analysis of defect categories and root causes.
    """

    category = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()
    cumulative_percentage = serializers.FloatField()


class FirstPassYieldTrendSerializer(serializers.Serializer):
    """Serializer for First Pass Yield trend data.

    BEP MES Alignment: Provides trend data for first-pass yield
    monitoring and continuous improvement tracking.
    """

    period = serializers.DateTimeField()
    first_pass_yield = serializers.FloatField()
    total_inspected = serializers.IntegerField()
    total_passed = serializers.IntegerField()
    target = serializers.FloatField(required=False, allow_null=True)
