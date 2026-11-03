"""Catalogue documentaire SQLite, indépendant de l’extraction et de Qdrant."""
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3

from schemas import DocumentMetadata, Dossier, Person


SCHEMA_VERSION = 1
_TABLES = {'dossiers', 'persons', 'dossier_persons', 'documents', 'document_persons'}
_SCHEMA = (
    '''CREATE TABLE dossiers (
        dossier_id TEXT NOT NULL PRIMARY KEY,
        title TEXT NOT NULL
    )''',
    '''CREATE TABLE persons (
        person_id TEXT NOT NULL PRIMARY KEY,
        display_name TEXT NOT NULL
    )''',
    '''CREATE TABLE dossier_persons (
        dossier_id TEXT NOT NULL,
        person_id TEXT NOT NULL,
        PRIMARY KEY (dossier_id, person_id),
        FOREIGN KEY (dossier_id) REFERENCES dossiers(dossier_id),
        FOREIGN KEY (person_id) REFERENCES persons(person_id)
    )''',
    '''CREATE TABLE documents (
        document_id TEXT NOT NULL PRIMARY KEY,
        dossier_id TEXT NOT NULL,
        source_kind TEXT NOT NULL,
        source_path TEXT NOT NULL,
        source_locator TEXT,
        UNIQUE (document_id, dossier_id),
        FOREIGN KEY (dossier_id) REFERENCES dossiers(dossier_id)
    )''',
    '''CREATE TABLE document_persons (
        document_id TEXT NOT NULL,
        dossier_id TEXT NOT NULL,
        person_id TEXT NOT NULL,
        PRIMARY KEY (document_id, person_id),
        FOREIGN KEY (document_id, dossier_id)
            REFERENCES documents(document_id, dossier_id),
        FOREIGN KEY (dossier_id, person_id)
            REFERENCES dossier_persons(dossier_id, person_id)
    )''',
    'CREATE INDEX documents_by_dossier ON documents(dossier_id)',
    'CREATE INDEX document_persons_by_person ON document_persons(dossier_id, person_id)',
)


class CatalogError(ValueError):
    """Opération refusée par le catalogue."""


class CatalogSchemaError(CatalogError):
    """Base non initialisée ou schéma incompatible."""


class CatalogConflictError(CatalogError):
    """Un identifiant existe déjà avec une définition différente."""


class DossierNotFoundError(CatalogError):
    """Le dossier demandé n’existe pas ; aucun élargissement du périmètre."""


@dataclass(frozen=True)
class ImportSummary:
    """Nombre de nouvelles entités ; un réimport identique retourne des zéros."""

    dossiers: int = 0
    persons: int = 0
    documents: int = 0


