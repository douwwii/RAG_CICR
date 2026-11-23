import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from query_rewriting import rewrite_question, validate_rewrite
from segmentation_schemas import Generation, GenerationError

class QueryRewritingTests(unittest.TestCase):
    def test_valid_query_is_encoded(self):
        client, encoder = Mock(), Mock()
        client.generate.return_value = Generation(content=json.dumps({'query':'Personne ayant récupéré le sac de Sami.'}))
        self.assertEqual(rewrite_question(client, 'Qui a le sac de Sami ?', encoder), 'Personne ayant récupéré le sac de Sami.')
        encoder.validate_query.assert_called_once()
        encoder.embed_query.assert_not_called()

    def test_failure_preserves_original(self):
        for content in ['{}', '{"query":"   "}', 'réponse libre']:
            client = Mock()
            client.generate.return_value = Generation(content=content)
            self.assertEqual(rewrite_question(client, 'Question originale ?', Mock()), 'Question originale ?')
        client.generate.side_effect = GenerationError('connection', 'Indisponible')
        self.assertEqual(rewrite_question(client, 'Question originale ?', Mock()), 'Question originale ?')

    def test_preserves_dates_names_negations_and_questions(self):
        for original, query in [
            ('Sami a-t-il disparu le 8 mai ?', 'Disparition de Sami le 8 mai.'),
            ('Sami a-t-il disparu le 8 mai ?', 'Sami a-t-il disparu le 9 mai ?'),
            ('Sami a-t-il disparu le 8 mai ?', 'Sami a-t-il disparu le 8 juin ?'),
            ('Qui a vu Sami ?', 'Qui a vu Nora ?'),
            ('Pourquoi Lina ne figure pas au registre ?', 'Pourquoi Lina figure au registre ?'),
            ('Où un voisin pense-t-il avoir vu Lina ?', 'Où un voisin a-t-il vu Lina ?'),
        ]:
            with self.subTest(original=original, query=query), self.assertRaises(ValueError):
                validate_rewrite(original, query)
        validate_rewrite('Où Amir Hadžić a-t-il disparu ?', "Où Amir Hadžić a-t-il disparu ?")
        validate_rewrite('Qui a récupéré le sac de Sami ?', 'Personne ayant récupéré le sac de Sami.')

    def test_token_overflow_falls_back(self):
        client, encoder = Mock(), Mock()
        client.generate.return_value = Generation(content='{"query":"Personne ayant récupéré le sac de Sami."}')
        encoder.validate_query.side_effect = ValueError('Trop de tokens')
        self.assertEqual(rewrite_question(client, 'Qui a récupéré le sac de Sami ?', encoder), 'Qui a récupéré le sac de Sami ?')
