"""Journal persistant ; les connexions SQLite restent propres à chaque thread."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class JobRepository:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY, document_id TEXT UNIQUE NOT NULL,
                dossier_id TEXT NOT NULL, digest TEXT NOT NULL, filename TEXT NOT NULL,
                status TEXT NOT NULL, stage TEXT NOT NULL, error TEXT, warning TEXT,
                page_count INTEGER, passage_count INTEGER,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                UNIQUE(dossier_id, digest))''')
            db.execute('CREATE TABLE IF NOT EXISTS dossier_settings (dossier_id TEXT PRIMARY KEY, archived INTEGER NOT NULL DEFAULT 0)')
            db.execute("UPDATE jobs SET status='error', stage='Interrompu', error='Le serveur a été arrêté pendant cet import. Réimportez le fichier pour réessayer.' WHERE status IN ('queued','running')")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, job_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()
            return dict(row) if row else None

    def documents(self, dossier_id):
        with self.connection() as db:
            return {r['document_id']: dict(r) for r in db.execute('SELECT * FROM jobs WHERE dossier_id=?', (dossier_id,))}

    def duplicate(self, dossier_id, digest):
        with self.connection() as db:
            row = db.execute('SELECT * FROM jobs WHERE dossier_id=? AND digest=?', (dossier_id, digest)).fetchone()
            return dict(row) if row else None

    def create(self, job_id, document_id, dossier_id, digest, filename):
        with self.connection() as db:
            db.execute('INSERT INTO jobs(job_id,document_id,dossier_id,digest,filename,status,stage) VALUES(?,?,?,?,?,?,?)',
                       (job_id, document_id, dossier_id, digest, filename, 'queued', 'En attente'))

    def update(self, job_id, **values):
        allowed = {'status', 'stage', 'error', 'warning', 'page_count', 'passage_count'}
        if not values or not values.keys() <= allowed:
            raise ValueError('Mise à jour de tâche invalide.')
        with self.connection() as db:
            db.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in values) + ' WHERE job_id=?', (*values.values(), job_id))

    @staticmethod
    def public(job):
        return {k: v for k, v in job.items() if k != 'digest'}

    def archived(self):
        with self.connection() as db:
            return {r[0] for r in db.execute('SELECT dossier_id FROM dossier_settings WHERE archived=1')}

    def archive(self, dossier_id, archived):
        with self.connection() as db:
            db.execute('INSERT INTO dossier_settings VALUES (?,?) ON CONFLICT(dossier_id) DO UPDATE SET archived=excluded.archived', (dossier_id, int(archived)))

    def move_document(self, document_id, destination):
        with self.connection() as db:
            db.execute('UPDATE jobs SET dossier_id=? WHERE document_id=?', (destination, document_id))

    def delete_documents(self, document_ids, dossier_id=None):
        with self.connection() as db:
            db.executemany('DELETE FROM jobs WHERE document_id=?', [(d,) for d in document_ids])
            if dossier_id is not None:
                db.execute('DELETE FROM dossier_settings WHERE dossier_id=?', (dossier_id,))
