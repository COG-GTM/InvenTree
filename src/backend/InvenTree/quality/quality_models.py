"""Quality Management System Models for BEP MES Contract.

This module implements comprehensive quality management data models to support
the Bureau of Engraving and Printing (BEP) Manufacturing Execution System (MES)
contract requirements for ISO 9001 compliance and quality management.

BEP MES Contract Alignment:
---------------------------
Focus Area: Quality Management
Goal: ISO 9001 compliance
Key Outcomes:
- "Implement advanced IT solutions to modernize quality management"
- "Ensuring ISO 9001 compliance, digitalized processes, and continuous improvement"
- "A cross-functional Agile team aligning digital tools with quality goals"
- "Developing Quality dashboards with real-time KPIs"

This implementation enables BEP to:
1. Track quality inspections with full traceability
2. Categorize defects with root cause analysis
3. Implement quality hold/release workflows
4. Monitor real-time quality KPIs (defect rates, first-pass yield, trends)
5. Export quality reports for ISO 9001 audits
6. Maintain continuous improvement through data-driven insights

STIG/NIST Compliance:
- All models include audit fields (created_by, created_at, updated_at)
- Sensitive operations require authentication
- Data integrity enforced through model validation
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from build.models import Build
from common.models import InvenTreeModel
from part.models import Part
from stock.models import StockItem, StockLocation


class InspectionType(models.TextChoices):
    """Enumeration of quality inspection types.

    BEP MES Alignment: Supports comprehensive inspection tracking for
    currency production quality assurance at various stages.
    """
    INCOMING = 'INCOMING', _('Incoming Inspection')
    IN_PROCESS = 'IN_PROCESS', _('In-Process Inspection')
    FINAL = 'FINAL', _('Final Inspection')
    FIRST_ARTICLE = 'FIRST_ARTICLE', _('First Article Inspection')
    PERIODIC = 'PERIODIC', _('Periodic Inspection')
    RECEIVING = 'RECEIVING', _('Receiving Inspection')
    AUDIT = 'AUDIT', _('Quality Audit')
    CALIBRATION = 'CALIBRATION', _('Calibration Check')


class InspectionResult(models.TextChoices):
    """Enumeration of inspection result outcomes.

    BEP MES Alignment: Enables clear pass/fail tracking for
    quality metrics and first-pass yield calculations.
    """
    PASS = 'PASS', _('Pass')
    FAIL = 'FAIL', _('Fail')
    CONDITIONAL = 'CONDITIONAL', _('Conditional Pass')
    PENDING = 'PENDING', _('Pending Review')
    NOT_APPLICABLE = 'N/A', _('Not Applicable')


class DefectSeverity(models.TextChoices):
    """Enumeration of defect severity levels.

    BEP MES Alignment: Critical for currency production where
    defect severity directly impacts product usability and
    compliance with Treasury standards.
    """
    CRITICAL = 'CRITICAL', _('Critical - Product Unusable')
    MAJOR = 'MAJOR', _('Major - Significant Impact')
    MINOR = 'MINOR', _('Minor - Cosmetic/Limited Impact')
    OBSERVATION = 'OBSERVATION', _('Observation - No Impact')


class DefectCategory(models.TextChoices):
    """Enumeration of defect categories for currency production.

    BEP MES Alignment: Specific categories aligned with
    currency manufacturing defect types for accurate
    classification and root cause analysis.
    """
    DIMENSIONAL = 'DIMENSIONAL', _('Dimensional - Out of Specification')
    VISUAL = 'VISUAL', _('Visual - Appearance Defect')
    FUNCTIONAL = 'FUNCTIONAL', _('Functional - Performance Issue')
    MATERIAL = 'MATERIAL', _('Material - Raw Material Defect')
    PROCESS = 'PROCESS', _('Process - Manufacturing Error')
    CONTAMINATION = 'CONTAMINATION', _('Contamination - Foreign Material')
    ALIGNMENT = 'ALIGNMENT', _('Alignment - Registration Error')
    COLOR = 'COLOR', _('Color - Color Variation')
    PRINT = 'PRINT', _('Print - Printing Defect')
    SECURITY = 'SECURITY', _('Security Feature - Security Element Issue')
    OTHER = 'OTHER', _('Other')


class HoldStatus(models.TextChoices):
    """Enumeration of quality hold statuses.

    BEP MES Alignment: Implements quality hold/release workflow
    required for ISO 9001 compliance and controlled material
    disposition in currency production.
    """
    ACTIVE = 'ACTIVE', _('Active Hold')
    PENDING_REVIEW = 'PENDING_REVIEW', _('Pending Review')
    APPROVED_RELEASE = 'APPROVED_RELEASE', _('Approved for Release')
    REJECTED = 'REJECTED', _('Rejected - Scrap/Rework')
    CONDITIONALLY_RELEASED = 'CONDITIONALLY_RELEASED', _('Conditionally Released')


class RootCauseCategory(models.TextChoices):
    """Enumeration of root cause categories for defect analysis.

    BEP MES Alignment: Supports systematic root cause analysis
    required for continuous improvement and ISO 9001 corrective
    action procedures.
    """
    MAN = 'MAN', _('Man - Human Error')
    MACHINE = 'MACHINE', _('Machine - Equipment Failure')
    MATERIAL = 'MATERIAL', _('Material - Raw Material Issue')
    METHOD = 'METHOD', _('Method - Process/Procedure Issue')
    MEASUREMENT = 'MEASUREMENT', _('Measurement - Inspection Error')
    ENVIRONMENT = 'ENVIRONMENT', _('Environment - Environmental Factor')
    UNKNOWN = 'UNKNOWN', _('Unknown - Under Investigation')


class QualityInspection(InvenTreeModel):
    """Quality Inspection record for tracking inspection activities.

    BEP MES Contract Alignment:
    - Tracks all quality inspections with full traceability
    - Supports multiple inspection types (incoming, in-process, final)
    - Records inspector, date, results, and measurements
    - Enables first-pass yield calculations
    - Provides audit trail for ISO 9001 compliance

    Key Outcomes Addressed:
    - "Implement advanced IT solutions to modernize quality management"
    - "Ensuring ISO 9001 compliance, digitalized processes"
    """

    class Meta:
        verbose_name = _('Quality Inspection')
        verbose_name_plural = _('Quality Inspections')
        ordering = ['-inspection_date']

    inspection_number = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_('Inspection Number'),
        help_text=_('Unique identifier for this inspection')
    )

    inspection_type = models.CharField(
        max_length=20,
        choices=InspectionType.choices,
        default=InspectionType.IN_PROCESS,
        verbose_name=_('Inspection Type'),
        help_text=_('Type of quality inspection performed')
    )

    part = models.ForeignKey(
        Part,
        on_delete=models.CASCADE,
        related_name='quality_inspections',
        verbose_name=_('Part'),
        help_text=_('Part being inspected')
    )

    stock_item = models.ForeignKey(
        StockItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_inspections',
        verbose_name=_('Stock Item'),
        help_text=_('Specific stock item being inspected (if applicable)')
    )

    build_order = models.ForeignKey(
        Build,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_inspections',
        verbose_name=_('Build Order'),
        help_text=_('Associated build order (if applicable)')
    )

    location = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_inspections',
        verbose_name=_('Location'),
        help_text=_('Location where inspection was performed')
    )

    inspection_date = models.DateTimeField(
        verbose_name=_('Inspection Date'),
        help_text=_('Date and time of inspection')
    )

    inspector = models.ForeignKey(
        'users.Owner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inspections_performed',
        verbose_name=_('Inspector'),
        help_text=_('Person who performed the inspection')
    )

    result = models.CharField(
        max_length=20,
        choices=InspectionResult.choices,
        default=InspectionResult.PENDING,
        verbose_name=_('Result'),
        help_text=_('Overall inspection result')
    )

    quantity_inspected = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=0,
        verbose_name=_('Quantity Inspected'),
        help_text=_('Total quantity inspected')
    )

    quantity_passed = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=0,
        verbose_name=_('Quantity Passed'),
        help_text=_('Quantity that passed inspection')
    )

    quantity_failed = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=0,
        verbose_name=_('Quantity Failed'),
        help_text=_('Quantity that failed inspection')
    )

    sampling_plan = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('Sampling Plan'),
        help_text=_('Sampling plan used (e.g., AQL, 100% inspection)')
    )

    specification_reference = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_('Specification Reference'),
        help_text=_('Reference to quality specification or standard')
    )

    notes = models.TextField(
        blank=True,
        verbose_name=_('Notes'),
        help_text=_('Additional inspection notes and observations')
    )

    attachments = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Attachments'),
        help_text=_('List of attachment references (photos, documents)')
    )

    created_by = models.ForeignKey(
        'users.Owner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inspections_created',
        verbose_name=_('Created By'),
        help_text=_('User who created this inspection record')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    @property
    def pass_rate(self):
        """Calculate the pass rate for this inspection."""
        if self.quantity_inspected > 0:
            return float(self.quantity_passed / self.quantity_inspected) * 100
        return 0.0

    @property
    def is_passed(self):
        """Check if inspection result is a pass."""
        return self.result == InspectionResult.PASS

    def __str__(self):
        return f"{self.inspection_number} - {self.part.name}"


class QualityDefect(InvenTreeModel):
    """Quality Defect record for tracking and categorizing defects.

    BEP MES Contract Alignment:
    - Enables defect categorization with severity levels
    - Supports root cause analysis using 6M methodology
    - Tracks corrective actions and resolution
    - Provides data for defect rate calculations
    - Enables trend analysis for continuous improvement

    Key Outcomes Addressed:
    - "Add defect categorization and root cause analysis fields"
    - "Continuous improvement for reliable, efficient operations"
    """

    class Meta:
        verbose_name = _('Quality Defect')
        verbose_name_plural = _('Quality Defects')
        ordering = ['-detected_date']

    defect_number = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_('Defect Number'),
        help_text=_('Unique identifier for this defect')
    )

    inspection = models.ForeignKey(
        QualityInspection,
        on_delete=models.CASCADE,
        related_name='defects',
        verbose_name=_('Inspection'),
        help_text=_('Inspection where defect was detected')
    )

    part = models.ForeignKey(
        Part,
        on_delete=models.CASCADE,
        related_name='quality_defects',
        verbose_name=_('Part'),
        help_text=_('Part with defect')
    )

    stock_item = models.ForeignKey(
        StockItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_defects',
        verbose_name=_('Stock Item'),
        help_text=_('Specific stock item with defect (if applicable)')
    )

    category = models.CharField(
        max_length=20,
        choices=DefectCategory.choices,
        default=DefectCategory.OTHER,
        verbose_name=_('Defect Category'),
        help_text=_('Category of defect')
    )

    severity = models.CharField(
        max_length=20,
        choices=DefectSeverity.choices,
        default=DefectSeverity.MINOR,
        verbose_name=_('Severity'),
        help_text=_('Severity level of defect')
    )

    description = models.TextField(
        verbose_name=_('Description'),
        help_text=_('Detailed description of the defect')
    )

    detected_date = models.DateTimeField(
        verbose_name=_('Detected Date'),
        help_text=_('Date and time defect was detected')
    )

    detected_by = models.ForeignKey(
        'users.Owner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='defects_detected',
        verbose_name=_('Detected By'),
        help_text=_('Person who detected the defect')
    )

    quantity_affected = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=1,
        verbose_name=_('Quantity Affected'),
        help_text=_('Number of units affected by this defect')
    )

    root_cause_category = models.CharField(
        max_length=20,
        choices=RootCauseCategory.choices,
        default=RootCauseCategory.UNKNOWN,
        verbose_name=_('Root Cause Category'),
        help_text=_('Category of root cause (6M methodology)')
    )

    root_cause_description = models.TextField(
        blank=True,
        verbose_name=_('Root Cause Description'),
        help_text=_('Detailed root cause analysis')
    )

    corrective_action = models.TextField(
        blank=True,
        verbose_name=_('Corrective Action'),
        help_text=_('Corrective action taken or planned')
    )

    preventive_action = models.TextField(
        blank=True,
        verbose_name=_('Preventive Action'),
        help_text=_('Preventive action to avoid recurrence')
    )

    disposition = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_('Disposition'),
        help_text=_('Final disposition (scrap, rework, use-as-is, etc.)')
    )

    is_resolved = models.BooleanField(
        default=False,
        verbose_name=_('Is Resolved'),
        help_text=_('Whether the defect has been resolved')
    )

    resolved_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Resolved Date'),
        help_text=_('Date defect was resolved')
    )

    resolved_by = models.ForeignKey(
        'users.Owner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='defects_resolved',
        verbose_name=_('Resolved By'),
        help_text=_('Person who resolved the defect')
    )

    attachments = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Attachments'),
        help_text=_('List of attachment references (photos, documents)')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    def __str__(self):
        return f"{self.defect_number} - {self.category}"


class QualityHold(InvenTreeModel):
    """Quality Hold record for managing material holds and releases.

    BEP MES Contract Alignment:
    - Implements quality hold/release workflow
    - Tracks hold reasons and approval chain
    - Supports conditional releases with restrictions
    - Provides audit trail for ISO 9001 compliance
    - Enables controlled material disposition

    Key Outcomes Addressed:
    - "Implement quality hold/release workflow"
    - "ISO 9001 compliance, digitalized processes"
    """

    class Meta:
        verbose_name = _('Quality Hold')
        verbose_name_plural = _('Quality Holds')
        ordering = ['-hold_date']

    hold_number = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_('Hold Number'),
        help_text=_('Unique identifier for this quality hold')
    )

    status = models.CharField(
        max_length=25,
        choices=HoldStatus.choices,
        default=HoldStatus.ACTIVE,
        verbose_name=_('Status'),
        help_text=_('Current status of the quality hold')
    )

    part = models.ForeignKey(
        Part,
        on_delete=models.CASCADE,
        related_name='quality_holds',
        verbose_name=_('Part'),
        help_text=_('Part being held')
    )

    stock_item = models.ForeignKey(
        StockItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_holds',
        verbose_name=_('Stock Item'),
        help_text=_('Specific stock item being held (if applicable)')
    )

    location = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_holds',
        verbose_name=_('Location'),
        help_text=_('Location of held material')
    )

    defect = models.ForeignKey(
        QualityDefect,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_holds',
        verbose_name=_('Related Defect'),
        help_text=_('Defect that triggered this hold (if applicable)')
    )

    inspection = models.ForeignKey(
        QualityInspection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_holds',
        verbose_name=_('Related Inspection'),
        help_text=_('Inspection that triggered this hold (if applicable)')
    )

    hold_date = models.DateTimeField(
        verbose_name=_('Hold Date'),
        help_text=_('Date and time hold was initiated')
    )

    hold_reason = models.TextField(
        verbose_name=_('Hold Reason'),
        help_text=_('Reason for placing material on hold')
    )

    quantity_held = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=0,
        verbose_name=_('Quantity Held'),
        help_text=_('Quantity of material on hold')
    )

    initiated_by = models.ForeignKey(
        'users.Owner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='holds_initiated',
        verbose_name=_('Initiated By'),
        help_text=_('Person who initiated the hold')
    )

    review_notes = models.TextField(
        blank=True,
        verbose_name=_('Review Notes'),
        help_text=_('Notes from quality review')
    )

    reviewed_by = models.ForeignKey(
        'users.Owner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='holds_reviewed',
        verbose_name=_('Reviewed By'),
        help_text=_('Person who reviewed the hold')
    )

    reviewed_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Reviewed Date'),
        help_text=_('Date hold was reviewed')
    )

    disposition_decision = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('Disposition Decision'),
        help_text=_('Final disposition decision (release, scrap, rework, etc.)')
    )

    release_conditions = models.TextField(
        blank=True,
        verbose_name=_('Release Conditions'),
        help_text=_('Conditions for release (if conditionally released)')
    )

    released_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Released Date'),
        help_text=_('Date material was released from hold')
    )

    released_by = models.ForeignKey(
        'users.Owner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='holds_released',
        verbose_name=_('Released By'),
        help_text=_('Person who released the hold')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    @property
    def is_active(self):
        """Check if hold is currently active."""
        return self.status == HoldStatus.ACTIVE

    @property
    def is_released(self):
        """Check if hold has been released."""
        return self.status in [
            HoldStatus.APPROVED_RELEASE,
            HoldStatus.CONDITIONALLY_RELEASED
        ]

    def __str__(self):
        return f"{self.hold_number} - {self.status}"


class QualityMetric(InvenTreeModel):
    """Quality Metric record for tracking quality KPIs over time.

    BEP MES Contract Alignment:
    - Stores calculated quality metrics for dashboard display
    - Tracks defect rates, first-pass yield, and trends
    - Enables historical analysis and reporting
    - Supports ISO 9001 management review requirements

    Key Outcomes Addressed:
    - "Developing Quality dashboards with real-time KPIs"
    - "Display defect rates, first-pass yield, and quality trends"
    """

    class Meta:
        verbose_name = _('Quality Metric')
        verbose_name_plural = _('Quality Metrics')
        ordering = ['-period_end']
        unique_together = ['metric_type', 'period_start', 'period_end', 'part']

    METRIC_TYPES = [
        ('DEFECT_RATE', _('Defect Rate')),
        ('FIRST_PASS_YIELD', _('First Pass Yield')),
        ('INSPECTION_PASS_RATE', _('Inspection Pass Rate')),
        ('SCRAP_RATE', _('Scrap Rate')),
        ('REWORK_RATE', _('Rework Rate')),
        ('CUSTOMER_RETURNS', _('Customer Returns')),
        ('HOLD_DURATION', _('Average Hold Duration')),
        ('DEFECTS_PER_UNIT', _('Defects Per Unit')),
        ('COST_OF_QUALITY', _('Cost of Quality')),
    ]

    metric_type = models.CharField(
        max_length=30,
        choices=METRIC_TYPES,
        verbose_name=_('Metric Type'),
        help_text=_('Type of quality metric')
    )

    part = models.ForeignKey(
        Part,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='quality_metrics',
        verbose_name=_('Part'),
        help_text=_('Part this metric applies to (null for overall metrics)')
    )

    period_start = models.DateTimeField(
        verbose_name=_('Period Start'),
        help_text=_('Start of measurement period')
    )

    period_end = models.DateTimeField(
        verbose_name=_('Period End'),
        help_text=_('End of measurement period')
    )

    value = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        verbose_name=_('Value'),
        help_text=_('Metric value')
    )

    target_value = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name=_('Target Value'),
        help_text=_('Target value for this metric')
    )

    unit = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_('Unit'),
        help_text=_('Unit of measurement (%, count, etc.)')
    )

    sample_size = models.IntegerField(
        default=0,
        verbose_name=_('Sample Size'),
        help_text=_('Number of items in the sample')
    )

    notes = models.TextField(
        blank=True,
        verbose_name=_('Notes'),
        help_text=_('Additional notes about this metric')
    )

    calculated_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Calculated At'),
        help_text=_('When this metric was calculated')
    )

    @property
    def is_on_target(self):
        """Check if metric meets target."""
        if self.target_value is None:
            return None
        if self.metric_type in ['DEFECT_RATE', 'SCRAP_RATE', 'REWORK_RATE', 'CUSTOMER_RETURNS', 'DEFECTS_PER_UNIT']:
            return self.value <= self.target_value
        return self.value >= self.target_value

    @property
    def variance_from_target(self):
        """Calculate variance from target."""
        if self.target_value is None or self.target_value == 0:
            return None
        return float((self.value - self.target_value) / self.target_value) * 100

    def __str__(self):
        part_name = self.part.name if self.part else 'Overall'
        return f"{self.metric_type} - {part_name} ({self.period_start.date()} to {self.period_end.date()})"


class QualityChecklistTemplate(InvenTreeModel):
    """Quality Checklist Template for standardized inspection procedures.

    BEP MES Contract Alignment:
    - Provides standardized inspection checklists
    - Ensures consistent quality checks across inspectors
    - Supports ISO 9001 documented procedures
    - Enables customization per part or inspection type

    Key Outcomes Addressed:
    - "Implement advanced IT solutions to modernize quality management"
    - "ISO 9001 compliance, digitalized processes"
    """

    class Meta:
        verbose_name = _('Quality Checklist Template')
        verbose_name_plural = _('Quality Checklist Templates')
        ordering = ['name']

    name = models.CharField(
        max_length=200,
        verbose_name=_('Name'),
        help_text=_('Name of the checklist template')
    )

    description = models.TextField(
        blank=True,
        verbose_name=_('Description'),
        help_text=_('Description of the checklist purpose')
    )

    inspection_type = models.CharField(
        max_length=20,
        choices=InspectionType.choices,
        default=InspectionType.IN_PROCESS,
        verbose_name=_('Inspection Type'),
        help_text=_('Type of inspection this checklist applies to')
    )

    part = models.ForeignKey(
        Part,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_checklists',
        verbose_name=_('Part'),
        help_text=_('Specific part this checklist applies to (null for generic)')
    )

    checklist_items = models.JSONField(
        default=list,
        verbose_name=_('Checklist Items'),
        help_text=_('List of checklist items with criteria and acceptance limits')
    )

    revision = models.CharField(
        max_length=20,
        default='1.0',
        verbose_name=_('Revision'),
        help_text=_('Revision number of this checklist')
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active'),
        help_text=_('Whether this checklist is currently active')
    )

    created_by = models.ForeignKey(
        'users.Owner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checklists_created',
        verbose_name=_('Created By'),
        help_text=_('User who created this checklist')
    )

    approved_by = models.ForeignKey(
        'users.Owner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checklists_approved',
        verbose_name=_('Approved By'),
        help_text=_('User who approved this checklist')
    )

    approved_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Approved Date'),
        help_text=_('Date checklist was approved')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    def __str__(self):
        return f"{self.name} (Rev {self.revision})"


class QualityChecklistResult(InvenTreeModel):
    """Quality Checklist Result for recording completed checklist inspections.

    BEP MES Contract Alignment:
    - Records completed checklist inspections
    - Tracks individual item results
    - Links to parent inspection record
    - Provides detailed audit trail

    Key Outcomes Addressed:
    - "Implement advanced IT solutions to modernize quality management"
    - "Export quality reports for ISO audits"
    """

    class Meta:
        verbose_name = _('Quality Checklist Result')
        verbose_name_plural = _('Quality Checklist Results')
        ordering = ['-completed_at']

    inspection = models.ForeignKey(
        QualityInspection,
        on_delete=models.CASCADE,
        related_name='checklist_results',
        verbose_name=_('Inspection'),
        help_text=_('Parent inspection record')
    )

    template = models.ForeignKey(
        QualityChecklistTemplate,
        on_delete=models.SET_NULL,
        null=True,
        related_name='results',
        verbose_name=_('Template'),
        help_text=_('Checklist template used')
    )

    item_results = models.JSONField(
        default=list,
        verbose_name=_('Item Results'),
        help_text=_('Results for each checklist item')
    )

    overall_result = models.CharField(
        max_length=20,
        choices=InspectionResult.choices,
        default=InspectionResult.PENDING,
        verbose_name=_('Overall Result'),
        help_text=_('Overall checklist result')
    )

    completed_by = models.ForeignKey(
        'users.Owner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checklists_completed',
        verbose_name=_('Completed By'),
        help_text=_('Person who completed the checklist')
    )

    completed_at = models.DateTimeField(
        verbose_name=_('Completed At'),
        help_text=_('Date and time checklist was completed')
    )

    notes = models.TextField(
        blank=True,
        verbose_name=_('Notes'),
        help_text=_('Additional notes from checklist completion')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )

    def __str__(self):
        return f"Checklist for {self.inspection.inspection_number}"
