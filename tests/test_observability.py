import json
import logging
from unittest.mock import patch

from prometheus_client.parser import text_string_to_metric_families

import observability
from main import app
from observability import JsonFormatter


@app.get("/observability-test/{resource_id}", status_code=202)
def observability_test_route(resource_id: str):
    return {"accepted": bool(resource_id)}


def _sample_value(metrics_text, metric_name, expected_labels):
    for family in text_string_to_metric_families(metrics_text):
        for sample in family.samples:
            if sample.name == metric_name and all(
                sample.labels.get(key) == value
                for key, value in expected_labels.items()
            ):
                return sample.value
    return 0.0


def test_metrics_output_counter_status_and_normalized_route(client):
    sensitive_id = "order-507f1f77bcf86cd799439011"
    labels = {
        "service": "order-service",
        "method": "GET",
        "route": "/observability-test/{resource_id}",
        "status_code": "202",
    }
    before = _sample_value(client.get("/metrics").text, "http_requests_total", labels)
    with patch.object(observability.access_logger, "info") as access_log:
        response = client.get(f"/observability-test/{sensitive_id}")
    assert response.status_code == 202
    logged_fields = access_log.call_args.kwargs["extra"]
    assert logged_fields["route"] == "/observability-test/{resource_id}"
    assert sensitive_id not in logged_fields["route"]
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    assert "# HELP http_requests_total" in metrics.text
    assert "# HELP http_request_duration_seconds" in metrics.text
    assert "process_virtual_memory_bytes" in metrics.text
    assert "python_info" in metrics.text
    assert sensitive_id not in metrics.text
    assert _sample_value(metrics.text, "http_requests_total", labels) == before + 1


def test_not_found_status_is_counted_without_raw_path(client):
    raw_path = "/missing/private-resource-123456"
    assert client.get(raw_path).status_code == 404
    metrics = client.get("/metrics").text
    assert raw_path not in metrics
    assert (
        _sample_value(
            metrics,
            "http_requests_total",
            {
                "service": "order-service",
                "method": "GET",
                "route": "__unmatched__",
                "status_code": "404",
            },
        )
        >= 1
    )


def test_json_formatter_emits_safe_one_line_fields():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "ignored", (), None)
    record.event = "http_request"
    record.method = "GET"
    record.route = "/api/items/{item_id}"
    record.status = 200
    record.duration_ms = 1.25
    rendered = JsonFormatter("order-service").format(record)
    payload = json.loads(rendered)
    assert "\n" not in rendered
    assert set(payload) == {
        "timestamp",
        "level",
        "service",
        "event",
        "method",
        "route",
        "status",
        "duration_ms",
    }
    assert payload["service"] == "order-service"
    assert payload["route"] == "/api/items/{item_id}"
