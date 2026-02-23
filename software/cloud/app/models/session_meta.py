from pydantic import BaseModel
from moose_lib import Key, clickhouse_datetime64
from datetime import datetime
from typing import Optional


class SessionMeta(BaseModel):
    session_id: Key[str]
    horse_name: Optional[str] = None
    location: str = ""
    notes: str = ""
    start_time: clickhouse_datetime64(6)
    end_time: Optional[clickhouse_datetime64(6)] = None
    total_samples: int = 0
    device_config: str = "{}"
    uploaded_at: clickhouse_datetime64(6)
