"""Import explicite du manifeste fictif, sans extraction ni indexation vectorielle."""
import argparse
import json
from pathlib import Path
import sqlite3

from pydantic import ValidationError

from catalog import Catalog, CatalogError
from common import CATALOG_FILE, CATALOG_SEED_FILE
from data_loader import DataValidationError, load_field_records
from schemas import CatalogSeed, DocumentMetadata


def load_catalog_seed(path: Path) -> CatalogSeed:
    """Valide le manifeste et résout ses sources relativement à son répertoire."""
    path = Path(path).resolve()
    try:
        seed = CatalogSeed.model_validate(json.loads(path.read_text('utf-8')))
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        raise DataValidationError(f'{path}: manifeste invalide : {exc}') from exc

    sources = {}
    documents = []
    for document in seed.documents:
        source_path = (path.parent / document.source_path).resolve()
        if not source_path.is_file():
            raise DataValidationError(f'{path}: source absente pour {document.document_id}: {source_path}')
        # Le manifeste de démonstration relie les références historiques à leur id JSON.
        if document.source_locator is not None:
            prefix, separator, record_id = document.source_locator.partition('=')
            if (
                source_path.suffix.lower() != '.json' or prefix != 'id' or not separator
                or not record_id.isascii() or not record_id.isdecimal()
                or len(record_id) > 20
            ):
                raise DataValidationError(
                    f'{path}: emplacement non pris en charge pour {document.document_id}: '
                    f'{document.source_locator} (attendu : id=N dans un corpus JSON)'
                )
            if source_path not in sources:
                sources[source_path] = {r.id: r for r in load_field_records(source_path)}
            record = sources[source_path].get(int(record_id))
            if record is None or record.document_id != document.document_id:
                raise DataValidationError(f'{path}: référence source incohérente pour {document.document_id}')
            if record.person_id not in document.person_ids or record.source_kind != document.source_kind:
                raise DataValidationError(f'{path}: métadonnées source incohérentes pour {document.document_id}')
        documents.append(DocumentMetadata.model_validate({
            **document.model_dump(), 'source_path': str(source_path),
        }))
    return CatalogSeed(dossiers=seed.dossiers, persons=seed.persons, documents=documents)


def main() -> None:
    parser = argparse.ArgumentParser(description='Initialiser le catalogue documentaire fictif')
    parser.add_argument('--seed', type=Path, default=CATALOG_SEED_FILE, help='Manifeste JSON')
    parser.add_argument('--db', type=Path, default=CATALOG_FILE, help='Fichier SQLite du catalogue')
    args = parser.parse_args()
    try:
        seed = load_catalog_seed(args.seed)
        with Catalog(args.db) as catalog:
            catalog.initialize()
            summary = catalog.register(
                dossiers=seed.dossiers, persons=seed.persons, documents=seed.documents,
            )
            print(f'Catalogue : {args.db.resolve()}')
            print(f'Ajoutés : {summary.dossiers} dossiers, {summary.persons} personnes, '
                  f'{summary.documents} documents')
            for dossier in catalog.list_dossiers():
                print(f'{dossier.dossier_id} | {dossier.title} | '
                      f'{len(dossier.person_ids)} personnes | '
                      f'{len(catalog.list_documents(dossier.dossier_id))} documents')
    except (DataValidationError, CatalogError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f'Erreur : {exc}\n')


if __name__ == '__main__':
    main()
