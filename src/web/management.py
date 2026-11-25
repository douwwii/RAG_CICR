"""Gestion locale ; journal de déplacement pour restaurer une opération interrompue."""
import json
from pathlib import Path
from uuid import uuid4
from catalog import Catalog
from schemas import Dossier
from qdrant_client import models


class Management:
    def create_dossier(self, title):
        dossier = Dossier(dossier_id='DOS-'+str(uuid4()), title=title.strip())
        with self.lock, Catalog(self.catalog_path) as catalog:
            catalog.register(dossiers=[dossier])
        return dict(dossier.model_dump(), archived=False)

    def update_dossier(self, dossier_id, title=None, archived=None):
        with self.lock, Catalog(self.catalog_path) as catalog:
            self.recover_delete()
            catalog.list_documents(dossier_id)
            if archived and any(j['status'] in {'running','queued'} for j in self.jobs.documents(dossier_id).values()):
                raise ValueError('Un import est en cours dans ce dossier.')
            if title is not None:
                catalog.rename_dossier(dossier_id, title)
            if archived is not None:
                self.jobs.archive(dossier_id, archived)

    def _set_document_scope(self, document_id, destination, artifact):
        with Catalog(self.catalog_path) as catalog:
            catalog.move_document(document_id, destination)
        self.jobs.move_document(document_id, destination)
        if artifact is not None:
            updated = json.loads(json.dumps(artifact))
            updated['segmentation']['document']['source']['dossier_id'] = destination
            for p in updated['passages']:
                p['dossier_id'] = destination
            path = self.artifact_path / (document_id+'.json')
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(updated, ensure_ascii=False), encoding='utf-8')
            temporary.replace(path)
        for collection in [self.index_config.fields.collection_name, self.index_config.passage_collection]:
            if self.client.collection_exists(collection):
                result = self.client.set_payload(collection, payload={'dossier_id':destination}, points=models.Filter(must=[
                    models.FieldCondition(key='document_id', match=models.MatchValue(value=document_id))]), wait=True)
                if result.status != models.UpdateStatus.COMPLETED:
                    raise ValueError('Mise à jour du périmètre Qdrant inachevée.')
        self.reranking_cache.clear()

    def recover_move(self):
        journal = self.data_path / 'document-move.json'
        if journal.exists():
            data = json.loads(journal.read_text(encoding='utf-8'))
            self._set_document_scope(data['document_id'], data['origin'], data['artifact'])
            if data.get('added_persons'):
                with Catalog(self.catalog_path) as catalog:
                    catalog.remove_unused_person_links(data['destination'], data['added_persons'])
            journal.unlink()

    def move_document(self, origin, document_id, destination):
        with self.lock:
            self.recover_move()
            self.recover_delete()
            self.require_dossier(origin)
            self.require_dossier(destination)
            if origin == destination:
                raise ValueError('Choisissez un autre dossier.')
            with Catalog(self.catalog_path, read_only=True) as catalog:
                document = catalog.get_document(origin, document_id)
                if document is None:
                    raise FileNotFoundError()
                added_persons = sorted(set(document.person_ids) - {p.person_id for p in catalog.list_persons(destination)})
            jobs = self.jobs.documents(origin)
            job = jobs.get(document_id)
            if job and job['status'] in {'queued','running'}:
                raise ValueError('Un import est en cours pour ce document.')
            if job and self.jobs.duplicate(destination, job['digest']):
                raise ValueError('Ce document existe déjà dans le dossier de destination.')
            path = self.artifact_path / (document_id+'.json')
            artifact = json.loads(path.read_text()) if path.exists() else None
            journal = self.data_path / 'document-move.json'
            temporary = journal.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(document_id=document_id,origin=origin,artifact=artifact,destination=destination,added_persons=added_persons),ensure_ascii=False))
            temporary.replace(journal)
            try:
                self._set_document_scope(document_id, destination, artifact)
            except Exception:
                self.recover_move()
                raise
            journal.unlink()

    def recover_delete(self):
        import shutil
        journal = self.data_path / 'document-delete.json'
        if not journal.exists():
            return
        data = json.loads(journal.read_text())
        ids = data['documents']
        for collection in [self.index_config.fields.collection_name, self.index_config.passage_collection]:
            if ids and self.client.collection_exists(collection):
                result = self.client.delete(collection, points_selector=models.FilterSelector(filter=models.Filter(must=[
                    models.FieldCondition(key='document_id', match=models.MatchAny(any=ids))])), wait=True)
                if result.status != models.UpdateStatus.COMPLETED:
                    raise ValueError('Suppression Qdrant inachevée.')
        with Catalog(self.catalog_path) as catalog:
            catalog.delete_documents(ids, data['dossier'])
        self.jobs.delete_documents(ids, data['dossier'])
        self.reranking_cache.clear()
        for item in data['files']:
            path = self.data_path / item
            if not path.resolve().is_relative_to(self.data_path):
                raise ValueError('Chemin de suppression invalide.')
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        journal.unlink()

    def delete(self, dossier_id, document_id=None):
        with self.lock:
            self.recover_move()
            self.recover_delete()
            with Catalog(self.catalog_path, read_only=True) as catalog:
                documents = catalog.list_documents(dossier_id)
            if document_id is not None:
                documents = [d for d in documents if d.document_id == document_id]
                if not documents:
                    raise FileNotFoundError()
            ids = [d.document_id for d in documents]
            if any(j['status'] in {'running','queued'} and j['document_id'] in ids
                   for j in self.jobs.documents(dossier_id).values()):
                raise ValueError('Un import est en cours. Attendez sa fin avant de supprimer.')
            files = []
            for doc in documents:
                # Les sources JSON/TXT historiques peuvent être partagées : ne pas les effacer.
                paths = [self.artifact_path / (doc.document_id+'.json'),
                         self.artifact_path / 'checkpoints' / doc.document_id]
                if doc.source_kind == 'pdf' and Path(doc.source_path).resolve() == self.data_path / (doc.document_id+'.pdf'):
                    paths.append(Path(doc.source_path))
                for path in paths:
                    if path.exists() and path.resolve().is_relative_to(self.data_path):
                        files.append(str(path.resolve().relative_to(self.data_path)))
            journal = self.data_path / 'document-delete.json'
            temporary = journal.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(documents=ids,dossier=dossier_id if document_id is None else None,files=files)))
            temporary.replace(journal)
            self.recover_delete()
