"""Quality Management System REST API for BEP MES Contract.

This module implements REST API endpoints for the quality management system
to support the Bureau of Engraving and Printing (BEP) Manufacturing Execution
System (MES) contract requirements.

BEP MES Contract Alignment:
---------------------------
Focus Area: Quality Management
Goal: ISO 9001 compliance
Key Outcomes:
- "Implement advanced IT solutions to modernize quality management"
- "Ensuring ISO 9001 compliance, digitalized processes, and continuous improvement"
- "A cross-functional Agile team aligning digital tools with quality goals"
- "Developing Quality dashboards with real-time KPIs"

API Endpoints:
- GET/POST /api/quality/inspections/ - List/create inspections
- GET/PUT/DELETE /api/quality/inspections/{pk}/ - Inspection detail
- GET/POST /api/quality/defects/ - List/create defects
- GET/PUT/DELETE /api/quality/defects/{pk}/ - Defect detail
- POST /api/quality/defects/{pk}/resolve/ - Resolve defect
- GET/POST /api/quality/holds/ - List/create holds
- GET/PUT/DELETE /api/quality/holds/{pk}/ - Hold detail
- POST /api/quality/holds/{pk}/review/ - Review hold
- POST /api/quality/holds/{pk}/release/ - Release hold
- GET/POST /api/quality/metrics/ - List/create metrics
- GET/POST /api/quality/checklists/ - List/create checklist templates
- GET/POST /api/quality/checklist-results/ - List/create checklist results
- GET /api/quality/dashboard/ - Quality dashboard data
- POST /api/quality/reports/ - Generate quality reports
"""

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncDay, TruncWeek
from django.utils import timezone

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from quality.quality_models import (
    DefectSeverity,
    HoldStatus,
    InspectionResult,
    QualityChecklistResult,
    QualityChecklistTemplate,
    QualityDefect,
    QualityHold,
    QualityInspection,
    QualityMetric,
)
from quality.quality_serializers import (
    DefectParetoSerializer,
    QualityChecklistResultSerializer,
    QualityChecklistTemplateSerializer,
    QualityDashboardSerializer,
    QualityDefectCreateSerializer,
    QualityDefectResolveSerializer,
    QualityDefectSerializer,
    QualityHoldCreateSerializer,
    QualityHoldReleaseSerializer,
    QualityHoldReviewSerializer,
    QualityHoldSerializer,
    QualityInspectionCreateSerializer,
    QualityInspectionSerializer,
    QualityMetricSerializer,
    QualityReportSerializer,
)


class QualityInspectionList(generics.ListCreateAPIView):
    """API endpoint for listing and creating quality inspections.

    BEP MES Contract Alignment:
    - Enables tracking of all quality inspections with full traceability
    - Supports multiple inspection types (incoming, in-process, final)
    - Provides audit trail for ISO 9001 compliance

    GET: List all inspections with filtering and search
    POST: Create a new inspection record
    """

    queryset = QualityInspection.objects.all()
    filterset_fields = [
        'inspection_type',
        'part',
        'stock_item',
        'build_order',
        'location',
        'inspector',
        'result',
    ]
    search_fields = ['inspection_number', 'notes', 'specification_reference']
    ordering_fields = ['inspection_date', 'created_at', 'inspection_number']
    ordering = ['-inspection_date']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return QualityInspectionCreateSerializer
        return QualityInspectionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        date_from = params.get('date_from')
        if date_from:
            queryset = queryset.filter(inspection_date__gte=date_from)

        date_to = params.get('date_to')
        if date_to:
            queryset = queryset.filter(inspection_date__lte=date_to)

        result_filter = params.get('result_filter')
        if result_filter == 'passed':
            queryset = queryset.filter(result=InspectionResult.PASS)
        elif result_filter == 'failed':
            queryset = queryset.filter(result=InspectionResult.FAIL)
        elif result_filter == 'pending':
            queryset = queryset.filter(result=InspectionResult.PENDING)

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class QualityInspectionDetail(generics.RetrieveUpdateDestroyAPIView):
    """API endpoint for retrieving, updating, and deleting a quality inspection.

    BEP MES Contract Alignment:
    - Provides detailed inspection data with full traceability
    - Enables inspection updates and corrections
    - Maintains audit trail for ISO 9001 compliance
    """

    queryset = QualityInspection.objects.all()
    serializer_class = QualityInspectionSerializer


