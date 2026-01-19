"""Supply Chain Enhancement models for BEP MES Contract.

This module implements real-time stock alerts and automated reconciliation
capabilities to support the Bureau of Engraving and Printing (BEP)
Manufacturing Execution System (MES) contract requirements.

BEP MES Contract Alignment:
- Supply Chain Team Focus Area: "Integrate automation, real-time tracking,
  and analytics into supply chain systems to improve transparency, efficiency,
  and risk management while enabling data-driven performance monitoring"
- Key Outcome: "A cross-functional Agile team improving inventory accuracy
  through real-time tracking and automated reconciliation"

This implementation enables:
1. Real-time stock level monitoring with configurable thresholds
2. Automated alerts when inventory falls below critical levels
3. Email and webhook notifications for supply chain managers
4. Automated reconciliation reports comparing physical vs. system counts
5. Discrepancy tracking and resolution workflows
6. Treasury-compliant export formats for audit trails
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

import structlog

import InvenTree.models
from part.models import Part
from stock.models import StockItem, StockLocation

logger = structlog.get_logger('inventree')


class AlertPriority(models.TextChoices):
    """Priority levels for stock alerts.

    Supports the BEP MES requirement for "risk management" by enabling
    prioritization of supply chain issues based on business impact.
    """

    CRITICAL = 'CRITICAL', _('Critical - Production at Risk')
    HIGH = 'HIGH', _('High - Immediate Action Required')
    MEDIUM = 'MEDIUM', _('Medium - Action Required Soon')
    LOW = 'LOW', _('Low - Monitor Situation')
    INFO = 'INFO', _('Informational')


class AlertStatus(models.TextChoices):
    """Status values for stock alerts.

    Supports the BEP MES requirement for "continuous improvement" by
    tracking alert lifecycle from creation to resolution.
    """

    ACTIVE = 'ACTIVE', _('Active')
    ACKNOWLEDGED = 'ACKNOWLEDGED', _('Acknowledged')
    IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
    RESOLVED = 'RESOLVED', _('Resolved')
    SUPPRESSED = 'SUPPRESSED', _('Suppressed')


class AlertType(models.TextChoices):
    """Types of stock alerts.

    Supports the BEP MES requirement for "data-driven performance monitoring"
    by categorizing different supply chain events.
    """

    LOW_STOCK = 'LOW_STOCK', _('Low Stock Level')
    CRITICAL_STOCK = 'CRITICAL_STOCK', _('Critical Stock Level')
    OUT_OF_STOCK = 'OUT_OF_STOCK', _('Out of Stock')
    OVERSTOCK = 'OVERSTOCK', _('Overstock Condition')
    EXPIRING_SOON = 'EXPIRING_SOON', _('Expiring Soon')
    EXPIRED = 'EXPIRED', _('Expired Stock')
    RECONCILIATION_DISCREPANCY = 'RECONCILIATION_DISCREPANCY', _('Reconciliation Discrepancy')
    REORDER_POINT = 'REORDER_POINT', _('Reorder Point Reached')


class ReconciliationStatus(models.TextChoices):
    """Status values for reconciliation records.

    Supports the BEP MES requirement for "automated reconciliation" by
    tracking the lifecycle of inventory reconciliation activities.
    """

    PENDING = 'PENDING', _('Pending Review')
    IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
    COMPLETED = 'COMPLETED', _('Completed')
    APPROVED = 'APPROVED', _('Approved')
    REJECTED = 'REJECTED', _('Rejected')


class DiscrepancyType(models.TextChoices):
    """Types of inventory discrepancies.

    Supports the BEP MES requirement for "inventory accuracy" by
    categorizing different types of count variances.
    """

    SHORTAGE = 'SHORTAGE', _('Physical Count Less Than System')
    OVERAGE = 'OVERAGE', _('Physical Count Greater Than System')
    LOCATION_MISMATCH = 'LOCATION_MISMATCH', _('Item in Wrong Location')
    CONDITION_ISSUE = 'CONDITION_ISSUE', _('Item Condition Discrepancy')
    MISSING = 'MISSING', _('Item Not Found')
    UNRECORDED = 'UNRECORDED', _('Unrecorded Item Found')


class StockAlertThreshold(InvenTree.models.MetadataMixin, models.Model):
    """Configurable thresholds for stock level alerts.

    This model enables BEP supply chain managers to define alert thresholds
    for parts or locations, supporting the contract requirement for
    "real-time tracking" and "risk management."

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "real-time tracking" of inventory levels
    - Enterprise Data: Supports "data-driven decisions" through configurable rules
    - Quality Management: Provides audit trail for ISO 9001 compliance

    Attributes:
        part: The part to monitor (optional, can be location-based)
        location: The location to monitor (optional, can be part-based)
        minimum_stock: Minimum stock level before triggering low stock alert
        critical_stock: Critical stock level before triggering critical alert
        reorder_point: Stock level at which to trigger reorder notification
        maximum_stock: Maximum stock level before triggering overstock alert
        alert_priority: Default priority for alerts from this threshold
        notification_emails: Comma-separated list of email addresses to notify
        webhook_url: URL for webhook notifications
        is_active: Whether this threshold is currently active
    """

    class Meta:
        verbose_name = _('Stock Alert Threshold')
        verbose_name_plural = _('Stock Alert Thresholds')
        unique_together = [['part', 'location']]

    @staticmethod
    def get_api_url():
        return reverse('api-stock-alert-threshold-list')

    part = models.ForeignKey(
        Part,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='stock_alert_thresholds',
        verbose_name=_('Part'),
        help_text=_('Part to monitor for stock alerts'),
    )

    location = models.ForeignKey(
        StockLocation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='stock_alert_thresholds',
        verbose_name=_('Location'),
        help_text=_('Location to monitor for stock alerts'),
    )

    minimum_stock = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name=_('Minimum Stock Level'),
        help_text=_('Stock level below which a low stock alert is triggered'),
    )

    critical_stock = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name=_('Critical Stock Level'),
        help_text=_('Stock level below which a critical alert is triggered'),
    )

    reorder_point = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name=_('Reorder Point'),
        help_text=_('Stock level at which to trigger reorder notification'),
    )

    maximum_stock = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name=_('Maximum Stock Level'),
        help_text=_('Stock level above which an overstock alert is triggered'),
    )

    alert_priority = models.CharField(
        max_length=20,
        choices=AlertPriority.choices,
        default=AlertPriority.MEDIUM,
        verbose_name=_('Default Alert Priority'),
        help_text=_('Default priority for alerts generated from this threshold'),
    )

    notification_emails = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Notification Emails'),
        help_text=_('Comma-separated list of email addresses for notifications'),
    )

    webhook_url = models.URLField(
        blank=True,
        default='',
        verbose_name=_('Webhook URL'),
        help_text=_('URL for webhook notifications (supports BEP system integration)'),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Active'),
        help_text=_('Whether this threshold is currently active'),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created'),
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated'),
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_stock_thresholds',
        verbose_name=_('Created By'),
    )

    def __str__(self):
        if self.part:
            return f"Threshold for {self.part.name}"
        elif self.location:
            return f"Threshold for {self.location.name}"
        return f"Stock Alert Threshold #{self.pk}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.part and not self.location:
            raise ValidationError(_('Either part or location must be specified'))
        if self.critical_stock > self.minimum_stock:
            raise ValidationError(_('Critical stock level must be less than or equal to minimum stock level'))

    def get_notification_email_list(self) -> list[str]:
        if not self.notification_emails:
            return []
        return [email.strip() for email in self.notification_emails.split(',') if email.strip()]

    def check_stock_level(self, current_stock: Decimal) -> Optional[AlertType]:
        if current_stock <= 0:
            return AlertType.OUT_OF_STOCK
        if current_stock <= self.critical_stock:
            return AlertType.CRITICAL_STOCK
        if current_stock <= self.minimum_stock:
            return AlertType.LOW_STOCK
        if self.reorder_point and current_stock <= self.reorder_point:
            return AlertType.REORDER_POINT
        if self.maximum_stock and current_stock > self.maximum_stock:
            return AlertType.OVERSTOCK
        return None


class StockAlert(InvenTree.models.MetadataMixin, models.Model):
    """Real-time stock alert for supply chain monitoring.

    This model captures stock-related alerts to support the BEP MES
    requirement for "real-time tracking" and "proactive action."

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "real-time tracking" of inventory issues
    - Data Analytics: Supports "proactive action" through alert notifications
    - Quality Management: Provides audit trail for ISO 9001 compliance

    Attributes:
        part: The part associated with this alert
        location: The location associated with this alert
        alert_type: Type of alert (low stock, critical, etc.)
        priority: Priority level of the alert
        status: Current status of the alert
        threshold: The threshold that triggered this alert
        current_stock: Stock level when alert was triggered
        threshold_value: The threshold value that was violated
        message: Human-readable alert message
        acknowledged_by: User who acknowledged the alert
        acknowledged_at: When the alert was acknowledged
        resolved_by: User who resolved the alert
        resolved_at: When the alert was resolved
        resolution_notes: Notes about how the alert was resolved
    """

    class Meta:
        verbose_name = _('Stock Alert')
        verbose_name_plural = _('Stock Alerts')
        ordering = ['-created_at']

    @staticmethod
    def get_api_url():
        return reverse('api-stock-alert-list')

    part = models.ForeignKey(
        Part,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='stock_alerts',
        verbose_name=_('Part'),
    )

    location = models.ForeignKey(
        StockLocation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='stock_alerts',
        verbose_name=_('Location'),
    )

    alert_type = models.CharField(
        max_length=30,
        choices=AlertType.choices,
        verbose_name=_('Alert Type'),
    )

    priority = models.CharField(
        max_length=20,
        choices=AlertPriority.choices,
        default=AlertPriority.MEDIUM,
        verbose_name=_('Priority'),
    )

    status = models.CharField(
        max_length=20,
        choices=AlertStatus.choices,
        default=AlertStatus.ACTIVE,
        verbose_name=_('Status'),
    )

    threshold = models.ForeignKey(
        StockAlertThreshold,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name=_('Threshold'),
    )

    current_stock = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        verbose_name=_('Current Stock Level'),
        help_text=_('Stock level when alert was triggered'),
    )

    threshold_value = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name=_('Threshold Value'),
        help_text=_('The threshold value that was violated'),
    )

    message = models.TextField(
        verbose_name=_('Message'),
        help_text=_('Human-readable alert message'),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created'),
    )

    acknowledged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_stock_alerts',
        verbose_name=_('Acknowledged By'),
    )

    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Acknowledged At'),
    )

    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_stock_alerts',
        verbose_name=_('Resolved By'),
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Resolved At'),
    )

    resolution_notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Resolution Notes'),
        help_text=_('Notes about how the alert was resolved'),
    )

    notification_sent = models.BooleanField(
        default=False,
        verbose_name=_('Notification Sent'),
        help_text=_('Whether notification has been sent for this alert'),
    )

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.part or self.location}"

    def acknowledge(self, user: User, notes: str = ''):
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        if notes:
            self.resolution_notes = notes
        self.save()

    def resolve(self, user: User, notes: str = ''):
        self.status = AlertStatus.RESOLVED
        self.resolved_by = user
        self.resolved_at = timezone.now()
        if notes:
            self.resolution_notes = notes
        self.save()


class InventoryReconciliation(InvenTree.models.MetadataMixin, models.Model):
    """Inventory reconciliation record for automated stocktaking.

    This model supports the BEP MES requirement for "automated reconciliation"
    by tracking physical counts against system records.

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "automated reconciliation" of inventory
    - Enterprise Data: Supports "trusted data products" through verification
    - Quality Management: Provides audit trail for ISO 9001 compliance

    Attributes:
        reference: Unique reference number for this reconciliation
        location: The location being reconciled
        status: Current status of the reconciliation
        scheduled_date: When the reconciliation was scheduled
        started_at: When the reconciliation started
        completed_at: When the reconciliation was completed
        performed_by: User who performed the reconciliation
        approved_by: User who approved the reconciliation
        notes: General notes about the reconciliation
        total_items_counted: Total number of items counted
        total_discrepancies: Number of discrepancies found
        total_variance_value: Total monetary value of variances
    """

    class Meta:
        verbose_name = _('Inventory Reconciliation')
        verbose_name_plural = _('Inventory Reconciliations')
        ordering = ['-created_at']

    @staticmethod
    def get_api_url():
        return reverse('api-inventory-reconciliation-list')

    reference = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_('Reference'),
        help_text=_('Unique reference number for this reconciliation'),
    )

    location = models.ForeignKey(
        StockLocation,
        on_delete=models.CASCADE,
        related_name='reconciliations',
        verbose_name=_('Location'),
        help_text=_('Location being reconciled'),
    )

    status = models.CharField(
        max_length=20,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.PENDING,
        verbose_name=_('Status'),
    )

    scheduled_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('Scheduled Date'),
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Started At'),
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Completed At'),
    )

    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='performed_reconciliations',
        verbose_name=_('Performed By'),
    )

    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_reconciliations',
        verbose_name=_('Approved By'),
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Approved At'),
    )

    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Notes'),
    )

    total_items_counted = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Total Items Counted'),
    )

    total_discrepancies = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Total Discrepancies'),
    )

    total_variance_value = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=Decimal('0'),
        verbose_name=_('Total Variance Value'),
        help_text=_('Total monetary value of inventory variances'),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created'),
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_reconciliations',
        verbose_name=_('Created By'),
    )

    def __str__(self):
        return f"Reconciliation {self.reference} - {self.location.name}"

    def start(self, user: User):
        self.status = ReconciliationStatus.IN_PROGRESS
        self.started_at = timezone.now()
        self.performed_by = user
        self.save()

    def complete(self):
        self.status = ReconciliationStatus.COMPLETED
        self.completed_at = timezone.now()
        self.total_items_counted = self.line_items.count()
        self.total_discrepancies = self.line_items.exclude(
            discrepancy_type__isnull=True
        ).count()
        self.save()

    def approve(self, user: User):
        self.status = ReconciliationStatus.APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

    def reject(self, user: User, notes: str = ''):
        self.status = ReconciliationStatus.REJECTED
        self.approved_by = user
        self.approved_at = timezone.now()
        if notes:
            self.notes = f"{self.notes}\nRejection reason: {notes}"
        self.save()


class ReconciliationLineItem(models.Model):
    """Individual line item in an inventory reconciliation.

    This model captures the comparison between physical counts and
    system records for each stock item, supporting the BEP MES
    requirement for "inventory accuracy."

    BEP MES Contract Alignment:
    - Supply Chain Team: Enables "inventory accuracy" tracking
    - Enterprise Data: Supports "discrepancy reports" generation
    - Quality Management: Provides detailed audit trail

    Attributes:
        reconciliation: The parent reconciliation record
        stock_item: The stock item being counted
        part: The part being counted (if no specific stock item)
        system_quantity: Quantity recorded in the system
        physical_quantity: Quantity counted physically
        variance: Difference between physical and system counts
        discrepancy_type: Type of discrepancy if any
        notes: Notes about this line item
        counted_by: User who performed the count
        counted_at: When the count was performed
    """

    class Meta:
        verbose_name = _('Reconciliation Line Item')
        verbose_name_plural = _('Reconciliation Line Items')

    reconciliation = models.ForeignKey(
        InventoryReconciliation,
        on_delete=models.CASCADE,
        related_name='line_items',
        verbose_name=_('Reconciliation'),
    )

    stock_item = models.ForeignKey(
        StockItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reconciliation_items',
        verbose_name=_('Stock Item'),
    )

    part = models.ForeignKey(
        Part,
        on_delete=models.CASCADE,
        related_name='reconciliation_items',
        verbose_name=_('Part'),
    )

    system_quantity = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        verbose_name=_('System Quantity'),
        help_text=_('Quantity recorded in the system'),
    )

    physical_quantity = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        verbose_name=_('Physical Quantity'),
        help_text=_('Quantity counted physically'),
    )

    variance = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        verbose_name=_('Variance'),
        help_text=_('Difference between physical and system counts'),
    )

    variance_percentage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Variance Percentage'),
    )

    discrepancy_type = models.CharField(
        max_length=30,
        choices=DiscrepancyType.choices,
        null=True,
        blank=True,
        verbose_name=_('Discrepancy Type'),
    )

    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Notes'),
    )

    counted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='counted_reconciliation_items',
        verbose_name=_('Counted By'),
    )

    counted_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Counted At'),
    )

    def save(self, *args, **kwargs):
        self.variance = self.physical_quantity - self.system_quantity
        if self.system_quantity != 0:
            self.variance_percentage = (self.variance / self.system_quantity) * 100
        else:
            self.variance_percentage = None
        if self.variance != 0 and not self.discrepancy_type:
            if self.variance < 0:
                self.discrepancy_type = DiscrepancyType.SHORTAGE
            else:
                self.discrepancy_type = DiscrepancyType.OVERAGE
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.part.name}: System={self.system_quantity}, Physical={self.physical_quantity}"
