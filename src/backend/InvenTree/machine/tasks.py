"""Background tasks for the machine app telemetry processing."""

from datetime import timedelta

from django.core.exceptions import AppRegistryNotReady
from django.db.models import Avg
from django.utils import timezone

import structlog
from opentelemetry import trace

from InvenTree.tasks import ScheduledTask, offload_task, scheduled_task

logger = structlog.get_logger('inventree')
tracer = trace.get_tracer(__name__)


def process_telemetry_alerts(telemetry_id: int):
    """Process a single telemetry data point for threshold violations.

    This function is called asynchronously after telemetry data is submitted
    to check if any configured thresholds have been violated.

    Args:
        telemetry_id: The ID of the MachineTelemetry record to process
    """
    try:
        from machine.models import MachineTelemetry, TelemetryAlert, TelemetryThreshold
    except AppRegistryNotReady:
        logger.warning('Could not process telemetry alerts - App registry not ready')
        return

    try:
        telemetry = MachineTelemetry.objects.get(pk=telemetry_id)
    except MachineTelemetry.DoesNotExist:
        logger.warning('Telemetry record %s not found', telemetry_id)
        return

    # Find applicable thresholds for this telemetry
    thresholds = TelemetryThreshold.objects.filter(
        machine_config=telemetry.machine_config,
        metric_type=telemetry.metric_type,
        enabled=True,
    )

    # Also check thresholds that match the specific metric name
    if telemetry.metric_name:
        thresholds = thresholds.filter(
            metric_name__in=['', telemetry.metric_name]
        )

    for threshold in thresholds:
        is_violation, alert_type, severity = threshold.check_value(telemetry.value)

        if is_violation and alert_type and severity:
            # Check if a similar alert already exists recently (within 1 hour)
            recent_alert = TelemetryAlert.objects.filter(
                machine_config=telemetry.machine_config,
                alert_type=alert_type,
                metric_type=telemetry.metric_type,
                metric_name=telemetry.metric_name,
                created__gte=timezone.now() - timedelta(hours=1),
            ).first()

            if recent_alert:
                # Update existing alert with new values
                recent_alert.actual_value = telemetry.value
                recent_alert.telemetry_data = telemetry
                recent_alert.save()
                logger.info(
                    'Updated existing alert %s for machine %s',
                    recent_alert.pk,
                    telemetry.machine_config.name,
                )
            else:
                # Create new alert
                message = _generate_alert_message(
                    telemetry, threshold, alert_type, severity
                )

                alert = TelemetryAlert.objects.create(
                    machine_config=telemetry.machine_config,
                    alert_type=alert_type,
                    severity=severity,
                    metric_type=telemetry.metric_type,
                    metric_name=telemetry.metric_name,
                    message=message,
                    threshold_value=_get_threshold_value(threshold, alert_type),
                    actual_value=telemetry.value,
                    telemetry_data=telemetry,
                )

                logger.info(
                    'Created alert %s for machine %s: %s',
                    alert.pk,
                    telemetry.machine_config.name,
                    message,
                )

                # Trigger notification for critical alerts
                if severity in [
                    TelemetryAlert.AlertSeverity.CRITICAL,
                    TelemetryAlert.AlertSeverity.EMERGENCY,
                ]:
                    _trigger_alert_notification(alert)


def _generate_alert_message(telemetry, threshold, alert_type, severity):
    """Generate a human-readable alert message.

    Args:
        telemetry: The MachineTelemetry record
        threshold: The TelemetryThreshold that was violated
        alert_type: The type of alert
        severity: The severity level

    Returns:
        str: The alert message
    """
    from machine.models import TelemetryAlert

    metric_display = telemetry.metric_name or telemetry.get_metric_type_display()
    unit = f' {telemetry.unit}' if telemetry.unit else ''

    if alert_type == TelemetryAlert.AlertType.THRESHOLD_HIGH:
        threshold_val = threshold.max_value if severity == TelemetryAlert.AlertSeverity.CRITICAL else threshold.warning_max
        return (
            f'{metric_display} value ({telemetry.value}{unit}) exceeded '
            f'{"critical" if severity == TelemetryAlert.AlertSeverity.CRITICAL else "warning"} '
            f'threshold ({threshold_val}{unit})'
        )
    elif alert_type == TelemetryAlert.AlertType.THRESHOLD_LOW:
        threshold_val = threshold.min_value if severity == TelemetryAlert.AlertSeverity.CRITICAL else threshold.warning_min
        return (
            f'{metric_display} value ({telemetry.value}{unit}) fell below '
            f'{"critical" if severity == TelemetryAlert.AlertSeverity.CRITICAL else "warning"} '
            f'threshold ({threshold_val}{unit})'
        )

    return f'{metric_display} anomaly detected: value={telemetry.value}{unit}'


