import json
import logging
import sys
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests handled by the service.",
    ("service", "method", "route", "status_code"),
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("service", "method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

access_logger = logging.getLogger("sports_store.access")


class JsonFormatter(logging.Formatter):
    """Render application records as compact, one-line operational JSON."""

    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "service": self.service,
        }
        event = getattr(record, "event", None)
        if event:
            payload["event"] = event
        else:
            payload["message"] = record.getMessage()

        for field in ("method", "route", "status", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _configure_json_logging(service: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.WARNING)

    logging.getLogger(service).setLevel(logging.INFO)
    access_logger.setLevel(logging.INFO)

    for logger_name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(logging.INFO)

    logging.getLogger("uvicorn.access").disabled = True
    for logger_name in ("httpx", "httpcore", "motor", "pymongo"):
        logging.getLogger(logger_name).disabled = True


def _normalized_route(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path_format", None) or getattr(
        route, "path", "__unmatched__"
    )


def configure_observability(app: FastAPI, service: str) -> None:
    _configure_json_logging(service)

    @app.middleware("http")
    async def observe_request(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_seconds = time.perf_counter() - started
            route = _normalized_route(request)
            method = request.method
            HTTP_REQUESTS.labels(
                service=service,
                method=method,
                route=route,
                status_code=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION.labels(
                service=service, method=method, route=route
            ).observe(duration_seconds)
            access_logger.info(
                "http_request",
                extra={
                    "event": "http_request",
                    "method": method,
                    "route": route,
                    "status": status_code,
                    "duration_ms": round(duration_seconds * 1000, 3),
                },
            )

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(
            content=generate_latest(),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )
