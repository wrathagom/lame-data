from moose_lib import Api, MooseClient
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.ingest.pipelines import session_meta_pipeline, sensor_reading_pipeline

SessionMetaTable = session_meta_pipeline.get_table()
SensorReadingTable = sensor_reading_pipeline.get_table()


# --- List sessions ---

class SessionsQueryParams(BaseModel):
    horse_name: Optional[str] = None

class SessionRecord(BaseModel):
    session_id: str
    horse_name: Optional[str] = None
    location: str
    notes: str
    start_time: str
    end_time: Optional[str] = None
    total_samples: int
    device_config: str
    uploaded_at: str

def list_sessions(client: MooseClient, params: SessionsQueryParams) -> list[SessionRecord]:
    if params.horse_name:
        query = """
        SELECT session_id, horse_name, location, notes,
               toString(start_time) as start_time,
               toString(end_time) as end_time,
               total_samples, device_config,
               toString(uploaded_at) as uploaded_at
        FROM {table}
        WHERE horse_name = {horse_name}
        ORDER BY start_time DESC
        """
        return client.query.execute(query, {
            "table": SessionMetaTable,
            "horse_name": params.horse_name,
        })
    else:
        query = """
        SELECT session_id, horse_name, location, notes,
               toString(start_time) as start_time,
               toString(end_time) as end_time,
               total_samples, device_config,
               toString(uploaded_at) as uploaded_at
        FROM {table}
        ORDER BY start_time DESC
        """
        return client.query.execute(query, {"table": SessionMetaTable})

sessions_api = Api[SessionsQueryParams, SessionRecord](
    name="sessions",
    query_function=list_sessions,
)


# --- Session detail ---

class SessionDetailParams(BaseModel):
    session_id: str
    downsample: Optional[int] = 1

class SensorReadingRecord(BaseModel):
    session_id: str
    device_id: int
    position: str
    sequence: int
    timestamp: str
    accel_x: float
    accel_y: float
    accel_z: float
    magnitude: float

def get_session_detail(client: MooseClient, params: SessionDetailParams) -> list[SensorReadingRecord]:
    downsample = max(1, params.downsample or 1)
    query = """
    SELECT session_id, device_id, position, sequence,
           toString(timestamp) as timestamp,
           accel_x, accel_y, accel_z, magnitude
    FROM {table}
    WHERE session_id = {session_id}
    AND sequence % {downsample} = 0
    ORDER BY device_id, sequence
    """
    return client.query.execute(query, {
        "table": SensorReadingTable,
        "session_id": params.session_id,
        "downsample": downsample,
    })

session_detail_api = Api[SessionDetailParams, SensorReadingRecord](
    name="session-detail",
    query_function=get_session_detail,
)