def _get_threshold_value(threshold, alert_type):
    """Get the threshold value that was violated.

    Args:
        threshold: The TelemetryThreshold
        alert_type: The type of alert

    Returns:
        float: The threshold value
    """
    from machine.models import TelemetryAlert

    if alert_type == TelemetryAlert.AlertType.THRESHOLD_HIGH:
        return threshold.max_value or threshold.warning_max
    elif alert_type == TelemetryAlert.AlertType.THRESHOLD_LOW:
        return threshold.min_value or threshold.warning_min
    return None


def _trigger_alert_notification(alert):
    """Trigger a notification for a critical alert.

    Args:
        alert: The TelemetryAlert record
    """
    try:
        from common.notifications import NotificationBody, trigger_notification
    except AppRegistryNotReady:
        logger.warning('Could not trigger notification - App registry not ready')
        return

    notification_body = NotificationBody(
        name=f'Machine Alert: {alert.machine_config.name}',
        slug='machine.telemetry_alert',
        message=alert.message,
        template='email/telemetry_alert.html',
    )

    # Get responsible users for the machine (if any)
    # For now, we'll just log the notification
    logger.info(
        'Notification triggered for alert %s: %s',
        alert.pk,
        alert.message,
    )


def offload_telemetry_processing(telemetry_id: int):
    """Offload telemetry processing to background worker.

    Args:
        telemetry_id: The ID of the MachineTelemetry record to process
    """
    offload_task(
        'machine.tasks.process_telemetry_alerts',
        telemetry_id,
        group='machine_telemetry',
    )


@tracer.start_as_current_span('check_missing_telemetry')
@scheduled_task(ScheduledTask.HOURLY)
def check_missing_telemetry():
    """Check for machines that haven't reported telemetry recently.

    This scheduled task runs hourly to detect machines that may have
    stopped reporting telemetry data, which could indicate a connectivity
    or equipment issue.
    """
    try:
        from machine.models import MachineConfig, MachineTelemetry, TelemetryAlert
    except AppRegistryNotReady:
        logger.warning('Could not check missing telemetry - App registry not ready')
        return

    # Check for active machines that haven't reported in the last hour
    threshold_time = timezone.now() - timedelta(hours=1)

    active_machines = MachineConfig.objects.filter(active=True)

    for machine in active_machines:
        # Check if this machine has any telemetry data
        has_telemetry = MachineTelemetry.objects.filter(
            machine_config=machine
        ).exists()

        if not has_telemetry:
            # Machine has never reported telemetry, skip
            continue

        # Check for recent telemetry
        recent_telemetry = MachineTelemetry.objects.filter(
            machine_config=machine,
            timestamp__gte=threshold_time,
        ).exists()

        if not recent_telemetry:
            # Check if we already have a recent missing data alert
            recent_alert = TelemetryAlert.objects.filter(
                machine_config=machine,
                alert_type=TelemetryAlert.AlertType.MISSING_DATA,
                created__gte=threshold_time,
            ).exists()

            if not recent_alert:
                # Create missing data alert
                TelemetryAlert.objects.create(
                    machine_config=machine,
                    alert_type=TelemetryAlert.AlertType.MISSING_DATA,
                    severity=TelemetryAlert.AlertSeverity.WARNING,
                    message=f'Machine {machine.name} has not reported telemetry data in the last hour',
                )

                logger.warning(
                    'Machine %s has not reported telemetry in the last hour',
                    machine.name,
                )


@tracer.start_as_current_span('cleanup_old_telemetry')
@scheduled_task(ScheduledTask.DAILY)
def cleanup_old_telemetry():
    """Clean up old telemetry data to prevent database bloat.

    This scheduled task runs daily to remove telemetry data older than
    the configured retention period (default: 90 days).
    """
    try:
        from common.settings import get_global_setting

        from machine.models import MachineTelemetry
    except AppRegistryNotReady:
        logger.warning('Could not cleanup old telemetry - App registry not ready')
        return

    # Get retention period from settings (default: 90 days)
    retention_days = get_global_setting('MACHINE_TELEMETRY_RETENTION_DAYS', 90)

    try:
        retention_days = int(retention_days)
    except (ValueError, TypeError):
        retention_days = 90

    if retention_days <= 0:
        logger.info('Telemetry retention disabled (retention_days=%s)', retention_days)
        return

    threshold_date = timezone.now() - timedelta(days=retention_days)

    # Delete old telemetry records
    deleted_count, _ = MachineTelemetry.objects.filter(
        timestamp__lt=threshold_date
    ).delete()

    if deleted_count > 0:
        logger.info(
            'Deleted %s telemetry records older than %s days',
            deleted_count,
            retention_days,
        )


