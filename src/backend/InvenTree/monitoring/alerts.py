"""Alert and notification system for monitoring.

This module provides alert management capabilities including threshold-based
alerts, notification channels, and alert history tracking.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


class AlertStatus(Enum):
    """Alert status."""

    ACTIVE = 'active'
    ACKNOWLEDGED = 'acknowledged'
    RESOLVED = 'resolved'


@dataclass
class AlertRule:
    """Definition of an alert rule.

    Attributes:
        rule_id: Unique identifier for the rule
        name: Human-readable name
        description: Description of what the rule monitors
        metric_name: Name of the metric to monitor
        condition: Condition type ('gt', 'lt', 'eq', 'gte', 'lte')
        threshold: Threshold value for the condition
        severity: Alert severity when triggered
        cooldown_seconds: Minimum time between alerts (default 300)
        enabled: Whether the rule is active
    """

    rule_id: str
    name: str
    description: str
    metric_name: str
    condition: str
    threshold: float
    severity: AlertSeverity = AlertSeverity.WARNING
    cooldown_seconds: int = 300
    enabled: bool = True
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class Alert:
    """Represents an active or historical alert.

    Attributes:
        alert_id: Unique identifier for the alert
        rule_id: ID of the rule that triggered the alert
        name: Alert name (from rule)
        message: Alert message
        severity: Alert severity
        status: Current alert status
        metric_value: The metric value that triggered the alert
        threshold: The threshold that was breached
        triggered_at: When the alert was triggered
        acknowledged_at: When the alert was acknowledged (if applicable)
        resolved_at: When the alert was resolved (if applicable)
        labels: Additional labels/metadata
    """

    alert_id: str
    rule_id: str
    name: str
    message: str
    severity: AlertSeverity
    status: AlertStatus
    metric_value: float
    threshold: float
    triggered_at: datetime = field(default_factory=datetime.now)
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary format.

        Returns:
            Dictionary representation of the alert
        """
        return {
            'alert_id': self.alert_id,
            'rule_id': self.rule_id,
            'name': self.name,
            'message': self.message,
            'severity': self.severity.value,
            'status': self.status.value,
            'metric_value': self.metric_value,
            'threshold': self.threshold,
            'triggered_at': self.triggered_at.isoformat(),
            'acknowledged_at': (
                self.acknowledged_at.isoformat() if self.acknowledged_at else None
            ),
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'labels': self.labels,
        }


class NotificationChannel:
    """Base class for notification channels."""

    def __init__(self, name: str, enabled: bool = True):
        """Initialize the notification channel.

        Args:
            name: Channel name
            enabled: Whether the channel is enabled
        """
        self.name = name
        self.enabled = enabled

    def send(self, alert: Alert) -> bool:
        """Send an alert notification.

        Args:
            alert: The alert to send

        Returns:
            True if notification was sent successfully
        """
        raise NotImplementedError


class LogNotificationChannel(NotificationChannel):
    """Notification channel that logs alerts."""

    def __init__(self, name: str = 'log', enabled: bool = True):
        """Initialize the log notification channel."""
        super().__init__(name, enabled)

    def send(self, alert: Alert) -> bool:
        """Log the alert.

        Args:
            alert: The alert to log

        Returns:
            True (always succeeds)
        """
        if not self.enabled:
            return False

        log_method = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.ERROR: logger.error,
            AlertSeverity.CRITICAL: logger.critical,
        }.get(alert.severity, logger.warning)

        log_method(
            'alert_notification',
            alert_id=alert.alert_id,
            name=alert.name,
            message=alert.message,
            severity=alert.severity.value,
            metric_value=alert.metric_value,
            threshold=alert.threshold,
        )
        return True


class WebhookNotificationChannel(NotificationChannel):
    """Notification channel that sends alerts via webhook."""

    def __init__(
        self,
        name: str,
        webhook_url: str,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
    ):
        """Initialize the webhook notification channel.

        Args:
            name: Channel name
            webhook_url: URL to send webhook requests to
            headers: Optional HTTP headers
            enabled: Whether the channel is enabled
        """
        super().__init__(name, enabled)
        self.webhook_url = webhook_url
        self.headers = headers or {}

    def send(self, alert: Alert) -> bool:
        """Send alert via webhook.

        Args:
            alert: The alert to send

        Returns:
            True if webhook was sent successfully
        """
        if not self.enabled:
            return False

        try:
            import json
            import urllib.request

            payload = json.dumps(alert.to_dict()).encode('utf-8')
            headers = {'Content-Type': 'application/json', **self.headers}

            request = urllib.request.Request(
                self.webhook_url, data=payload, headers=headers, method='POST'
            )

            with urllib.request.urlopen(request, timeout=10) as response:
                success = response.status == 200

            logger.info(
                'webhook_notification_sent',
                channel=self.name,
                alert_id=alert.alert_id,
                success=success,
            )
            return success

        except Exception as e:
            logger.error(
                'webhook_notification_failed',
                channel=self.name,
                alert_id=alert.alert_id,
                error=str(e),
            )
            return False


