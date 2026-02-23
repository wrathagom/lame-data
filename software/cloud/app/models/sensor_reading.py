from pydantic import BaseModel
from moose_lib import Key
from datetime import datetime


class SensorReading(BaseModel):
    session_id: Key[str]
    device_id: int
    position: str = ""
    sequence: int
    timestamp: datetime
    accel_x: float
    accel_y: float
    accel_z: float
    magnitude: float
