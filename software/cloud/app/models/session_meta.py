from pydantic import BaseModel
from moose_lib import Key
from datetime import datetime
from typing import Optional


class SessionMeta(BaseModel):
    session_id: Key[str]
    horse_name: Optional[str] = None
    location: str = ""
    notes: str = ""
    start_time: datetime
    end_time: Optional[datetime] = None
    total_samples: int = 0
    device_config: str = "{}"
    uploaded_at: datetime
