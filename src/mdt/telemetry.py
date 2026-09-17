import logging
import os

from opentelemetry import metrics, trace


def configure() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.sdk.resources import Resource

        configure_azure_monitor(
            resource=Resource.create({"service.name": "mdt-observatory"}),
            logger_name="mdt",
            enable_live_metrics=False,
            instrumentation_options={
                "azure_sdk": {"enabled": False},
                "requests": {"enabled": False},
                "urllib": {"enabled": False},
                "urllib3": {"enabled": False},
            },
        )


tracer = trace.get_tracer("mdt.workflow")
meter = metrics.get_meter("mdt.workflow")
event_counter = meter.create_counter("mdt.events", description="Persisted MDT workflow events")
error_counter = meter.create_counter("mdt.errors", description="Visible failed agent analyses")