class QualityDefectList(generics.ListCreateAPIView):
    """API endpoint for listing and creating quality defects.

    BEP MES Contract Alignment:
    - Enables defect categorization with severity levels
    - Supports root cause analysis using 6M methodology
    - Provides data for defect rate calculations and trend analysis

    GET: List all defects with filtering and search
    POST: Create a new defect record
    """

    queryset = QualityDefect.objects.all()
    filterset_fields = [
        'inspection',
        'part',
        'stock_item',
        'category',
        'severity',
        'root_cause_category',
        'is_resolved',
        'detected_by',
    ]
    search_fields = ['defect_number', 'description', 'corrective_action']
    ordering_fields = ['detected_date', 'created_at', 'severity']
    ordering = ['-detected_date']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return QualityDefectCreateSerializer
        return QualityDefectSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        date_from = params.get('date_from')
        if date_from:
            queryset = queryset.filter(detected_date__gte=date_from)

        date_to = params.get('date_to')
        if date_to:
            queryset = queryset.filter(detected_date__lte=date_to)

        unresolved_only = params.get('unresolved_only')
        if unresolved_only and unresolved_only.lower() == 'true':
            queryset = queryset.filter(is_resolved=False)

        return queryset


class QualityDefectDetail(generics.RetrieveUpdateDestroyAPIView):
    """API endpoint for retrieving, updating, and deleting a quality defect.

    BEP MES Contract Alignment:
    - Provides detailed defect data with root cause analysis
    - Enables defect updates and resolution tracking
    - Maintains audit trail for continuous improvement
    """

    queryset = QualityDefect.objects.all()
    serializer_class = QualityDefectSerializer


