from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

# Until a model has a finished job: from the published RTX 4090 bf16 time
# (1344x768, 5 s, 50 steps: ~1000 s), the slow end for a 24 GB card.
PRIOR_RATE = 0.6
PRIOR_OVERHEAD = 30.0
HISTORY = 50

def work(job: Dict[str, Any]) -> float:
    """Relative cost of a clip: denoising evaluations x latent volume."""
    megapixels = job['width'] * job['height'] / 1e6
    evaluations = max(1, int(job['num_inference_steps']) - 1)
    return evaluations * megapixels * job['num_frames'] / 4

def fit(samples: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    """Fit seconds = overhead + rate * work, with medians so the slow first job
    after a server start does not skew it."""
    samples = [(w, s) for w, s in samples if w > 0 and s > 0]
    if not samples:
        return None

    slopes = [
        (s2 - s1) / (w2 - w1)
        for i, (w1, s1) in enumerate(samples)
        for w2, s2 in samples[i + 1:]
        if abs(w2 - w1) > 1e-9
    ]
    slopes = [slope for slope in slopes if slope > 0]
    if slopes:
        rate = median(slopes)
        overhead = max(0.0, median(s - rate * w for w, s in samples))
    else:
        # all samples cost the same, so overhead cannot be separated out.
        rate, overhead = median(s / w for w, s in samples), 0.0
    return rate, overhead

class Estimator:
    def __init__(self, db_file):
        self.db_file = db_file
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_file) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS timings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model TEXT NOT NULL,
                    workflow TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    num_frames INTEGER,
                    num_inference_steps INTEGER,
                    seconds REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def record(self, job: Dict[str, Any], seconds: float) -> None:
        with sqlite3.connect(self.db_file) as conn:
            conn.execute('''
                INSERT INTO timings (
                    model, workflow, width, height, num_frames,
                    num_inference_steps, seconds
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                job['model'], job['workflow'], job['width'], job['height'],
                job['num_frames'], job['num_inference_steps'], seconds
            ))
            conn.commit()

    def calibration(self, model: str, workflow: str) -> Dict[str, Any]:
        """Fitted rate and overhead for a model, or the prior without data."""
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('''
                SELECT width, height, num_frames, num_inference_steps, seconds
                FROM timings WHERE model = ? AND workflow = ?
                ORDER BY id DESC LIMIT ?
            ''', (model, workflow, HISTORY)).fetchall()

        fitted = fit([(work(dict(row)), row['seconds']) for row in rows])
        if fitted is None:
            return dict(rate=PRIOR_RATE, overhead=PRIOR_OVERHEAD, samples=0, calibrated=False)
        return dict(rate=fitted[0], overhead=fitted[1], samples=len(rows), calibrated=True)

    def seconds(self, job: Dict[str, Any], calibration: Dict[str, Any] = None) -> float:
        calibration = calibration or self.calibration(job['model'], job['workflow'])
        return calibration['overhead'] + calibration['rate'] * work(job)

    def estimate(self, configurations: List[Dict[str, Any]], model: str, workflow: str) -> Dict[str, Any]:
        """Per-configuration and total time for an expanded sweep."""
        calibration = self.calibration(model, workflow)
        rows, total = [], 0.0
        for configuration in configurations:
            per_clip = self.seconds(configuration, calibration)
            subtotal = per_clip * configuration['clips']
            total += subtotal
            rows.append(dict(seconds_per_clip=per_clip, seconds=subtotal, **configuration))
        return dict(
            configurations=rows,
            clips=sum(c['clips'] for c in configurations),
            seconds=total,
            finish_at=(datetime.now() + timedelta(seconds=total)).isoformat(timespec='seconds'),
            calibration=calibration,
        )
