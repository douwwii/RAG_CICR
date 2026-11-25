"""Garde-fous de reformulation multilingue ; aucune requête distante."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from query_rewriting import validate_rewrite, PROMPT

class MultilingualTests(unittest.TestCase):
    def test_questions_in_four_languages_and_mixed_script_names(self):
        for q in ['Is the death of Lina confirmed?', '¿Se ha confirmado la muerte de Karim?', 'هل تم تأكيد وفاة Adam؟', 'Le décès de Sami est-il confirmé ?']:
            validate_rewrite(q,q)
        self.assertIn('Conserve la langue de la question', PROMPT)
        self.assertNotIn('pour MiniLM', PROMPT)

    def test_foreign_negations_and_identifiers_cannot_disappear(self):
        for a,b in [('Lina was not seen on 12 April','Lina was seen on 12 April'),('Karim nunca llegó al centro','Karim llegó al centro'),('لم يصل Adam إلى المركز','وصل Adam إلى المركز'),('Was Lina seen in RF-42?','Was Lina seen in RF-77?'), ('Karim llegó en abril','Karim llegó en mayo'), ('وصل Adam في أبريل','وصل Adam في مايو')]:
            with self.subTest(a=a),self.assertRaises(ValueError): validate_rewrite(a,b)
