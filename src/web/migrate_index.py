"""Construire et vérifier une nouvelle génération avant de basculer le manifeste web.

Exécuter serveur arrêté : python -m web.migrate_index (PYTHONPATH=src).
"""
import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import sqlite3
from uuid import uuid4

from qdrant_client import QdrantClient

from catalog import Catalog
from catalog_index import prepare_index_records
from common import CATALOG_FILE, DATA_FILE
from config import ROOT, VectorStoreConfig, OllamaConfig
from data_loader import load_field_records
from ingestion import ingest_pdf
from ollama_client import OllamaClient
from passage_index import PassageIndex
from qdrant_store import QdrantVectorStore
from web.index_config import WebIndexConfig, BGE_CONFIG, CONTEXT_VERSION, create_embedder


def build_index(data_path, catalog_path, *, embedder=None, llm=None):
    data_path = Path(data_path).resolve()
    old = WebIndexConfig.load(data_path)
    jobs_path = data_path / 'jobs.sqlite'
    jobs = []
    if jobs_path.exists():
        with closing(sqlite3.connect(jobs_path)) as db:
            db.row_factory = sqlite3.Row
            jobs = [dict(r) for r in db.execute('SELECT * FROM jobs')]
        if any(j['status'] in {'queued', 'running'} for j in jobs):
            raise ValueError('Terminez les imports en cours avant de migrer.')
    generation = data_path / 'indexes' / ('bge-context-coherent-' + str(uuid4()))
    generation.mkdir(parents=True)
    config = WebIndexConfig(
        embedding=BGE_CONFIG,
        fields=VectorStoreConfig(path=generation / 'qdrant', collection_name='cicr_fields_bge_context_v1'),
        passage_collection='spoc_pdf_bge_coherent_v1',
        text_builder_version=CONTEXT_VERSION, artifact_path=generation / 'artifacts', coherent=True,
    )
    config.artifact_path.mkdir()
    encoder = embedder or create_embedder(config.embedding)
    llm = llm or OllamaClient(OllamaConfig(
        base_url=os.environ.get('SPOC_OLLAMA_URL', 'http://127.0.0.1:11435'),
        model_name=os.environ.get('SPOC_OLLAMA_MODEL', 'qwen3.8:27b-mlx'),
        timeout_seconds=180.0, num_predict=16384,
    ))
    with Catalog(catalog_path, read_only=True) as catalog:
        records = prepare_index_records(load_field_records(DATA_FILE), catalog, DATA_FILE, include_person_context=True)
    counts = {}
    with QdrantVectorStore(config.fields) as store:
        print('Indexation des champs avec leur contexte de personne…', flush=True)
        store.rebuild(records, encoder.embed_documents([r.embedding_text for r in records]),
                      profile=encoder.profile, text_builder_version=config.text_builder_version)
    with closing(QdrantClient(path=str(config.fields.path))) as client:
        index = PassageIndex(client, collection=config.passage_collection)
        index.ensure(encoder)
        for job in jobs:
            if job['status'] != 'done':
                continue
            with Catalog(catalog_path, read_only=True) as catalog:
                source = catalog.get_document(job['dossier_id'], job['document_id'])
            if source is None or source.source_kind != 'pdf':
                raise ValueError('Source PDF indexée introuvable dans le catalogue.')
            path = Path(source.source_path).resolve()
            if path != data_path / (source.document_id + '.pdf') or sha256(path.read_bytes()).hexdigest() != job['digest']:
                raise ValueError('Le PDF original ne correspond plus à son empreinte.')
            print('Réindexation PDF :', job['filename'], flush=True)
            pages, passages, warning = ingest_pdf(path, source, llm, encoder, index,
                config.artifact_path / (source.document_id + '.json'),
                lambda stage: print('  ' + stage, flush=True), coherent=True)
            if warning:
                raise ValueError('Migration non activée : le découpage cohérent est en repli.')
            counts[job['job_id']] = dict(page_count=pages, passage_count=passages)
        if client.count(config.fields.collection_name, exact=True).count != len(records):
            raise ValueError('Champs manquants dans le nouvel index.')
        if client.count(config.passage_collection, exact=True).count != sum(c['passage_count'] for c in counts.values()):
            raise ValueError('Passages manquants dans le nouvel index.')
    # Réouverture et vérification des références/profils avec le chemin de recherche applicatif.
    from search import retrieve
    with QdrantVectorStore(config.fields) as store, Catalog(catalog_path, read_only=True) as catalog:
        for r in records:
            hits = retrieve(store, encoder, r.embedding_text, catalog=catalog, dossier_id=r.dossier_id,
                            top_k=5, text_builder_version=config.text_builder_version)
            if not any(h.id == r.id for h in hits):
                raise ValueError(f'Champ {r.id} non retrouvé après réouverture.')
    report = dict(fields=len(records), pdf_documents=len(counts), passages=sum(c['passage_count'] for c in counts.values()),
                  embedding_profile=encoder.profile.model_dump(), jobs=counts)
    (generation / 'migration.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return config, report, old


def activate_index(data_path, config, report, old):
    data_path = Path(data_path)
    # Toutes les opérations susceptibles d’échouer avant la publication laissent l’ancien index actif.
    (data_path / 'previous_index.json').write_text(old.model_dump_json(indent=2), encoding='utf-8')
    temporary = data_path / 'active_index.tmp'
    temporary.write_text(config.model_dump_json(indent=2), encoding='utf-8')
    temporary.replace(data_path / 'active_index.json')
    # Ces compteurs sont indicatifs ; la source et les vecteurs sont déjà validés et publiés.
    if report['jobs']:
        with closing(sqlite3.connect(data_path / 'jobs.sqlite')) as db, db:
            for job_id, counts in report['jobs'].items():
                db.execute('UPDATE jobs SET page_count=?, passage_count=?, warning=NULL WHERE job_id=?',
                           (counts['page_count'], counts['passage_count'], job_id))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-path', type=Path, default=Path(os.environ.get('SPOC_WEB_DATA', ROOT / 'web_data')))
    parser.add_argument('--catalog', type=Path, default=CATALOG_FILE)
    args = parser.parse_args()
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1', 8000)) == 0:
            parser.error('Arrêtez le backend sur le port 8000 avant la migration.')
    config, report, old = build_index(args.data_path, args.catalog)
    activate_index(args.data_path, config, report, old)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print('BGE-M3 contexte_coherent activé. Vous pouvez relancer l’application.', flush=True)


if __name__ == '__main__':
    main()
