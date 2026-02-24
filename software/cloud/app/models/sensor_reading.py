from pydantic import BaseModel
from moose_lib import Key, clickhouse_datetime64
from datetime import datetime


class SensorReading(BaseModel):
    session_id: Key[str]
    device_id: int
    position: str = ""
    millis_time: int
    timestamp: clickhouse_datetime64(6)
    accel_x: float
    accel_y: float
    accel_z: float
    magnitude: float
