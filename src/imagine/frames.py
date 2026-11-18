import io
from pathlib import Path
import shutil
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

import av
from PIL import Image

def read_frame(source: Path, frame: Optional[str] = None, time: Optional[float] = None) -> Tuple[Image.Image, int, float]:
    """The first frame, the last, or the one on screen at `time`, with its index and time."""
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate)
        start = float(stream.start_time * stream.time_base) if stream.start_time else 0.0

        if frame != 'first' and time is not None and time > 0:
            container.seek(int((time + start) / stream.time_base), stream=stream)

        picked = None
        for decoded in container.decode(stream):
            at = (decoded.time or 0.0) - start
            # a player shows a frame until the next one is due.
            if picked is not None and frame is None and time is not None and at > time + 1e-3:
                break
            picked = decoded
            if frame == 'first':
                break

        if picked is None:
            raise ValueError('The clip has no frames.')
        at = max(0.0, (picked.time or 0.0) - start)
        return picked.to_image(), round(at * fps), at

class FrameLibrary:
    """Stills used as frames or references, with the clip and frame each came
    from. An outside edit is stored as a new version of the frame it edits."""

    def __init__(self, db_file, uploads):
        self.db_file = db_file
        self.uploads = Path(uploads)
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_file) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    root_id INTEGER,
                    parent_id INTEGER,
                    source_filename TEXT,
                    frame_index INTEGER,
                    time REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

    def _insert(self, conn, **values) -> int:
        columns = ', '.join(values)
        marks = ', '.join('?' for _ in values)
        frame_id = conn.execute(
            f'INSERT INTO frames ({columns}) VALUES ({marks})', tuple(values.values())
        ).lastrowid
        conn.execute('UPDATE frames SET root_id = COALESCE(root_id, id) WHERE id = ?', (frame_id,))
        return frame_id

    def cut(self, source: Path, frame: Optional[str] = None, time: Optional[float] = None) -> Dict[str, Any]:
        """A still from a generated file; the same frame twice is one entry."""
        source = Path(source)
        if source.suffix.lower() != '.mp4':
            return self._cut(source, 'image', None, None, lambda target: shutil.copyfile(source, target))

        if frame not in ('first', 'last') and time is None:
            frame = 'last'
        image, index, at = read_frame(source, frame=frame, time=None if frame else float(time))
        return self._cut(source, 'extract', index, at, image.save)

    def _cut(self, source, kind, index, at, write) -> Dict[str, Any]:
        with sqlite3.connect(self.db_file) as conn:
            existing = conn.execute('''
                SELECT id FROM frames
                WHERE source_filename = ? AND kind = ? AND frame_index IS ?
            ''', (source.name, kind, index)).fetchone()
            if existing:
                return self.get(existing[0])

            filename = source.name if index is None else f'{source.stem}_f{index:05d}.png'
            write(self.uploads / filename)
            frame_id = self._insert(
                conn, filename=filename, kind=kind, source_filename=source.name,
                frame_index=index, time=at,
            )
        return self.get(frame_id)

    def add(self, data: bytes, suffix: str, parent_id: Optional[int] = None) -> Dict[str, Any]:
        """Store an uploaded still; with `parent_id`, as an edit of that frame."""
        try:
            Image.open(io.BytesIO(data)).verify()
        except Exception:
            raise ValueError('That file is not an image.')

        with sqlite3.connect(self.db_file) as conn:
            root_id = None
            if parent_id is not None:
                parent = conn.execute('SELECT root_id FROM frames WHERE id = ?', (parent_id,)).fetchone()
                if parent is None:
                    raise ValueError('No such frame to add a version to.')
                root_id = parent[0]

            filename = f'{uuid.uuid4()}{suffix.lower() or ".png"}'
            (self.uploads / filename).write_bytes(data)
            frame_id = self._insert(
                conn, filename=filename, kind='edit' if parent_id is not None else 'upload',
                root_id=root_id, parent_id=parent_id,
            )
        return self.get(frame_id)

    def get(self, frame_id: int) -> Optional[Dict[str, Any]]:
        return next((frame for frame in self.all() if frame['id'] == frame_id), None)

    def all(self) -> List[Dict[str, Any]]:
        """Every frame, newest first."""
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('''
                SELECT frames.*, images.prompt AS source_prompt, images.url AS source_url
                FROM frames
                LEFT JOIN images ON images.filename = frames.source_filename
                ORDER BY frames.id
            ''').fetchall()

        families: Dict[int, List[int]] = {}
        for row in rows:
            families.setdefault(row['root_id'], []).append(row['id'])

        frames = []
        for row in rows:
            family = families[row['root_id']]
            frames.append(dict(
                id=row['id'],
                filename=row['filename'],
                url=f'/uploads/{row["filename"]}',
                kind=row['kind'],
                root_id=row['root_id'],
                parent_id=row['parent_id'],
                version=family.index(row['id']) + 1,
                versions=len(family),
                source=dict(
                    filename=row['source_filename'],
                    url=row['source_url'],
                    prompt=row['source_prompt'],
                ) if row['source_filename'] else None,
                frame_index=row['frame_index'],
                time=row['time'],
                created_at=row['created_at'],
            ))
        return frames[::-1]
