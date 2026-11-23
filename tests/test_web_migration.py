"""Migration isolée, publication contrôlée et réutilisation par le backend."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from catalog import Catalog
from catalog_index import prepare_index_records
from common import DATA_FILE
from data_loader import load_field_records
from schemas import Dossier, Person, DocumentMetadata
from web.index_config import WebIndexConfig, CONTEXT_VERSION
from web.migrate_index import build_index, activate_index
from web.service import WebService
from test_web import TestModel, ExactLLM
from test_embeddings import make_embedder
from segmentation import segment_document
from segmentation_schemas import Generation

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.catalog=self.path/'catalog.sqlite'
        self.records=load_field_records(DATA_FILE)[:2]
        with Catalog(self.catalog) as catalog:
            catalog.initialize()
            catalog.register(persons=[Person(person_id='P001',display_name='Jean Dupont')],
                             dossiers=[Dossier(dossier_id='DOS001',title='Fictif',person_ids=['P001'])],
                             documents=[DocumentMetadata(document_id=r.document_id,dossier_id='DOS001',source_kind=r.source_kind,source_path=str(DATA_FILE),source_locator=f'id={r.id}',person_ids=['P001']) for r in self.records])
        model=TestModel();model.max_seq_length=128
        self.encoder,_=make_embedder(model=model)

    def tearDown(self):self.temp.cleanup()

    def test_build_does_not_activate_then_service_uses_published_generation(self):
        data=self.path/'data';data.mkdir()
        with patch('web.migrate_index.load_field_records',return_value=self.records):
            config,report,old=build_index(data,self.catalog,embedder=self.encoder,llm=ExactLLM())
        self.assertFalse((data/'active_index.json').exists())
        self.assertEqual(report['fields'],2)
        self.assertTrue(config.coherent)
        activate_index(data,config,report,old)
        self.assertEqual(WebIndexConfig.load(data),config)
        self.assertTrue((data/'previous_index.json').exists())
        service=WebService(catalog_path=self.catalog,data_path=data,embedder=self.encoder,llm=ExactLLM())
        try:
            hits=service.search('DOS001','Jean Dupont',5)
            self.assertTrue(hits)
            self.assertEqual(service.index_config.text_builder_version,CONTEXT_VERSION)
            self.assertEqual(service.artifact_path,config.artifact_path)
            self.assertTrue(all(h['dossier_id']=='DOS001' for h in hits))
        finally:service.close()

    def test_failure_preserves_active_manifest(self):
        data=self.path/'data';data.mkdir()
        content=WebIndexConfig(artifact_path=data).model_dump_json()
        (data/'active_index.json').write_text(content)
        with patch('web.migrate_index.load_field_records',return_value=self.records),patch.object(self.encoder,'embed_documents',side_effect=ValueError('Simulation')):
            with self.assertRaises(ValueError):build_index(data,self.catalog,embedder=self.encoder,llm=ExactLLM())
        self.assertEqual((data/'active_index.json').read_text(),content)

    def test_person_context_does_not_rewrite_source_or_identifiers(self):
        with Catalog(self.catalog,read_only=True) as catalog:
            records=prepare_index_records(self.records,catalog,DATA_FILE,include_person_context=True)
        for old,new in zip(self.records,records):
            self.assertEqual(old.value,new.value);self.assertEqual(old.id,new.id)
            self.assertTrue(new.embedding_text.startswith('Personne : Jean Dupont.'))

    def test_coherent_segmentation_anchors_the_original_text(self):
        source=DocumentMetadata(document_id='D',dossier_id='DOS001',source_kind='pdf',source_path='test.pdf')
        text='Titre du document\nUn témoignage reste\nincertain.\n'
        from unittest.mock import Mock
        client=Mock();client.generate.return_value=Generation(content='{"passages":[{"title":"Témoignage","text":"Un témoignage reste incertain."}]}')
        run=segment_document(text,source,client,prompt='Test',prompt_version='v3-coherent',coherent=True)
        self.assertEqual(run.document.status,'validated')
        self.assertEqual(''.join(p.text for p in run.document.passages),text)