class QualityDefectResolve(APIView):
    """API endpoint for resolving a quality defect.

    BEP MES Contract Alignment:
    - Implements defect resolution workflow
    - Documents corrective and preventive actions
    - Supports continuous improvement tracking

    POST: Resolve a defect with corrective action documentation
    """

    @extend_schema(
        request=QualityDefectResolveSerializer,
        responses={200: QualityDefectSerializer}
    )
    def post(self, request, pk):
        try:
            defect = QualityDefect.objects.get(pk=pk)
        except QualityDefect.DoesNotExist:
            return Response(
                {'error': 'Defect not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if defect.is_resolved:
            return Response(
                {'error': 'Defect is already resolved'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = QualityDefectResolveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        defect.corrective_action = serializer.validated_data.get(
            'corrective_action', defect.corrective_action
        )
        defect.preventive_action = serializer.validated_data.get(
            'preventive_action', defect.preventive_action
        )
        defect.disposition = serializer.validated_data['disposition']
        defect.is_resolved = True
        defect.resolved_date = timezone.now()
        defect.resolved_by = request.user
        defect.save()

        return Response(
            QualityDefectSerializer(defect).data,
            status=status.HTTP_200_OK
        )


class QualityHoldList(generics.ListCreateAPIView):
    """API endpoint for listing and creating quality holds.

    BEP MES Contract Alignment:
    - Implements quality hold/release workflow
    - Tracks hold reasons and approval chain
    - Supports controlled material disposition

    GET: List all holds with filtering and search
    POST: Create a new hold record
    """

    queryset = QualityHold.objects.all()
    filterset_fields = [
        'status',
        'part',
        'stock_item',
        'location',
        'defect',
        'inspection',
        'initiated_by',
    ]
    search_fields = ['hold_number', 'hold_reason', 'review_notes']
    ordering_fields = ['hold_date', 'created_at', 'status']
    ordering = ['-hold_date']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return QualityHoldCreateSerializer
        return QualityHoldSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        active_only = params.get('active_only')
        if active_only and active_only.lower() == 'true':
            queryset = queryset.filter(status=HoldStatus.ACTIVE)

        pending_review = params.get('pending_review')
        if pending_review and pending_review.lower() == 'true':
            queryset = queryset.filter(status=HoldStatus.PENDING_REVIEW)

        return queryset

    def perform_create(self, serializer):
        serializer.save(initiated_by=self.request.user)


class QualityHoldDetail(generics.RetrieveUpdateDestroyAPIView):
    """API endpoint for retrieving, updating, and deleting a quality hold.

    BEP MES Contract Alignment:
    - Provides detailed hold data with approval chain
    - Enables hold updates and status tracking
    - Maintains audit trail for ISO 9001 compliance
    """

    queryset = QualityHold.objects.all()
    serializer_class = QualityHoldSerializer


class QualityHoldReview(APIView):
    """API endpoint for reviewing a quality hold.

    BEP MES Contract Alignment:
    - Implements hold review workflow
    - Documents disposition decisions
    - Supports conditional release with restrictions

    POST: Review a hold with disposition decision
    """

    @extend_schema(
        request=QualityHoldReviewSerializer,
        responses={200: QualityHoldSerializer}
    )
    def post(self, request, pk):
        try:
            hold = QualityHold.objects.get(pk=pk)
        except QualityHold.DoesNotExist:
            return Response(
                {'error': 'Hold not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if hold.status not in [HoldStatus.ACTIVE, HoldStatus.PENDING_REVIEW]:
            return Response(
                {'error': 'Hold cannot be reviewed in current status'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = QualityHoldReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        hold.review_notes = serializer.validated_data['review_notes']
        hold.disposition_decision = serializer.validated_data['disposition_decision']
        hold.status = serializer.validated_data['status']
        hold.release_conditions = serializer.validated_data.get('release_conditions', '')
        hold.reviewed_by = request.user
        hold.reviewed_date = timezone.now()

        if hold.status in [HoldStatus.APPROVED_RELEASE, HoldStatus.CONDITIONALLY_RELEASED]:
            hold.released_date = timezone.now()
            hold.released_by = request.user

        hold.save()

        return Response(
            QualityHoldSerializer(hold).data,
            status=status.HTTP_200_OK
        )


class QualityHoldRelease(APIView):
    """API endpoint for releasing a quality hold.

    BEP MES Contract Alignment:
    - Implements hold release workflow
    - Documents release authorization
    - Provides audit trail for material disposition

    POST: Release a hold that has been approved
    """

    @extend_schema(
        request=QualityHoldReleaseSerializer,
        responses={200: QualityHoldSerializer}
    )
    def post(self, request, pk):
        try:
            hold = QualityHold.objects.get(pk=pk)
        except QualityHold.DoesNotExist:
            return Response(
                {'error': 'Hold not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if hold.status != HoldStatus.PENDING_REVIEW:
            return Response(
                {'error': 'Hold must be in pending review status to release'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = QualityHoldReleaseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        hold.status = HoldStatus.APPROVED_RELEASE
        hold.released_date = timezone.now()
        hold.released_by = request.user
        if serializer.validated_data.get('release_notes'):
            hold.review_notes += f"\n\nRelease Notes: {serializer.validated_data['release_notes']}"
        hold.save()

        return Response(
            QualityHoldSerializer(hold).data,
            status=status.HTTP_200_OK
        )


class QualityMetricList(generics.ListCreateAPIView):
    """API endpoint for listing and creating quality metrics.

    BEP MES Contract Alignment:
    - Stores calculated quality metrics for dashboard display
    - Tracks defect rates, first-pass yield, and trends
    - Supports ISO 9001 management review requirements

    GET: List all metrics with filtering
    POST: Create a new metric record
    """

    queryset = QualityMetric.objects.all()
    serializer_class = QualityMetricSerializer
    filterset_fields = ['metric_type', 'part']
    ordering_fields = ['period_end', 'calculated_at']
    ordering = ['-period_end']

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        period_start = params.get('period_start')
        if period_start:
            queryset = queryset.filter(period_start__gte=period_start)

        period_end = params.get('period_end')
        if period_end:
            queryset = queryset.filter(period_end__lte=period_end)

        return queryset


class QualityMetricDetail(generics.RetrieveUpdateDestroyAPIView):
    """API endpoint for retrieving, updating, and deleting a quality metric.
    """

    queryset = QualityMetric.objects.all()
    serializer_class = QualityMetricSerializer


class QualityChecklistTemplateList(generics.ListCreateAPIView):
    """API endpoint for listing and creating quality checklist templates.

    BEP MES Contract Alignment:
    - Provides standardized inspection checklists
    - Ensures consistent quality checks across inspectors
    - Supports ISO 9001 documented procedures

    GET: List all checklist templates
    POST: Create a new checklist template
    """

    queryset = QualityChecklistTemplate.objects.all()
    serializer_class = QualityChecklistTemplateSerializer
    filterset_fields = ['inspection_type', 'part', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class QualityChecklistTemplateDetail(generics.RetrieveUpdateDestroyAPIView):
    """API endpoint for retrieving, updating, and deleting a checklist template.
    """

    queryset = QualityChecklistTemplate.objects.all()
    serializer_class = QualityChecklistTemplateSerializer


class QualityChecklistResultList(generics.ListCreateAPIView):
    """API endpoint for listing and creating checklist results.

    BEP MES Contract Alignment:
    - Records completed checklist inspections
    - Tracks individual item results
    - Provides detailed audit trail

    GET: List all checklist results
    POST: Create a new checklist result
    """

    queryset = QualityChecklistResult.objects.all()
    serializer_class = QualityChecklistResultSerializer
    filterset_fields = ['inspection', 'template', 'overall_result', 'completed_by']
    ordering_fields = ['completed_at', 'created_at']
    ordering = ['-completed_at']


class QualityChecklistResultDetail(generics.RetrieveUpdateDestroyAPIView):
    """API endpoint for retrieving, updating, and deleting a checklist result.
    """

    queryset = QualityChecklistResult.objects.all()
    serializer_class = QualityChecklistResultSerializer


class QualityDashboardView(APIView):
    """API endpoint for quality dashboard data aggregation.

    BEP MES Contract Alignment:
    - "Developing Quality dashboards with real-time KPIs"
    - "Display defect rates, first-pass yield, and quality trends"

    This endpoint aggregates quality data for dashboard display,
    providing real-time visibility into quality performance metrics
    as required for BEP's quality management modernization.

    GET: Retrieve aggregated quality dashboard data
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='period_start',
                type=OpenApiTypes.DATETIME,
                description='Start of reporting period'
            ),
            OpenApiParameter(
                name='period_end',
                type=OpenApiTypes.DATETIME,
                description='End of reporting period'
            ),
            OpenApiParameter(
                name='part',
                type=OpenApiTypes.INT,
                description='Filter by part ID'
            ),
        ],
        responses={200: QualityDashboardSerializer}
    )
    def get(self, request):
        params = request.query_params

        period_end = timezone.now()
        period_start = period_end - timezone.timedelta(days=30)

        if params.get('period_start'):
            period_start = timezone.datetime.fromisoformat(
                params['period_start'].replace('Z', '+00:00')
            )
        if params.get('period_end'):
            period_end = timezone.datetime.fromisoformat(
                params['period_end'].replace('Z', '+00:00')
            )

        inspections = QualityInspection.objects.filter(
            inspection_date__gte=period_start,
            inspection_date__lte=period_end
        )
        defects = QualityDefect.objects.filter(
            detected_date__gte=period_start,
            detected_date__lte=period_end
        )
        holds = QualityHold.objects.all()

        part_id = params.get('part')
        if part_id:
            inspections = inspections.filter(part_id=part_id)
            defects = defects.filter(part_id=part_id)
            holds = holds.filter(part_id=part_id)

        total_inspections = inspections.count()
        passed_inspections = inspections.filter(result=InspectionResult.PASS).count()
        failed_inspections = inspections.filter(result=InspectionResult.FAIL).count()
        inspection_pass_rate = (
            (passed_inspections / total_inspections * 100)
            if total_inspections > 0 else 0
        )

        total_defects = defects.count()
        critical_defects = defects.filter(severity=DefectSeverity.CRITICAL).count()
        major_defects = defects.filter(severity=DefectSeverity.MAJOR).count()
        minor_defects = defects.filter(severity=DefectSeverity.MINOR).count()

        total_inspected = inspections.aggregate(
            total=Sum('quantity_inspected')
        )['total'] or 0
        defect_rate = (total_defects / total_inspected * 100) if total_inspected > 0 else 0

        total_passed_first = inspections.aggregate(
            total=Sum('quantity_passed')
        )['total'] or 0
        first_pass_yield = (
            (total_passed_first / total_inspected * 100)
            if total_inspected > 0 else 0
        )

        active_holds = holds.filter(status=HoldStatus.ACTIVE).count()
        pending_review_holds = holds.filter(status=HoldStatus.PENDING_REVIEW).count()

        released_holds = holds.filter(released_date__isnull=False)
        if released_holds.exists():
            avg_duration = released_holds.annotate(
                duration=F('released_date') - F('hold_date')
            ).aggregate(avg=Avg('duration'))['avg']
            average_hold_duration_hours = (
                avg_duration.total_seconds() / 3600 if avg_duration else 0
            )
        else:
            average_hold_duration_hours = 0

        defects_by_category = dict(
            defects.values('category').annotate(count=Count('pk')).values_list('category', 'count')
        )

        defects_by_root_cause = dict(
            defects.values('root_cause_category').annotate(count=Count('pk')).values_list('root_cause_category', 'count')
        )

        inspections_by_type = dict(
            inspections.values('inspection_type').annotate(count=Count('pk')).values_list('inspection_type', 'count')
        )

        trend_data = list(
            inspections.annotate(day=TruncDay('inspection_date'))
            .values('day')
            .annotate(
                total=Count('pk'),
                passed=Count('pk', filter=Q(result=InspectionResult.PASS)),
                failed=Count('pk', filter=Q(result=InspectionResult.FAIL))
            )
            .order_by('day')
        )

        dashboard_data = {
            'period_start': period_start,
            'period_end': period_end,
            'total_inspections': total_inspections,
            'passed_inspections': passed_inspections,
            'failed_inspections': failed_inspections,
            'inspection_pass_rate': round(inspection_pass_rate, 2),
            'total_defects': total_defects,
            'critical_defects': critical_defects,
            'major_defects': major_defects,
            'minor_defects': minor_defects,
            'defect_rate': round(defect_rate, 4),
            'first_pass_yield': round(first_pass_yield, 2),
            'active_holds': active_holds,
            'pending_review_holds': pending_review_holds,
            'average_hold_duration_hours': round(average_hold_duration_hours, 2),
            'defects_by_category': defects_by_category,
            'defects_by_root_cause': defects_by_root_cause,
            'inspections_by_type': inspections_by_type,
            'trend_data': trend_data,
        }

        return Response(dashboard_data, status=status.HTTP_200_OK)


class QualityReportView(APIView):
    """API endpoint for generating quality reports.

    BEP MES Contract Alignment:
    - "Export quality reports for ISO audits"
    - "ISO 9001 compliance, digitalized processes"

    This endpoint generates quality reports for ISO 9001 audit compliance,
    including inspection summaries, defect analysis, and corrective action tracking.

    POST: Generate a quality report based on specified parameters
    """

    @extend_schema(
        request=QualityReportSerializer,
        responses={200: dict}
    )
    def post(self, request):
        serializer = QualityReportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        report_type = serializer.validated_data['report_type']
        period_start = serializer.validated_data['period_start']
        period_end = serializer.validated_data['period_end']
        part = serializer.validated_data.get('part')
        include_details = serializer.validated_data.get('include_details', True)

        inspections = QualityInspection.objects.filter(
            inspection_date__gte=period_start,
            inspection_date__lte=period_end
        )
        defects = QualityDefect.objects.filter(
            detected_date__gte=period_start,
            detected_date__lte=period_end
        )
        holds = QualityHold.objects.filter(
            hold_date__gte=period_start,
            hold_date__lte=period_end
        )

        if part:
            inspections = inspections.filter(part=part)
            defects = defects.filter(part=part)
            holds = holds.filter(part=part)

        report_data = {
            'report_type': report_type,
            'period_start': period_start.isoformat(),
            'period_end': period_end.isoformat(),
            'generated_at': timezone.now().isoformat(),
            'generated_by': request.user.username if request.user else 'System',
        }

        if report_type == 'INSPECTION_SUMMARY':
            report_data['summary'] = {
                'total_inspections': inspections.count(),
                'passed': inspections.filter(result=InspectionResult.PASS).count(),
                'failed': inspections.filter(result=InspectionResult.FAIL).count(),
                'conditional': inspections.filter(result=InspectionResult.CONDITIONAL).count(),
                'pending': inspections.filter(result=InspectionResult.PENDING).count(),
                'by_type': dict(
                    inspections.values('inspection_type')
                    .annotate(count=Count('pk'))
                    .values_list('inspection_type', 'count')
                ),
            }
            if include_details:
                report_data['details'] = QualityInspectionSerializer(
                    inspections, many=True
                ).data

        elif report_type == 'DEFECT_ANALYSIS':
            report_data['summary'] = {
                'total_defects': defects.count(),
                'by_severity': dict(
                    defects.values('severity')
                    .annotate(count=Count('pk'))
                    .values_list('severity', 'count')
                ),
                'by_category': dict(
                    defects.values('category')
                    .annotate(count=Count('pk'))
                    .values_list('category', 'count')
                ),
                'by_root_cause': dict(
                    defects.values('root_cause_category')
                    .annotate(count=Count('pk'))
                    .values_list('root_cause_category', 'count')
                ),
                'resolved': defects.filter(is_resolved=True).count(),
                'unresolved': defects.filter(is_resolved=False).count(),
            }
            if include_details:
                report_data['details'] = QualityDefectSerializer(
                    defects, many=True
                ).data

        elif report_type == 'HOLD_STATUS':
            report_data['summary'] = {
                'total_holds': holds.count(),
                'by_status': dict(
                    holds.values('status')
                    .annotate(count=Count('pk'))
                    .values_list('status', 'count')
                ),
                'active': holds.filter(status=HoldStatus.ACTIVE).count(),
                'released': holds.filter(
                    status__in=[HoldStatus.APPROVED_RELEASE, HoldStatus.CONDITIONALLY_RELEASED]
                ).count(),
                'rejected': holds.filter(status=HoldStatus.REJECTED).count(),
            }
            if include_details:
                report_data['details'] = QualityHoldSerializer(
                    holds, many=True
                ).data

        elif report_type == 'FIRST_PASS_YIELD':
            total_inspected = inspections.aggregate(
                total=Sum('quantity_inspected')
            )['total'] or 0
            total_passed = inspections.aggregate(
                total=Sum('quantity_passed')
            )['total'] or 0
            fpy = (total_passed / total_inspected * 100) if total_inspected > 0 else 0

            report_data['summary'] = {
                'total_inspected': float(total_inspected),
                'total_passed_first_time': float(total_passed),
                'first_pass_yield': round(fpy, 2),
                'trend': list(
                    inspections.annotate(week=TruncWeek('inspection_date'))
                    .values('week')
                    .annotate(
                        inspected=Sum('quantity_inspected'),
                        passed=Sum('quantity_passed')
                    )
                    .order_by('week')
                ),
            }

        elif report_type == 'CORRECTIVE_ACTION':
            defects_with_ca = defects.exclude(corrective_action='')
            report_data['summary'] = {
                'total_defects': defects.count(),
                'with_corrective_action': defects_with_ca.count(),
                'with_preventive_action': defects.exclude(preventive_action='').count(),
                'resolved': defects.filter(is_resolved=True).count(),
            }
            if include_details:
                report_data['details'] = QualityDefectSerializer(
                    defects_with_ca, many=True
                ).data

        elif report_type == 'AUDIT_TRAIL':
            report_data['inspections'] = {
                'count': inspections.count(),
                'records': QualityInspectionSerializer(
                    inspections.order_by('-inspection_date')[:100], many=True
                ).data if include_details else []
            }
            report_data['defects'] = {
                'count': defects.count(),
                'records': QualityDefectSerializer(
                    defects.order_by('-detected_date')[:100], many=True
                ).data if include_details else []
            }
            report_data['holds'] = {
                'count': holds.count(),
                'records': QualityHoldSerializer(
                    holds.order_by('-hold_date')[:100], many=True
                ).data if include_details else []
            }

        return Response(report_data, status=status.HTTP_200_OK)


class DefectParetoView(APIView):
    """API endpoint for Defect Pareto analysis.

    BEP MES Contract Alignment:
    - Supports continuous improvement through Pareto analysis
    - Identifies top defect categories for focused improvement
    - Enables data-driven quality management decisions

    GET: Retrieve Pareto analysis of defects by category or root cause
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='period_start',
                type=OpenApiTypes.DATETIME,
                description='Start of analysis period'
            ),
            OpenApiParameter(
                name='period_end',
                type=OpenApiTypes.DATETIME,
                description='End of analysis period'
            ),
            OpenApiParameter(
                name='group_by',
                type=OpenApiTypes.STR,
                description='Group by: category or root_cause',
                enum=['category', 'root_cause']
            ),
        ],
        responses={200: DefectParetoSerializer(many=True)}
    )
    def get(self, request):
        params = request.query_params

        period_end = timezone.now()
        period_start = period_end - timezone.timedelta(days=30)

        if params.get('period_start'):
            period_start = timezone.datetime.fromisoformat(
                params['period_start'].replace('Z', '+00:00')
            )
        if params.get('period_end'):
            period_end = timezone.datetime.fromisoformat(
                params['period_end'].replace('Z', '+00:00')
            )

        group_by = params.get('group_by', 'category')
        group_field = 'category' if group_by == 'category' else 'root_cause_category'

        defects = QualityDefect.objects.filter(
            detected_date__gte=period_start,
            detected_date__lte=period_end
        )

        total_defects = defects.count()
        if total_defects == 0:
            return Response([], status=status.HTTP_200_OK)

        grouped = list(
            defects.values(group_field)
            .annotate(count=Count('pk'))
            .order_by('-count')
        )

        pareto_data = []
        cumulative = 0
        for item in grouped:
            count = item['count']
            percentage = (count / total_defects) * 100
            cumulative += percentage
            pareto_data.append({
                'category': item[group_field],
                'count': count,
                'percentage': round(percentage, 2),
                'cumulative_percentage': round(cumulative, 2),
            })

        return Response(pareto_data, status=status.HTTP_200_OK)


quality_api_urls = [
    {
        'path': 'inspections/',
        'view': QualityInspectionList,
        'name': 'api-quality-inspection-list'
    },
    {
        'path': 'inspections/<int:pk>/',
        'view': QualityInspectionDetail,
        'name': 'api-quality-inspection-detail'
    },
    {
        'path': 'defects/',
        'view': QualityDefectList,
        'name': 'api-quality-defect-list'
    },
    {
        'path': 'defects/<int:pk>/',
        'view': QualityDefectDetail,
        'name': 'api-quality-defect-detail'
    },
    {
        'path': 'defects/<int:pk>/resolve/',
        'view': QualityDefectResolve,
        'name': 'api-quality-defect-resolve'
    },
    {
        'path': 'holds/',
        'view': QualityHoldList,
        'name': 'api-quality-hold-list'
    },
    {
        'path': 'holds/<int:pk>/',
        'view': QualityHoldDetail,
        'name': 'api-quality-hold-detail'
    },
    {
        'path': 'holds/<int:pk>/review/',
        'view': QualityHoldReview,
        'name': 'api-quality-hold-review'
    },
    {
        'path': 'holds/<int:pk>/release/',
        'view': QualityHoldRelease,
        'name': 'api-quality-hold-release'
    },
    {
        'path': 'metrics/',
        'view': QualityMetricList,
        'name': 'api-quality-metric-list'
    },
    {
        'path': 'metrics/<int:pk>/',
        'view': QualityMetricDetail,
        'name': 'api-quality-metric-detail'
    },
    {
        'path': 'checklists/',
        'view': QualityChecklistTemplateList,
        'name': 'api-quality-checklist-list'
    },
    {
        'path': 'checklists/<int:pk>/',
        'view': QualityChecklistTemplateDetail,
        'name': 'api-quality-checklist-detail'
    },
    {
        'path': 'checklist-results/',
        'view': QualityChecklistResultList,
        'name': 'api-quality-checklist-result-list'
    },
    {
        'path': 'checklist-results/<int:pk>/',
        'view': QualityChecklistResultDetail,
        'name': 'api-quality-checklist-result-detail'
    },
    {
        'path': 'dashboard/',
        'view': QualityDashboardView,
        'name': 'api-quality-dashboard'
    },
    {
        'path': 'reports/',
        'view': QualityReportView,
        'name': 'api-quality-reports'
    },
    {
        'path': 'pareto/',
        'view': DefectParetoView,
        'name': 'api-quality-pareto'
    },
]
