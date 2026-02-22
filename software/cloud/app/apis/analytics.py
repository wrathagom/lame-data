import json
from moose_lib import Api, MooseClient
from pydantic import BaseModel
from typing import Optional

from app.ingest.pipelines import sensor_reading_pipeline, session_meta_pipeline
from app.analysis.gait_segmentation import segment_gait

SensorReadingTable = sensor_reading_pipeline.get_table()
SessionMetaTable = session_meta_pipeline.get_table()


# --- Gait analysis ---

class GaitAnalysisParams(BaseModel):
    session_id: str
    device_id: int
    movement: Optional[float] = 0.02
    variance: Optional[float] = 2.0
    frequency: Optional[float] = 0.3
    min_segment: Optional[float] = 2.0

class GaitAnalysisResponse(BaseModel):
    boundaries: str  # JSON array
    times: str
    types: str
    durations: str
    confidence: str
    count: int
    params: str  # JSON object
    debug: str   # JSON object

def gait_analysis(client: MooseClient, params: GaitAnalysisParams) -> list[GaitAnalysisResponse]:
    query = """
    SELECT magnitude
    FROM {table}
    WHERE session_id = {session_id} AND device_id = {device_id}
    ORDER BY sequence
    """
    rows = client.query.execute_raw(query, {
        "session_id": params.session_id,
        "device_id": params.device_id,
    })

    magnitudes = [row[0] for row in rows]
    if not magnitudes:
        return []

    result = segment_gait(
        magnitudes,
        sample_rate=194,
        movement_threshold=params.movement or 0.02,
        variance_threshold=params.variance or 2.0,
        frequency_threshold=params.frequency or 0.3,
        min_segment_seconds=params.min_segment or 2.0,
    )

    return [GaitAnalysisResponse(
        boundaries=json.dumps(result["boundaries"]),
        times=json.dumps(result["times"]),
        types=json.dumps(result["types"]),
        durations=json.dumps(result["durations"]),
        confidence=json.dumps(result["confidence"]),
        count=result["count"],
        params=json.dumps(result["params"]),
        debug=json.dumps(result["debug"]),
    )]

gait_analysis_api = Api[GaitAnalysisParams, GaitAnalysisResponse](
    name="gait-analysis",
    query_function=gait_analysis,
)


# --- Trends ---

class TrendsParams(BaseModel):
    horse_name: str

class TrendRecord(BaseModel):
    session_id: str
    start_time: str
    avg_magnitude: float
    variance: float
    sample_count: int

def get_trends(client: MooseClient, params: TrendsParams) -> list[TrendRecord]:
    query = """
    SELECT
        r.session_id as session_id,
        toString(m.start_time) as start_time,
        avg(r.magnitude) as avg_magnitude,
        varPop(r.magnitude) as variance,
        count() as sample_count
    FROM {readings} r
    JOIN {meta} m ON r.session_id = m.session_id
    WHERE m.horse_name = {horse_name}
    GROUP BY r.session_id, m.start_time
    ORDER BY m.start_time
    """
    return client.query.execute(query, {
        "readings": SensorReadingTable,
        "meta": SessionMetaTable,
        "horse_name": params.horse_name,
    })

trends_api = Api[TrendsParams, TrendRecord](
    name="trends",
    query_function=get_trends,
)


# --- Asymmetry ---

class AsymmetryParams(BaseModel):
    session_id: str

class AsymmetryRecord(BaseModel):
    position: str
    avg_magnitude: float
    std_magnitude: float
    sample_count: int

def get_asymmetry(client: MooseClient, params: AsymmetryParams) -> list[AsymmetryRecord]:
    query = """
    SELECT
        position,
        avg(magnitude) as avg_magnitude,
        stddevPop(magnitude) as std_magnitude,
        count() as sample_count
    FROM {table}
    WHERE session_id = {session_id}
    AND position != ''
    GROUP BY position
    ORDER BY position
    """
    return client.query.execute(query, {
        "table": SensorReadingTable,
        "session_id": params.session_id,
    })

asymmetry_api = Api[AsymmetryParams, AsymmetryRecord](
    name="asymmetry",
    query_function=get_asymmetry,
)