@tracer.start_as_current_span('cleanup_old_alerts')
@scheduled_task(ScheduledTask.DAILY)
def cleanup_old_alerts():
    """Clean up old acknowledged alerts.

    This scheduled task runs daily to remove acknowledged alerts older than
    the configured retention period (default: 30 days).
    """
    try:
        from common.settings import get_global_setting

        from machine.models import TelemetryAlert
    except AppRegistryNotReady:
        logger.warning('Could not cleanup old alerts - App registry not ready')
        return

    # Get retention period from settings (default: 30 days)
    retention_days = get_global_setting('MACHINE_ALERT_RETENTION_DAYS', 30)

    try:
        retention_days = int(retention_days)
    except (ValueError, TypeError):
        retention_days = 30

    if retention_days <= 0:
        logger.info('Alert retention disabled (retention_days=%s)', retention_days)
        return

    threshold_date = timezone.now() - timedelta(days=retention_days)

    # Delete old acknowledged alerts
    deleted_count, _ = TelemetryAlert.objects.filter(
        acknowledged=True,
        created__lt=threshold_date,
    ).delete()

    if deleted_count > 0:
        logger.info(
            'Deleted %s acknowledged alerts older than %s days',
            deleted_count,
            retention_days,
        )


@tracer.start_as_current_span('process_rate_of_change_alerts')
@scheduled_task(ScheduledTask.MINUTES, 5)
def process_rate_of_change_alerts():
    """Process rate of change alerts for telemetry data.

    This scheduled task runs every 5 minutes to check for abnormal
    rates of change in telemetry data.
    """
    try:
        from machine.models import (
            MachineConfig,
            MachineTelemetry,
            TelemetryAlert,
            TelemetryThreshold,
        )
    except AppRegistryNotReady:
        logger.warning('Could not process rate of change alerts - App registry not ready')
        return

    # Get thresholds with rate of change configured
    thresholds = TelemetryThreshold.objects.filter(
        enabled=True,
        rate_of_change_threshold__isnull=False,
    )

    now = timezone.now()
    five_minutes_ago = now - timedelta(minutes=5)

    for threshold in thresholds:
        # Get recent telemetry for this threshold's machine and metric
        recent_telemetry = MachineTelemetry.objects.filter(
            machine_config=threshold.machine_config,
            metric_type=threshold.metric_type,
            timestamp__gte=five_minutes_ago,
        ).order_by('timestamp')

        if threshold.metric_name:
            recent_telemetry = recent_telemetry.filter(
                metric_name=threshold.metric_name
            )

        telemetry_list = list(recent_telemetry)

        if len(telemetry_list) < 2:
            continue

        # Calculate rate of change between consecutive readings
        for i in range(1, len(telemetry_list)):
            prev = telemetry_list[i - 1]
            curr = telemetry_list[i]

            time_diff_minutes = (curr.timestamp - prev.timestamp).total_seconds() / 60

            if time_diff_minutes <= 0:
                continue

            rate_of_change = abs(curr.value - prev.value) / time_diff_minutes

            if rate_of_change > threshold.rate_of_change_threshold:
                # Check for recent rate of change alert
                recent_alert = TelemetryAlert.objects.filter(
                    machine_config=threshold.machine_config,
                    alert_type=TelemetryAlert.AlertType.RATE_OF_CHANGE,
                    metric_type=threshold.metric_type,
                    created__gte=five_minutes_ago,
                ).exists()

                if not recent_alert:
                    metric_display = curr.metric_name or curr.get_metric_type_display()
                    unit = f' {curr.unit}' if curr.unit else ''

                    TelemetryAlert.objects.create(
                        machine_config=threshold.machine_config,
                        alert_type=TelemetryAlert.AlertType.RATE_OF_CHANGE,
                        severity=TelemetryAlert.AlertSeverity.WARNING,
                        metric_type=threshold.metric_type,
                        metric_name=curr.metric_name,
                        message=(
                            f'{metric_display} rate of change ({rate_of_change:.2f}{unit}/min) '
                            f'exceeded threshold ({threshold.rate_of_change_threshold}{unit}/min)'
                        ),
                        threshold_value=threshold.rate_of_change_threshold,
                        actual_value=rate_of_change,
                        telemetry_data=curr,
                    )

                    logger.warning(
                        'Rate of change alert for machine %s: %s',
                        threshold.machine_config.name,
                        metric_display,
                    )
                break  # Only create one alert per threshold per run
