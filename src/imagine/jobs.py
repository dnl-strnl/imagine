from datetime import datetime, timedelta
import json
import logging as log
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional

ACTIVE = ('queued', 'running')

class JobQueue:
    """Sweeps of jobs, run one at a time (one GPU) and kept in SQLite so they
    survive a restart."""

    def __init__(self, db_file, run_job: Callable[[Dict[str, Any]], Dict[str, Any]], estimator):
        self.db_file = db_file
        self.run_job = run_job
        self.estimator = estimator
        self._wake = threading.Event()
        self._thread = None
        self._init_db()

    def _init_db(self):
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_file) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sweeps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    spec_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sweep_id INTEGER NOT NULL,
                    config_key TEXT,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    error TEXT,
                    started_at REAL,
                    finished_at REAL,
                    output_filename TEXT
                )
            ''')
            # a job still running was cut off by a restart.
            conn.execute('''
                UPDATE jobs SET status = 'queued', started_at = NULL
                WHERE status = 'running'
            ''')
            conn.commit()

    def submit(self, name: str, spec: Dict[str, Any], jobs: List[Dict[str, Any]]) -> int:
        with sqlite3.connect(self.db_file) as conn:
            sweep_id = conn.execute(
                'INSERT INTO sweeps (name, spec_json) VALUES (?, ?)',
                (name, json.dumps(spec))
            ).lastrowid
            conn.executemany(
                'INSERT INTO jobs (sweep_id, config_key, payload_json) VALUES (?, ?, ?)',
                [(sweep_id, job['config_key'], json.dumps(job)) for job in jobs]
            )
            conn.commit()
        self._wake.set()
        return sweep_id

    def cancel(self, sweep_id: int) -> int:
        """Cancel the queued jobs of a sweep; the running one finishes."""
        with sqlite3.connect(self.db_file) as conn:
            cancelled = conn.execute('''
                UPDATE jobs SET status = 'cancelled'
                WHERE sweep_id = ? AND status = 'queued'
            ''', (sweep_id,)).rowcount
            conn.commit()
        return cancelled

    def run_next(self) -> bool:
        """Run the oldest queued job. Returns False when the queue is empty."""
        with sqlite3.connect(self.db_file) as conn:
            row = conn.execute('''
                SELECT id, sweep_id, payload_json FROM jobs
                WHERE status = 'queued' ORDER BY id LIMIT 1
            ''').fetchone()
            if row is None:
                return False
            job_id, sweep_id, payload_json = row
            started = time.time()
            conn.execute(
                "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
                (started, job_id)
            )
            conn.commit()

        job = dict(json.loads(payload_json), sweep_id=sweep_id, job_id=job_id)
        try:
            result = self.run_job(job)
            status, error = 'done', None
            self.estimator.record(job, time.time() - started)
        except Exception as job_exception:
            log.error(error := f'{job_exception=}')
            result, status = {}, 'failed'

        with sqlite3.connect(self.db_file) as conn:
            conn.execute('''
                UPDATE jobs SET status = ?, error = ?, finished_at = ?, output_filename = ?
                WHERE id = ?
            ''', (status, error, time.time(), result.get('filename'), job_id))
            conn.commit()
        return True

    def _work(self):
        while True:
            try:
                if not self.run_next():
                    self._wake.wait(timeout=2)
                    self._wake.clear()
            except Exception as worker_exception:
                log.error(f'{worker_exception=}')
                time.sleep(2)

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._work, daemon=True)
            self._thread.start()

    def _summary(self, conn, sweep) -> Dict[str, Any]:
        rows = conn.execute('''
            SELECT id, config_key, payload_json, status, error, started_at, finished_at
            FROM jobs WHERE sweep_id = ? ORDER BY id
        ''', (sweep['id'],)).fetchall()

        counts = dict(queued=0, running=0, done=0, failed=0, cancelled=0)
        groups, calibrations = {}, {}
        remaining, current, errors, now = 0.0, None, [], time.time()

        for row in rows:
            counts[row['status']] += 1
            group = groups.setdefault(row['config_key'], dict(
                config_key=row['config_key'], clips=0, done=0, failed=0, seconds=[]
            ))
            group['clips'] += 1
            if row['status'] == 'done':
                group['done'] += 1
                group['seconds'].append(row['finished_at'] - row['started_at'])
            elif row['status'] == 'failed':
                group['failed'] += 1
                errors.append(dict(job_id=row['id'], error=row['error']))
            elif row['status'] in ACTIVE:
                job = json.loads(row['payload_json'])
                key = (job['model'], job['workflow'])
                if key not in calibrations:
                    calibrations[key] = self.estimator.calibration(*key)
                expected = self.estimator.seconds(job, calibrations[key])
                if row['status'] == 'running':
                    elapsed = now - row['started_at']
                    remaining += max(0.0, expected - elapsed)
                    current = dict(
                        job_id=row['id'], prompt=job['prompt'], config_key=row['config_key'],
                        elapsed=elapsed, expected=expected
                    )
                else:
                    remaining += expected

        for group in groups.values():
            seconds = group.pop('seconds')
            group['seconds_per_clip'] = sum(seconds) / len(seconds) if seconds else None

        active = counts['queued'] + counts['running']
        if active:
            status = 'running' if counts['running'] else 'queued'
        else:
            status = 'cancelled' if counts['cancelled'] else 'done'

        return dict(
            id=sweep['id'],
            name=sweep['name'],
            created_at=sweep['created_at'],
            status=status,
            total=len(rows),
            counts=counts,
            configurations=list(groups.values()),
            current=current,
            errors=errors[-5:],
            remaining_seconds=remaining if active else 0.0,
            finish_at=(
                (datetime.now() + timedelta(seconds=remaining)).isoformat(timespec='seconds')
                if active else None
            ),
        )

    def sweeps(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Recent sweeps, newest first; each finish time includes the sweeps ahead of it."""
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT * FROM sweeps ORDER BY id DESC LIMIT ?', (limit,)
            ).fetchall()
            summaries = [self._summary(conn, row) for row in rows]

        ahead = 0.0
        for summary in reversed(summaries):
            if summary['finish_at']:
                ahead += summary['remaining_seconds']
                summary['remaining_seconds'] = ahead
                summary['finish_at'] = (
                    datetime.now() + timedelta(seconds=ahead)
                ).isoformat(timespec='seconds')
        return summaries

    def sweep(self, sweep_id: int) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT * FROM sweeps WHERE id = ?', (sweep_id,)).fetchone()
            return self._summary(conn, row) if row else None