class Catalog:
    def __init__(self, path: Path | str):
        self._connection = sqlite3.connect(str(path), isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        # Activer les contraintes avant toute transaction, sur chaque connexion.
        self._connection.execute('PRAGMA foreign_keys = ON')

    def __enter__(self) -> 'Catalog':
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._connection.execute('BEGIN IMMEDIATE')
        try:
            yield
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def initialize(self) -> None:
        """Crée une base vide ou accepte la version connue, sans écrasement."""
        with self._transaction():
            version = self._connection.execute('PRAGMA user_version').fetchone()[0]
            tables = {
                row[0] for row in self._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if version == SCHEMA_VERSION and tables == _TABLES:
                return
            if version != 0 or tables:
                raise CatalogSchemaError(
                    f'Base incompatible : version {version}, tables {sorted(tables)}. '
                    'Aucune réinitialisation automatique.'
                )
            for statement in _SCHEMA:
                self._connection.execute(statement)
            self._connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')

    def _require_schema(self) -> None:
        version = self._connection.execute('PRAGMA user_version').fetchone()[0]
        if version != SCHEMA_VERSION:
            raise CatalogSchemaError('Initialisez le catalogue avec initialize().')

    def _insert_or_check(self, table: str, columns: tuple[str, ...], values: tuple) -> bool:
        # Les noms SQL proviennent exclusivement des appels internes ci-dessous.
        row = self._connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} WHERE {columns[0]} = ?",
            (values[0],),
        ).fetchone()
        if row is not None:
            if tuple(row) != values:
                raise CatalogConflictError(
                    f'{table}: identifiant {values[0]} déjà défini différemment'
                )
            return False
        self._connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in values)})",
            values,
        )
        return True

    def _person_ids(self, table: str, column: str, identifier: str) -> list[str]:
        return [row[0] for row in self._connection.execute(
            f'SELECT person_id FROM {table} WHERE {column} = ? ORDER BY person_id',
            (identifier,),
        )]

    def register(
        self,
        *,
        dossiers: Sequence[Dossier] = (),
        persons: Sequence[Person] = (),
        documents: Sequence[DocumentMetadata] = (),
    ) -> ImportSummary:
        """Ajoute un lot atomiquement ; les définitions existantes sont immuables."""
        self._require_schema()
        # Revalider et copier les entrées avant la transaction, y compris les listes.
        dossiers = [Dossier.model_validate(d.model_dump()) for d in dossiers]
        persons = [Person.model_validate(p.model_dump()) for p in persons]
        documents = [DocumentMetadata.model_validate(d.model_dump()) for d in documents]
        added_dossiers = added_persons = added_documents = 0
        try:
            with self._transaction():
                for person in persons:
                    added_persons += self._insert_or_check(
                        'persons', ('person_id', 'display_name'),
                        (person.person_id, person.display_name),
                    )
                for dossier in dossiers:
                    inserted = self._insert_or_check(
                        'dossiers', ('dossier_id', 'title'),
                        (dossier.dossier_id, dossier.title),
                    )
                    if inserted:
                        self._connection.executemany(
                            'INSERT INTO dossier_persons VALUES (?, ?)',
                            [(dossier.dossier_id, p) for p in dossier.person_ids],
                        )
                    elif set(self._person_ids(
                        'dossier_persons', 'dossier_id', dossier.dossier_id,
                    )) != set(dossier.person_ids):
                        raise CatalogConflictError(
                            f'dossier {dossier.dossier_id}: personnes associées différentes'
                        )
                    added_dossiers += inserted
                for document in documents:
                    inserted = self._insert_or_check(
                        'documents',
                        ('document_id', 'dossier_id', 'source_kind', 'source_path', 'source_locator'),
                        (document.document_id, document.dossier_id, document.source_kind,
                         document.source_path, document.source_locator),
                    )
                    if inserted:
                        self._connection.executemany(
                            'INSERT INTO document_persons VALUES (?, ?, ?)',
                            [(document.document_id, document.dossier_id, p)
                             for p in document.person_ids],
                        )
                    elif set(self._person_ids(
                        'document_persons', 'document_id', document.document_id,
                    )) != set(document.person_ids):
                        raise CatalogConflictError(
                            f'document {document.document_id}: personnes associées différentes'
                        )
                    added_documents += inserted
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f'Lot annulé : relation ou identifiant invalide ({exc})') from exc
        return ImportSummary(added_dossiers, added_persons, added_documents)

    def _require_dossier(self, dossier_id: str) -> None:
        self._require_schema()
        if not self._connection.execute(
            'SELECT 1 FROM dossiers WHERE dossier_id = ?', (dossier_id,),
        ).fetchone():
            raise DossierNotFoundError(f'Dossier inconnu : {dossier_id}')

    def list_dossiers(self) -> list[Dossier]:
        self._require_schema()
        return [Dossier(
            dossier_id=row['dossier_id'], title=row['title'],
            person_ids=self._person_ids('dossier_persons', 'dossier_id', row['dossier_id']),
        ) for row in self._connection.execute('SELECT * FROM dossiers ORDER BY dossier_id')]

    def list_persons(self, dossier_id: str) -> list[Person]:
        self._require_dossier(dossier_id)
        rows = self._connection.execute(
            'SELECT p.person_id, p.display_name FROM persons p '
            'JOIN dossier_persons dp ON p.person_id = dp.person_id '
            'WHERE dp.dossier_id = ? ORDER BY p.person_id',
            (dossier_id,),
        )
        return [Person(**dict(row)) for row in rows]

    def _document_metadata(self, row: sqlite3.Row) -> DocumentMetadata:
        return DocumentMetadata(
            **dict(row),
            person_ids=self._person_ids('document_persons', 'document_id', row['document_id']),
        )

    def list_documents(
        self, dossier_id: str, person_id: str | None = None,
    ) -> list[DocumentMetadata]:
        self._require_dossier(dossier_id)
        query = 'SELECT d.* FROM documents d WHERE d.dossier_id = ?'
        parameters = [dossier_id]
        if person_id is not None:
            query += (
                ' AND EXISTS (SELECT 1 FROM document_persons dp '
                'WHERE dp.document_id = d.document_id AND dp.person_id = ?)'
            )
            parameters.append(person_id)
        rows = self._connection.execute(query + ' ORDER BY d.document_id', parameters)
        return [self._document_metadata(row) for row in rows]

    def get_document(
        self, dossier_id: str, document_id: str,
    ) -> DocumentMetadata | None:
        self._require_dossier(dossier_id)
        row = self._connection.execute(
            'SELECT * FROM documents WHERE dossier_id = ? AND document_id = ?',
            (dossier_id, document_id),
        ).fetchone()
        return self._document_metadata(row) if row else None
