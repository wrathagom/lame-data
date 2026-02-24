from moose_lib import IngestPipeline, IngestPipelineConfig, OlapConfig

from app.models.session_meta import SessionMeta
from app.models.sensor_reading import SensorReading

session_meta_pipeline = IngestPipeline[SessionMeta](
    "session-meta",
    IngestPipelineConfig(
        ingest_api=True,
        stream=True,
        table=OlapConfig(order_by_fields=["session_id"]),
    ),
)

sensor_reading_pipeline = IngestPipeline[SensorReading](
    "sensor-reading",
    IngestPipelineConfig(
        ingest_api=True,
        stream=True,
        table=OlapConfig(order_by_fields=["session_id", "device_id", "millis_time"]),
    ),
)
