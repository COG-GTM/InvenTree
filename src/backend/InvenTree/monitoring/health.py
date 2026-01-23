"""Health check endpoints and system health monitoring.

This module provides health check functionality for monitoring system status,
database connectivity, and service dependencies.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from django.db import connection

import structlog

logger = structlog.get_logger(__name__)


class HealthStatus(Enum):
    """Health status enumeration."""

    HEALTHY = 'healthy'
    DEGRADED = 'degraded'
    UNHEALTHY = 'unhealthy'


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    name: str
    status: HealthStatus
    message: str = ''
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SystemHealth:
    """Overall system health status."""

    status: HealthStatus
    checks: list[HealthCheckResult]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format.

        Returns:
            Dictionary representation of system health
        """
        return {
            'status': self.status.value,
            'timestamp': self.timestamp.isoformat(),
            'checks': [
                {
                    'name': check.name,
                    'status': check.status.value,
                    'message': check.message,
                    'duration_ms': check.duration_ms,
                    'details': check.details,
                }
                for check in self.checks
            ],
        }


class HealthChecker:
    """Health checker for monitoring system components.

    This class manages health checks for various system components
    and provides an overall health status.

    Example:
        checker = HealthChecker()
        checker.register_check('database', check_database_health)
        health = checker.run_all_checks()
        print(health.status)
    """

    def __init__(self):
        """Initialize the health checker."""
        self._checks: dict[str, Callable[[], HealthCheckResult]] = {}
        self._register_default_checks()

    def register_check(
        self, name: str, check_func: Callable[[], HealthCheckResult]
    ) -> None:
        """Register a health check.

        Args:
            name: Name of the health check
            check_func: Function that performs the health check
        """
        self._checks[name] = check_func
        logger.info('health_check_registered', name=name)

    def unregister_check(self, name: str) -> bool:
        """Unregister a health check.

        Args:
            name: Name of the health check to remove

        Returns:
            True if the check was removed, False if not found
        """
        if name in self._checks:
            del self._checks[name]
            return True
        return False

    def run_check(self, name: str) -> HealthCheckResult | None:
        """Run a specific health check.

        Args:
            name: Name of the health check to run

        Returns:
            HealthCheckResult or None if check not found
        """
        check_func = self._checks.get(name)
        if not check_func:
            return None

        start_time = time.perf_counter()
        try:
            result = check_func()
            result.duration_ms = (time.perf_counter() - start_time) * 1000
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error('health_check_error', name=name, error=str(e))
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f'Check failed with error: {e!s}',
                duration_ms=duration_ms,
            )

    def run_all_checks(self) -> SystemHealth:
        """Run all registered health checks.

        Returns:
            SystemHealth with overall status and individual check results
        """
        results = []
        for name in self._checks:
            result = self.run_check(name)
            if result:
                results.append(result)

        overall_status = self._determine_overall_status(results)

        logger.info(
            'health_checks_completed',
            overall_status=overall_status.value,
            check_count=len(results),
        )

        return SystemHealth(status=overall_status, checks=results)

    def _determine_overall_status(
        self, results: list[HealthCheckResult]
    ) -> HealthStatus:
        """Determine overall health status from individual check results.

        Args:
            results: List of health check results

        Returns:
            Overall HealthStatus
        """
        if not results:
            return HealthStatus.HEALTHY

        statuses = [r.status for r in results]

        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        if any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def _register_default_checks(self) -> None:
        """Register default health checks."""
        self.register_check('database', check_database_health)
        self.register_check('disk_space', check_disk_space)
        self.register_check('memory', check_memory_usage)


def check_database_health() -> HealthCheckResult:
    """Check database connectivity and health.

    Returns:
        HealthCheckResult for database health
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()

        return HealthCheckResult(
            name='database',
            status=HealthStatus.HEALTHY,
            message='Database connection successful',
            details={'connection_status': 'connected'},
        )
    except Exception as e:
        return HealthCheckResult(
            name='database',
            status=HealthStatus.UNHEALTHY,
            message=f'Database connection failed: {e!s}',
            details={'error': str(e)},
        )


def check_disk_space() -> HealthCheckResult:
    """Check available disk space.

    Returns:
        HealthCheckResult for disk space
    """
    try:
        import shutil

        total, used, free = shutil.disk_usage('/')
        free_percent = (free / total) * 100
        used_percent = (used / total) * 100

        details = {
            'total_gb': round(total / (1024**3), 2),
            'used_gb': round(used / (1024**3), 2),
            'free_gb': round(free / (1024**3), 2),
            'free_percent': round(free_percent, 2),
            'used_percent': round(used_percent, 2),
        }

        if free_percent < 5:
            return HealthCheckResult(
                name='disk_space',
                status=HealthStatus.UNHEALTHY,
                message=f'Critical: Only {free_percent:.1f}% disk space remaining',
                details=details,
            )
        elif free_percent < 15:
            return HealthCheckResult(
                name='disk_space',
                status=HealthStatus.DEGRADED,
                message=f'Warning: Only {free_percent:.1f}% disk space remaining',
                details=details,
            )
        else:
            return HealthCheckResult(
                name='disk_space',
                status=HealthStatus.HEALTHY,
                message=f'Disk space OK: {free_percent:.1f}% free',
                details=details,
            )
    except Exception as e:
        return HealthCheckResult(
            name='disk_space',
            status=HealthStatus.UNHEALTHY,
            message=f'Failed to check disk space: {e!s}',
            details={'error': str(e)},
        )


def check_memory_usage() -> HealthCheckResult:
    """Check system memory usage.

    Returns:
        HealthCheckResult for memory usage
    """
    try:
        with open('/proc/meminfo', encoding='utf-8') as f:
            meminfo = {}
            for line in f:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().split()[0]
                    meminfo[key] = int(value)

        total_kb = meminfo.get('MemTotal', 0)
        available_kb = meminfo.get('MemAvailable', 0)

        if total_kb == 0:
            raise ValueError('Could not read memory information')

        used_kb = total_kb - available_kb
        used_percent = (used_kb / total_kb) * 100
        available_percent = (available_kb / total_kb) * 100

        details = {
            'total_mb': round(total_kb / 1024, 2),
            'used_mb': round(used_kb / 1024, 2),
            'available_mb': round(available_kb / 1024, 2),
            'used_percent': round(used_percent, 2),
            'available_percent': round(available_percent, 2),
        }

        if used_percent > 95:
            return HealthCheckResult(
                name='memory',
                status=HealthStatus.UNHEALTHY,
                message=f'Critical: Memory usage at {used_percent:.1f}%',
                details=details,
            )
        elif used_percent > 85:
            return HealthCheckResult(
                name='memory',
                status=HealthStatus.DEGRADED,
                message=f'Warning: Memory usage at {used_percent:.1f}%',
                details=details,
            )
        else:
            return HealthCheckResult(
                name='memory',
                status=HealthStatus.HEALTHY,
                message=f'Memory OK: {used_percent:.1f}% used',
                details=details,
            )
    except Exception as e:
        return HealthCheckResult(
            name='memory',
            status=HealthStatus.UNHEALTHY,
            message=f'Failed to check memory: {e!s}',
            details={'error': str(e)},
        )


# Global health checker instance
_health_checker = HealthChecker()


def get_health_checker() -> HealthChecker:
    """Get the global health checker instance.

    Returns:
        The global HealthChecker instance
    """
    return _health_checker


def get_system_health() -> SystemHealth:
    """Get current system health status.

    Returns:
        SystemHealth with current status
    """
    return _health_checker.run_all_checks()
