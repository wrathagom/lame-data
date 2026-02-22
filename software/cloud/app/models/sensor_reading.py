from pydantic import BaseModel
from moose_lib import Key
from datetime import datetime


class SensorReading(BaseModel):
    id: Key[str]
    session_id: str
    device_id: int
    position: str = ""
    sequence: int
    timestamp: datetime
    accel_x: float
    accel_y: float
    accel_z: float
    magnitude: float
