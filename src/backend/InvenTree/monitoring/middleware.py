"""Django middleware for application performance monitoring.

This module provides middleware for tracking request/response metrics,
timing, and error rates.
"""

import time
from typing import Callable

from django.http import HttpRequest, HttpResponse

import structlog

from monitoring.metrics import get_registry

logger = structlog.get_logger(__name__)


class PerformanceMonitoringMiddleware:
    """Middleware for monitoring HTTP request performance.

    This middleware tracks request duration, status codes, and error rates
    for all incoming HTTP requests.

    Example:
        # In settings.py MIDDLEWARE list:
        MIDDLEWARE = [
            'monitoring.middleware.PerformanceMonitoringMiddleware',
            # ... other middleware
        ]
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain
        """
        self.get_response = get_response
        self.registry = get_registry()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request and track metrics.

        Args:
            request: The incoming HTTP request

        Returns:
            The HTTP response
        """
        start_time = time.perf_counter()

        endpoint = self._get_endpoint(request)
        method = request.method

        try:
            response = self.get_response(request)
            status_code = str(response.status_code)
            error = status_code.startswith(('4', '5'))
        except Exception as e:
            status_code = '500'
            error = True
            logger.error(
                'request_exception', method=method, endpoint=endpoint, error=str(e)
            )
            raise

        finally:
            duration = time.perf_counter() - start_time

            self.registry.increment(
                'http_requests_total',
                labels={'method': method, 'endpoint': endpoint, 'status': status_code},
            )

            self.registry.observe_histogram(
                'http_request_duration_seconds',
                duration,
                labels={'method': method, 'endpoint': endpoint},
            )

            if error:
                self.registry.increment(
                    'api_errors_total',
                    labels={'endpoint': endpoint, 'error_type': status_code},
                )

            logger.info(
                'request_completed',
                method=method,
                endpoint=endpoint,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
            )

        return response

    def _get_endpoint(self, request: HttpRequest) -> str:
        """Get a normalized endpoint path for the request.

        Args:
            request: The HTTP request

        Returns:
            Normalized endpoint path
        """
        path = request.path

        if hasattr(request, 'resolver_match') and request.resolver_match:
            route = request.resolver_match.route
            if route:
                return '/' + route.lstrip('/')

        return path


class RequestLoggingMiddleware:
    """Middleware for detailed request logging.

    This middleware logs detailed information about each request
    including headers, user info, and timing.

    Example:
        # In settings.py MIDDLEWARE list:
        MIDDLEWARE = [
            'monitoring.middleware.RequestLoggingMiddleware',
            # ... other middleware
        ]
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request and log details.

        Args:
            request: The incoming HTTP request

        Returns:
            The HTTP response
        """
        request_id = self._get_request_id(request)
        start_time = time.perf_counter()

        logger.info(
            'request_started',
            request_id=request_id,
            method=request.method,
            path=request.path,
            user=self._get_user_info(request),
            ip=self._get_client_ip(request),
        )

        response = self.get_response(request)

        duration = time.perf_counter() - start_time

        logger.info(
            'request_finished',
            request_id=request_id,
            method=request.method,
            path=request.path,
            status=response.status_code,
            duration_ms=round(duration * 1000, 2),
            content_length=response.get('Content-Length', 0),
        )

        response['X-Request-ID'] = request_id

        return response

    def _get_request_id(self, request: HttpRequest) -> str:
        """Get or generate a request ID.

        Args:
            request: The HTTP request

        Returns:
            Request ID string
        """
        request_id = request.headers.get('X-Request-ID')
        if not request_id:
            import uuid

            request_id = str(uuid.uuid4())
        return request_id

    def _get_user_info(self, request: HttpRequest) -> str:
        """Get user information from the request.

        Args:
            request: The HTTP request

        Returns:
            User identifier or 'anonymous'
        """
        if hasattr(request, 'user') and request.user.is_authenticated:
            return str(request.user.username)
        return 'anonymous'

    def _get_client_ip(self, request: HttpRequest) -> str:
        """Get the client IP address.

        Args:
            request: The HTTP request

        Returns:
            Client IP address
        """
        x_forwarded_for = request.headers.get('X-Forwarded-For')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class HealthCheckMiddleware:
    """Middleware for health check endpoints.

    This middleware intercepts requests to health check endpoints
    and returns health status without processing through the full stack.

    Example:
        # In settings.py MIDDLEWARE list:
        MIDDLEWARE = [
            'monitoring.middleware.HealthCheckMiddleware',
            # ... other middleware
        ]
    """

    HEALTH_PATHS = ['/health', '/health/', '/healthz', '/healthz/']
    READY_PATHS = ['/ready', '/ready/', '/readyz', '/readyz/']
    LIVE_PATHS = ['/live', '/live/', '/livez', '/livez/']

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request.

        Args:
            request: The incoming HTTP request

        Returns:
            The HTTP response
        """
        path = request.path

        if path in self.HEALTH_PATHS:
            return self._health_response()

        if path in self.READY_PATHS:
            return self._readiness_response()

        if path in self.LIVE_PATHS:
            return self._liveness_response()

        return self.get_response(request)

    def _health_response(self) -> HttpResponse:
        """Generate a full health check response.

        Returns:
            HTTP response with health status
        """
        import json

        from monitoring.health import get_system_health

        health = get_system_health()
        status_code = 200 if health.status.value == 'healthy' else 503

        return HttpResponse(
            json.dumps(health.to_dict()),
            content_type='application/json',
            status=status_code,
        )

    def _readiness_response(self) -> HttpResponse:
        """Generate a readiness check response.

        Returns:
            HTTP response indicating readiness
        """
        import json

        from monitoring.health import check_database_health

        db_health = check_database_health()
        is_ready = db_health.status.value == 'healthy'

        return HttpResponse(
            json.dumps({'ready': is_ready, 'database': db_health.status.value}),
            content_type='application/json',
            status=200 if is_ready else 503,
        )

    def _liveness_response(self) -> HttpResponse:
        """Generate a liveness check response.

        Returns:
            HTTP response indicating liveness
        """
        import json

        return HttpResponse(
            json.dumps({'alive': True}), content_type='application/json', status=200
        )
