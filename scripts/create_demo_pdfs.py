"""Générer deux PDF fictifs pour tester l’import ; aucun résultat n’est préindexé."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'data' / 'demo'
TARGET.mkdir(parents=True, exist_ok=True)
FONT = Path('/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf')
if not FONT.exists():
    FONT = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
if FONT.exists():
    pdfmetrics.registerFont(TTFont('Demo', str(FONT)))
font = 'Demo' if FONT.exists() else 'Helvetica'


def create(name, pages):
    pdf = canvas.Canvas(str(TARGET / name), pagesize=(595, 842), invariant=1)
    pdf.setTitle(name.removesuffix('.pdf'))
    for number, (title, sections) in enumerate(pages, 1):
        pdf.setFillColor(colors.HexColor('#173e5d'))
        pdf.setFont(font, 10)
        pdf.drawString(52, 786, 'SPOC - DOCUMENT ENTIÈREMENT FICTIF')
        pdf.setFont(font, 19)
        pdf.drawString(52, 740, title)
        cursor = 693
        for heading, body in sections:
            pdf.setFont(font, 12)
            pdf.setFillColor(colors.HexColor('#173e5d'))
            pdf.drawString(52, cursor, heading)
            cursor -= 27
            pdf.setFont(font, 11)
            pdf.setFillColor(colors.HexColor('#41586b'))
            for line in simpleSplit(body, font, 11, 490):
                pdf.drawString(52, cursor, line)
                cursor -= 19
            cursor -= 30
        pdf.setFont(font, 9)
        pdf.setFillColor(colors.HexColor('#8394a1'))
        pdf.drawString(52, 45, f'Données inventées pour les essais du prototype - Page {number}')
        pdf.showPage()
    pdf.save()
    print(TARGET / name)


create('dossier-a-temoignages.pdf', [
    ('Compte rendu de recherche', [
        ('Témoignage concernant Lina Morvan', 'Un voisin pense avoir aperçu Lina Morvan près du hangar le 5 juin. Il était loin et n’a pas pu confirmer son identité.'),
        ('Contrôle du registre', 'La liste du centre ne mentionne pas Lina. Le dernier feuillet manque. Cette absence ne permet pas de conclure sur son passage au centre.'),
        ('Entretien de suivi', 'L’entretien de suivi est prévu jeudi à 14 h.'),
    ]),
    ('Rectification et pièces associées', [
        ('Date concernant Sami Ferrand', 'La fiche initiale indique le 8 mai comme date de disparition. La famille précise que le 8 mai correspond au dernier appel. La date de disparition n’est pas établie.'),
        ('Affaires personnelles', 'Le sac de Sami a été remis à sa sœur Nora.'),
        ('Attestation relative à un homonyme', 'Une attestation mentionne Port-Lys comme lieu de décès. Le numéro du dossier indique qu’elle concerne un homonyme de Lina Morvan. Le décès de Lina n’est pas établi. La mairie de Belle-Rive conserve une copie de l’attestation.'),
    ]),
])
create('dossier-b-homonyme.pdf', [
    ('Observation dans un autre dossier', [
        ('Lina Morvan, dossier distinct', 'Le dossier indique que Lina Morvan a été vue au port le 12 juillet. Son identité a été vérifiée sur place. Cette personne appartient à un dossier distinct de celui du témoignage du hangar.'),
        ('Inventaire', 'Un sac a été enregistré à l’accueil de la mairie. Aucun rapprochement avec les affaires de Sami Ferrand n’est établi.'),
    ]),
])
