"""Durable revisions; approvals are bound to a specific immutable payload."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class OverlayStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('Unsupported overlay database version')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    approved INTEGER, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (
                    source_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(source_id,revision));
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, profile TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS batch_items (
                    batch_id TEXT NOT NULL, position INTEGER NOT NULL,
                    source_id TEXT NOT NULL, PRIMARY KEY(batch_id,position));
                PRAGMA user_version=1;
            ''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, source_id: str, payload: dict) -> int:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM sources WHERE id=?', (source_id,)).fetchone()
            if row:
                previous = db.execute('SELECT payload FROM revisions WHERE source_id=? AND revision=?',
                                      (source_id, row['revision'])).fetchone()[0]
                if previous == encoded:
                    return row['revision']
                if row['state'] == 'rendering':
                    raise ValueError('Cannot edit while rendering')
            revision = row['revision'] + 1 if row else 1
            db.execute('INSERT INTO revisions VALUES (?,?,?)', (source_id, revision, encoded))
            db.execute('INSERT OR REPLACE INTO sources VALUES (?,?,NULL,?)',
                       (source_id, revision, 'needs_edit' if payload.get('blocking') else 'review'))
            return revision

    def load(self, source_id: str) -> dict:
        with self._db() as db:
            row = db.execute('SELECT s.*,r.payload FROM sources s JOIN revisions r '
                             'ON s.id=r.source_id AND s.revision=r.revision WHERE s.id=?',
                             (source_id,)).fetchone()
            if row is None:
                raise KeyError(source_id)
            return {**dict(row), 'payload': json.loads(row['payload'])}

    def approve(self, source_id: str, revision: int):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT s.state,r.payload FROM sources s JOIN revisions r '
                             'ON s.id=r.source_id AND s.revision=r.revision '
                             'WHERE s.id=? AND s.revision=?', (source_id, revision)).fetchone()
            if row is None or row['state'] == 'rendering':
                raise ValueError('Stale or rendering revision')
            if json.loads(row['payload']).get('blocking'):
                raise ValueError('Resolve blocking warnings before approval')
            db.execute('UPDATE sources SET approved=?,state=? WHERE id=?',
                       (revision, 'approved', source_id))

    def is_approved(self, source_id: str, revision: int) -> bool:
        row = self.load(source_id)
        return row['revision'] == revision == row['approved']

    def set_state(self, source_id: str, revision: int, state: str):
        if state not in {'review', 'needs_edit', 'approved', 'rendering', 'completed', 'failed'}:
            raise ValueError('Invalid state')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM sources WHERE id=? AND revision=?',
                             (source_id, revision)).fetchone()
            if row is None:
                raise ValueError('Stale revision')
            if state in {'rendering', 'completed', 'approved'} and row['approved'] != revision:
                raise ValueError('Revision is not approved')
            if state == 'rendering' and row['state'] == 'rendering':
                raise ValueError('Already rendering')
            db.execute('UPDATE sources SET state=? WHERE id=?', (state, source_id))

    def save_batch(self, batch_id: str, source_ids: tuple[str, ...], profile: dict):
        if not source_ids or len(set(source_ids)) != len(source_ids):
            raise ValueError('Batch must contain unique sources')
        with self._db() as db:
            db.execute('INSERT OR REPLACE INTO batches VALUES (?,?)', (batch_id, json.dumps(profile)))
            db.execute('DELETE FROM batch_items WHERE batch_id=?', (batch_id,))
            db.executemany('INSERT INTO batch_items VALUES (?,?,?)',
                           [(batch_id, i, source) for i, source in enumerate(source_ids)])

    def load_batch(self, batch_id: str) -> dict:
        with self._db() as db:
            row = db.execute('SELECT profile FROM batches WHERE id=?', (batch_id,)).fetchone()
            if row is None:
                raise KeyError(batch_id)
            ids = [r[0] for r in db.execute('SELECT source_id FROM batch_items WHERE batch_id=? '
                                          'ORDER BY position', (batch_id,))]
            return {'source_ids': ids, 'profile': json.loads(row[0])}
