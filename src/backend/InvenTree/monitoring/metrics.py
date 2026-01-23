"""Metrics collection and tracking for application performance monitoring.

This module provides utilities for collecting and tracking application metrics
including response times, resource utilization, and custom business metrics.
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MetricValue:
    """Represents a single metric value with timestamp."""

    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class MetricDefinition:
    """Definition of a metric to be collected."""

    name: str
    description: str
    metric_type: str  # 'counter', 'gauge', 'histogram', 'summary'
    unit: str = ''
    labels: list[str] = field(default_factory=list)


class MetricsRegistry:
    """Registry for managing metric definitions and values.

    This class provides a central registry for defining and collecting metrics.
    It supports counters, gauges, histograms, and summaries.

    Example:
        registry = MetricsRegistry()
        registry.register_metric(MetricDefinition(
            name='http_requests_total',
            description='Total HTTP requests',
            metric_type='counter',
            labels=['method', 'endpoint', 'status']
        ))
        registry.increment('http_requests_total', labels={'method': 'GET', 'endpoint': '/api/parts', 'status': '200'})
    """

    def __init__(self):
        """Initialize the metrics registry."""
        self._metrics: dict[str, MetricDefinition] = {}
        self._values: dict[str, list[MetricValue]] = defaultdict(list)
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def register_metric(self, metric: MetricDefinition) -> None:
        """Register a new metric definition.

        Args:
            metric: The metric definition to register
        """
        with self._lock:
            self._metrics[metric.name] = metric
            logger.info('metric_registered', name=metric.name, type=metric.metric_type)

    def get_metric(self, name: str) -> MetricDefinition | None:
        """Get a metric definition by name.

        Args:
            name: The metric name

        Returns:
            MetricDefinition or None if not found
        """
        return self._metrics.get(name)

    def list_metrics(self) -> list[MetricDefinition]:
        """List all registered metrics.

        Returns:
            List of all metric definitions
        """
        return list(self._metrics.values())

    def increment(
        self, name: str, value: float = 1.0, labels: dict[str, str] | None = None
    ) -> None:
        """Increment a counter metric.

        Args:
            name: The metric name
            value: The value to increment by (default 1.0)
            labels: Optional labels for the metric
        """
        with self._lock:
            key = self._make_key(name, labels)
            self._counters[key] += value
            self._values[name].append(
                MetricValue(value=self._counters[key], labels=labels or {})
            )

    def set_gauge(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Set a gauge metric value.

        Args:
            name: The metric name
            value: The gauge value
            labels: Optional labels for the metric
        """
        with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = value
            self._values[name].append(MetricValue(value=value, labels=labels or {}))

    def observe_histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Observe a value for a histogram metric.

        Args:
            name: The metric name
            value: The observed value
            labels: Optional labels for the metric
        """
        with self._lock:
            key = self._make_key(name, labels)
            self._histograms[key].append(value)
            self._values[name].append(MetricValue(value=value, labels=labels or {}))

    def get_counter_value(
        self, name: str, labels: dict[str, str] | None = None
    ) -> float:
        """Get the current value of a counter.

        Args:
            name: The metric name
            labels: Optional labels for the metric

        Returns:
            The current counter value
        """
        key = self._make_key(name, labels)
        return self._counters.get(key, 0.0)

    def get_gauge_value(
        self, name: str, labels: dict[str, str] | None = None
    ) -> float | None:
        """Get the current value of a gauge.

        Args:
            name: The metric name
            labels: Optional labels for the metric

        Returns:
            The current gauge value or None if not set
        """
        key = self._make_key(name, labels)
        return self._gauges.get(key)

    def get_histogram_stats(
        self, name: str, labels: dict[str, str] | None = None
    ) -> dict[str, float]:
        """Get statistics for a histogram metric.

        Args:
            name: The metric name
            labels: Optional labels for the metric

        Returns:
            Dictionary with count, sum, min, max, avg statistics
        """
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])

        if not values:
            return {'count': 0, 'sum': 0, 'min': 0, 'max': 0, 'avg': 0}

        return {
            'count': len(values),
            'sum': sum(values),
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values),
        }

    def export_metrics(self) -> dict[str, Any]:
        """Export all metrics in a structured format.

        Returns:
            Dictionary with all metric values
        """
        with self._lock:
            return {
                'counters': dict(self._counters),
                'gauges': dict(self._gauges),
                'histograms': {
                    k: self.get_histogram_stats(k) for k in self._histograms
                },
                'exported_at': datetime.now().isoformat(),
            }

    def reset(self) -> None:
        """Reset all metric values."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._values.clear()

    def _make_key(self, name: str, labels: dict[str, str] | None) -> str:
        """Create a unique key for a metric with labels.

        Args:
            name: The metric name
            labels: Optional labels

        Returns:
            A unique string key
        """
        if not labels:
            return name
        label_str = ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
        return f'{name}{{{label_str}}}'