class AlertManager:
    """Manager for alert rules, active alerts, and notifications.

    This class handles alert rule evaluation, alert lifecycle management,
    and notification dispatch.

    Example:
        manager = AlertManager()
        manager.add_rule(AlertRule(
            rule_id='high_cpu',
            name='High CPU Usage',
            description='CPU usage exceeds 90%',
            metric_name='cpu_usage_percent',
            condition='gt',
            threshold=90,
            severity=AlertSeverity.WARNING
        ))
        manager.evaluate_metric('cpu_usage_percent', 95)
    """

    def __init__(self):
        """Initialize the alert manager."""
        self._rules: dict[str, AlertRule] = {}
        self._active_alerts: dict[str, Alert] = {}
        self._alert_history: list[Alert] = []
        self._channels: list[NotificationChannel] = []
        self._last_alert_times: dict[str, datetime] = {}

        self._channels.append(LogNotificationChannel())

    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule.

        Args:
            rule: The alert rule to add
        """
        self._rules[rule.rule_id] = rule
        logger.info('alert_rule_added', rule_id=rule.rule_id, name=rule.name)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove an alert rule.

        Args:
            rule_id: ID of the rule to remove

        Returns:
            True if the rule was removed
        """
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def get_rule(self, rule_id: str) -> AlertRule | None:
        """Get an alert rule by ID.

        Args:
            rule_id: The rule ID

        Returns:
            AlertRule or None if not found
        """
        return self._rules.get(rule_id)

    def list_rules(self) -> list[AlertRule]:
        """List all alert rules.

        Returns:
            List of all alert rules
        """
        return list(self._rules.values())

    def add_channel(self, channel: NotificationChannel) -> None:
        """Add a notification channel.

        Args:
            channel: The notification channel to add
        """
        self._channels.append(channel)
        logger.info('notification_channel_added', channel=channel.name)

    def evaluate_metric(
        self, metric_name: str, value: float, labels: dict[str, str] | None = None
    ) -> list[Alert]:
        """Evaluate a metric value against all applicable rules.

        Args:
            metric_name: Name of the metric
            value: Current metric value
            labels: Optional labels for the metric

        Returns:
            List of alerts that were triggered
        """
        triggered_alerts = []

        for rule in self._rules.values():
            if not rule.enabled or rule.metric_name != metric_name:
                continue

            if labels and rule.labels:
                if not all(labels.get(k) == v for k, v in rule.labels.items()):
                    continue

            if self._check_condition(value, rule.condition, rule.threshold):
                if self._is_in_cooldown(rule.rule_id, rule.cooldown_seconds):
                    continue

                alert = self._create_alert(rule, value, labels)
                triggered_alerts.append(alert)
                self._notify(alert)

        return triggered_alerts

    def acknowledge_alert(self, alert_id: str, user: str | None = None) -> bool:
        """Acknowledge an active alert.

        Args:
            alert_id: ID of the alert to acknowledge
            user: Optional user who acknowledged the alert

        Returns:
            True if the alert was acknowledged
        """
        alert = self._active_alerts.get(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now()

        logger.info('alert_acknowledged', alert_id=alert_id, user=user, name=alert.name)
        return True

    def resolve_alert(self, alert_id: str, user: str | None = None) -> bool:
        """Resolve an active alert.

        Args:
            alert_id: ID of the alert to resolve
            user: Optional user who resolved the alert

        Returns:
            True if the alert was resolved
        """
        alert = self._active_alerts.get(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now()

        del self._active_alerts[alert_id]
        self._alert_history.append(alert)

        logger.info('alert_resolved', alert_id=alert_id, user=user, name=alert.name)
        return True

    def get_active_alerts(self, severity: AlertSeverity | None = None) -> list[Alert]:
        """Get all active alerts.

        Args:
            severity: Optional filter by severity

        Returns:
            List of active alerts
        """
        alerts = list(self._active_alerts.values())
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts

    def get_alert_history(
        self, limit: int = 100, rule_id: str | None = None
    ) -> list[Alert]:
        """Get alert history.

        Args:
            limit: Maximum number of alerts to return
            rule_id: Optional filter by rule ID

        Returns:
            List of historical alerts
        """
        alerts = self._alert_history
        if rule_id:
            alerts = [a for a in alerts if a.rule_id == rule_id]
        return alerts[-limit:]

    def _check_condition(self, value: float, condition: str, threshold: float) -> bool:
        """Check if a value meets a condition.

        Args:
            value: The value to check
            condition: The condition type
            threshold: The threshold value

        Returns:
            True if the condition is met
        """
        conditions = {
            'gt': lambda v, t: v > t,
            'lt': lambda v, t: v < t,
            'eq': lambda v, t: v == t,
            'gte': lambda v, t: v >= t,
            'lte': lambda v, t: v <= t,
        }
        check_func = conditions.get(condition)
        if check_func:
            return check_func(value, threshold)
        return False

    def _is_in_cooldown(self, rule_id: str, cooldown_seconds: int) -> bool:
        """Check if a rule is in cooldown period.

        Args:
            rule_id: The rule ID
            cooldown_seconds: Cooldown period in seconds

        Returns:
            True if the rule is in cooldown
        """
        last_time = self._last_alert_times.get(rule_id)
        if not last_time:
            return False

        elapsed = (datetime.now() - last_time).total_seconds()
        return elapsed < cooldown_seconds

    def _create_alert(
        self, rule: AlertRule, value: float, labels: dict[str, str] | None
    ) -> Alert:
        """Create a new alert from a rule.

        Args:
            rule: The alert rule
            value: The metric value that triggered the alert
            labels: Optional labels

        Returns:
            The created Alert
        """
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            rule_id=rule.rule_id,
            name=rule.name,
            message=f'{rule.name}: {rule.metric_name} is {value} (threshold: {rule.threshold})',
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            metric_value=value,
            threshold=rule.threshold,
            labels=labels or {},
        )

        self._active_alerts[alert.alert_id] = alert
        self._last_alert_times[rule.rule_id] = datetime.now()

        logger.info(
            'alert_triggered',
            alert_id=alert.alert_id,
            rule_id=rule.rule_id,
            name=rule.name,
            value=value,
            threshold=rule.threshold,
        )

        return alert

    def _notify(self, alert: Alert) -> None:
        """Send notifications for an alert.

        Args:
            alert: The alert to notify about
        """
        for channel in self._channels:
            try:
                channel.send(alert)
            except Exception as e:
                logger.error(
                    'notification_failed',
                    channel=channel.name,
                    alert_id=alert.alert_id,
                    error=str(e),
                )


# Global alert manager instance
_alert_manager = AlertManager()


def get_alert_manager() -> AlertManager:
    """Get the global alert manager instance.

    Returns:
        The global AlertManager instance
    """
    return _alert_manager


def register_default_alert_rules() -> None:
    """Register default alert rules for common scenarios."""
    manager = get_alert_manager()

    default_rules = [
        AlertRule(
            rule_id='high_memory_usage',
            name='High Memory Usage',
            description='Memory usage exceeds 85%',
            metric_name='memory_usage_percent',
            condition='gt',
            threshold=85,
            severity=AlertSeverity.WARNING,
        ),
        AlertRule(
            rule_id='critical_memory_usage',
            name='Critical Memory Usage',
            description='Memory usage exceeds 95%',
            metric_name='memory_usage_percent',
            condition='gt',
            threshold=95,
            severity=AlertSeverity.CRITICAL,
        ),
        AlertRule(
            rule_id='low_disk_space',
            name='Low Disk Space',
            description='Disk space below 15%',
            metric_name='disk_free_percent',
            condition='lt',
            threshold=15,
            severity=AlertSeverity.WARNING,
        ),
        AlertRule(
            rule_id='critical_disk_space',
            name='Critical Disk Space',
            description='Disk space below 5%',
            metric_name='disk_free_percent',
            condition='lt',
            threshold=5,
            severity=AlertSeverity.CRITICAL,
        ),
        AlertRule(
            rule_id='high_api_error_rate',
            name='High API Error Rate',
            description='API error rate exceeds 5%',
            metric_name='api_error_rate_percent',
            condition='gt',
            threshold=5,
            severity=AlertSeverity.WARNING,
        ),
        AlertRule(
            rule_id='slow_response_time',
            name='Slow Response Time',
            description='Average response time exceeds 2 seconds',
            metric_name='avg_response_time_seconds',
            condition='gt',
            threshold=2.0,
            severity=AlertSeverity.WARNING,
        ),
        AlertRule(
            rule_id='build_order_backlog',
            name='Build Order Backlog',
            description='More than 100 pending build orders',
            metric_name='pending_build_orders',
            condition='gt',
            threshold=100,
            severity=AlertSeverity.WARNING,
        ),
        AlertRule(
            rule_id='low_stock_alert',
            name='Low Stock Alert',
            description='Stock level below minimum threshold',
            metric_name='stock_below_minimum_count',
            condition='gt',
            threshold=0,
            severity=AlertSeverity.WARNING,
        ),
    ]

    for rule in default_rules:
        manager.add_rule(rule)

    logger.info('default_alert_rules_registered', count=len(default_rules))