# Global metrics registry instance
_registry = MetricsRegistry()


def get_registry() -> MetricsRegistry:
    """Get the global metrics registry.

    Returns:
        The global MetricsRegistry instance
    """
    return _registry


class Timer:
    """Context manager for timing code execution.

    Example:
        with Timer('api_request_duration', labels={'endpoint': '/api/parts'}):
            # Code to time
            pass
    """

    def __init__(
        self,
        metric_name: str,
        labels: dict[str, str] | None = None,
        registry: MetricsRegistry | None = None,
    ):
        """Initialize the timer.

        Args:
            metric_name: Name of the histogram metric to record
            labels: Optional labels for the metric
            registry: Optional registry (uses global if not provided)
        """
        self.metric_name = metric_name
        self.labels = labels
        self.registry = registry or get_registry()
        self.start_time: float | None = None
        self.duration: float | None = None

    def __enter__(self) -> 'Timer':
        """Start the timer."""
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop the timer and record the duration."""
        if self.start_time is not None:
            self.duration = time.perf_counter() - self.start_time
            self.registry.observe_histogram(
                self.metric_name, self.duration, self.labels
            )


def timed(
    metric_name: str, labels_func: Callable[..., dict[str, str]] | None = None
) -> Callable:
    """Decorator for timing function execution.

    Args:
        metric_name: Name of the histogram metric to record
        labels_func: Optional function to generate labels from function args

    Returns:
        Decorated function

    Example:
        @timed('function_duration', labels_func=lambda x: {'arg': str(x)})
        def my_function(x):
            pass
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            labels = labels_func(*args, **kwargs) if labels_func else None
            with Timer(metric_name, labels):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def register_default_metrics() -> None:
    """Register default application metrics."""
    registry = get_registry()

    default_metrics = [
        MetricDefinition(
            name='http_requests_total',
            description='Total number of HTTP requests',
            metric_type='counter',
            labels=['method', 'endpoint', 'status'],
        ),
        MetricDefinition(
            name='http_request_duration_seconds',
            description='HTTP request duration in seconds',
            metric_type='histogram',
            unit='seconds',
            labels=['method', 'endpoint'],
        ),
        MetricDefinition(
            name='active_users',
            description='Number of currently active users',
            metric_type='gauge',
        ),
        MetricDefinition(
            name='database_query_duration_seconds',
            description='Database query duration in seconds',
            metric_type='histogram',
            unit='seconds',
            labels=['query_type', 'table'],
        ),
        MetricDefinition(
            name='build_orders_active',
            description='Number of active build orders',
            metric_type='gauge',
        ),
        MetricDefinition(
            name='build_orders_completed_total',
            description='Total number of completed build orders',
            metric_type='counter',
        ),
        MetricDefinition(
            name='inventory_items_total',
            description='Total number of inventory items',
            metric_type='gauge',
            labels=['category'],
        ),
        MetricDefinition(
            name='stock_movements_total',
            description='Total number of stock movements',
            metric_type='counter',
            labels=['movement_type'],
        ),
        MetricDefinition(
            name='api_errors_total',
            description='Total number of API errors',
            metric_type='counter',
            labels=['endpoint', 'error_type'],
        ),
        MetricDefinition(
            name='background_task_duration_seconds',
            description='Background task execution duration',
            metric_type='histogram',
            unit='seconds',
            labels=['task_name'],
        ),
    ]

    for metric in default_metrics:
        registry.register_metric(metric)

    logger.info('default_metrics_registered', count=len(default_metrics))
