"""Rapport PDF français, questions et corrigés espagnols, à partir des mesures réelles."""
from datetime import datetime
import hashlib
from html import escape
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEST = ROOT / 'output/pdf/evaluation-rag-espagnol-mancha4.pdf'
NAVY = colors.HexColor('#173347')
TEAL = colors.HexColor('#087F8C')
MUTED = colors.HexColor('#536876')
PALE = colors.HexColor('#EEF5F6')
FONT_PATH = Path('/usr/share/fonts/google-noto')


def main():
    cases = json.loads((HERE / 'questions.json').read_text(encoding='utf-8'))['cases']
    report = json.loads((HERE / 'results.json').read_text(encoding='utf-8'))
    rows = {r['id']: r for r in report['rows']}
    assert set(rows) == {c['id'] for c in cases}
    assert report['mode'] == 'technical_chunks_bge_only'
    assert report['questions_sha256'] == hashlib.sha256((HERE / 'questions.json').read_bytes()).hexdigest(), 'Relancer run.py après modification des annotations.'
    pdfmetrics.registerFont(TTFont('Noto', str(FONT_PATH / 'NotoSans-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('NotoBold', str(FONT_PATH / 'NotoSans-Bold.ttf')))
    pdfmetrics.registerFontFamily('Noto', normal='Noto', bold='NotoBold', italic='Noto', boldItalic='NotoBold')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('TitleM', fontName='NotoBold', fontSize=29, leading=35, textColor=NAVY, spaceAfter=16))
    styles.add(ParagraphStyle('HeadingM', fontName='NotoBold', fontSize=17, leading=23, textColor=NAVY, spaceAfter=13))
    styles.add(ParagraphStyle('SubM', fontName='NotoBold', fontSize=11, leading=15, textColor=TEAL, spaceBefore=12, spaceAfter=7))
    styles.add(ParagraphStyle('BodyM', fontName='Noto', fontSize=10, leading=15, textColor=NAVY, spaceAfter=10))
    styles.add(ParagraphStyle('SmallM', fontName='Noto', fontSize=8.3, leading=11.5, textColor=MUTED, spaceAfter=7))
    styles.add(ParagraphStyle('QuestionM', fontName='NotoBold', fontSize=10, leading=14, textColor=NAVY, spaceAfter=6))
    styles.add(ParagraphStyle('AnswerM', fontName='Noto', fontSize=9.2, leading=13, textColor=NAVY, spaceAfter=5))
    styles.add(ParagraphStyle('BadgeM', fontName='NotoBold', fontSize=8.3, leading=12, textColor=TEAL, spaceAfter=5))
    styles.add(ParagraphStyle('MetricM', fontName='NotoBold', fontSize=21, leading=28, textColor=TEAL, alignment=TA_CENTER))
    styles.add(ParagraphStyle('MetricLabelM', fontName='Noto', fontSize=8.5, leading=12, textColor=NAVY, alignment=TA_CENTER))
    width = A4[0] - 90
    story = []

    def p(text, style='BodyM'):
        return Paragraph(text, styles[style])

    def add(text, style='BodyM'):
        story.append(p(text, style))

    def table(data, widths):
        cells = [[p(escape(str(v)), 'SmallM') for v in row] for row in data]
        t = Table(cells, colWidths=widths, hAlign='LEFT', repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PALE),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, 0), 1, TEAL),
            ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#DDE6E9')),
        ]))
        story.append(t)

    s = report['summary']
    n = s['n']
    complete = round(s['coverage5'] * n)
    hit1 = round(s['hit1'] * n)
    date = datetime.fromisoformat(report['executed_at']).strftime('%d/%m/%Y à %H:%M')

    add('SPOC / ÉVALUATION DOCUMENTAIRE', 'BadgeM')
    story.append(Spacer(1, 22))
    add('Tester la recherche<br/>en espagnol', 'TitleM')
    add('Mancha 4 · 40 questions annotées', 'HeadingM')
    add(f'Mesure locale du {date} (Europe/Paris). Questions et corrigés en espagnol ; analyse et critères de contrôle en français.', 'SmallM')
    story.append(Spacer(1, 12))
    tiles = Table([
        [p(str(len(cases)), 'MetricM'), p(str(n), 'MetricM'), p(str(report['passage_count']), 'MetricM')],
        [p('questions préparées', 'MetricLabelM'), p('cas notés en retrieval', 'MetricLabelM'), p('extraits exacts indexés', 'MetricLabelM')],
    ], colWidths=[width / 3] * 3)
    tiles.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), PALE), ('TOPPADDING', (0, 0), (-1, 0), 12), ('BOTTOMPADDING', (0, 1), (-1, 1), 14)]))
    story.append(tiles)
    story.append(Spacer(1, 20))
    add('Ce que la mesure établit', 'SubM')
    add(f'<b>{complete}/{n} questions</b> retrouvent toutes leurs ancres attendues dans les cinq premiers extraits. Le premier extrait contient au moins une ancre sur <b>{hit1}/{n}</b> questions. Ces scores mesurent la localisation de preuves minimales, pas la justesse d’une réponse rédigée.')
    add('Ce qui reste à valider', 'SubM')
    add('Le serveur web et Qwen étaient inaccessibles lors du contrôle. La mesure utilise BGE-M3 et Qdrant en mémoire avec un découpage technique de la transcription. La segmentation Qwen, la reformulation et le reranking de l’application n’ont pas été mesurés.')
    add('Le prototype affiche des extraits et un bilan de pertinence ; il ne génère pas de réponse finale. Les 19 cas critiques doivent encore être relus humainement. Aucun taux d’hallucination n’est déduit de cette expérience.')
    add('Lecture rapide', 'SubM')
    add('Pages suivantes : protocole, résultats, puis 40 fiches directement utilisables. Les références de chaque fiche pointent vers les pages physiques du PDF original.', 'SmallM')
    story.append(PageBreak())

    add('01 / Protocole et barème', 'HeadingM')
    add('Une base de comparaison isolée', 'SubM')
    add('Corpus : transcription fournie des 80 pages de Mancha 4. Les annotations d’illisibilité, les pages quasi blanches et les copies du bulletin sont conservées. Le préambule de transcription n’est pas indexé. Fenêtres de 1 600 caractères par page, recouvrement de 300, texte et positions exacts. Les questions et corrigés ne sont jamais indexés.')
    add('Encodeur du projet : BAAI/bge-m3, révision 5617a9f61b028005a4858fdac845db406aefb181, vecteurs 1 024 dimensions normalisés, CPU avec quatre threads, similarité cosinus dans Qdrant temporaire. Les cinq premiers extraits sont évalués ; aucun seuil de similarité n’est assimilé à une vérité.', 'SmallM')
    add('Comment lire les scores', 'SubM')
    table([
        ['Mesure', 'Définition sur les 35 cas notés'],
        ['Hit@1 (ancre)', 'Au moins un groupe de preuves est représenté dans le premier extrait.'],
        ['Rappel des ancres@5', 'Part des groupes obligatoires retrouvés dans les cinq extraits, moyennée par question.'],
        ['Couverture@5 (ancres)', 'Toutes les ancres requises sont retrouvées dans les cinq extraits.'],
        ['MRR@5 (ancre)', 'Inverse du rang du premier extrait portant une ancre ; zéro si absent du top 5.'],
    ], [145, width - 145])
    story.append(Spacer(1, 10))
    add('Les 32 questions avec réponse et les 3 absences explicitement renseignées sont notées. Les 5 questions sans réponse dans le corpus restent hors score : leurs extraits doivent être jugés pour leur prudence. Une alternative du même groupe suffit, notamment les copies du bulletin p. 19, 31 et 35.', 'SmallM')
    add('Audit du barème : un premier essai à 25/35 omettait des formulations équivalentes pour ES01 et ES06. Elles ont été ajoutées sans changer questions, corpus, classement ou seuils. La signature p. 13 complète aussi ES30. Le jeu est diagnostique et non aveugle.', 'SmallM')
    add('Validation humaine obligatoire', 'SubM')
    add('<b>2 points</b> : informations et réserves complètes, appuyées par les extraits.<br/><b>1 point</b> : réponse partielle, sans fait inventé.<br/><b>0 point</b> : donnée essentielle absente, contradiction masquée ou affirmation non soutenue.')
    add('Repères exploratoires proposés avant lecture des scores : Hit@1 ≥ 70 %, rappel des ancres@5 ≥ 90 %, couverture@5 ≥ 85 %. Pour une validation fonctionnelle, exiger aussi zéro erreur critique sur les 19 cas signalés. Ces objectifs ne constituent pas des seuils universels.', 'SmallM')
    add('Ne jamais confirmer sans preuve une identité, une culpabilité ou un décès ; transformer une demande en résultat ; inventer un montant, un numéro de chambre ou une fin de texte illisible. Pour un cas absent du corpus, limiter la conclusion au contenu disponible.', 'SmallM')
    story.append(PageBreak())

    add('02 / Résultats observés', 'HeadingM')
    table([
        ['Indicateur', 'Valeur mesurée', 'Repère proposé'],
        ['Hit@1 (ancre)', f'{s["hit1"]:.1%} ({hit1}/{n})', '70 %'],
        ['Rappel des ancres@5', f'{s["anchor_recall5"]:.1%}', '90 %'],
        ['Couverture@5 (ancres)', f'{s["coverage5"]:.1%} ({complete}/{n})', '85 %'],
        ['MRR@5 (ancre)', f'{s["mrr5"]:.3f}', 'Descriptif'],
    ], [195, 160, width - 355])
    story.append(Spacer(1, 14))
    add('Où la recherche est incomplète', 'SubM')
    category_data = [['Famille', 'Cas notés', 'Couverture@5']]
    for name, stats in report['by_category'].items():
        category_data.append([name, stats['n'], f'{stats["coverage5"]:.0%}' if stats['n'] else 'Hors score'])
    table(category_data, [300, 85, width - 385])
    failed = [r for r in report['rows'] if r['metrics'] and not r['metrics']['coverage5']]
    add('Cas à examiner en priorité', 'SubM')
    if failed:
        add('Couverture incomplète des ancres : <b>' + ', '.join(r['id'] for r in failed) + '</b>. Les fiches indiquent les pages retrouvées et les groupes manquants. Lire les extraits avant d’attribuer l’échec au moteur : une ancre est un indicateur minimal de localisation.', 'SmallM')
    else:
        add('Toutes les ancres sont retrouvées dans les cinq extraits. La qualité de leur interprétation et des justifications reste à contrôler.', 'SmallM')
    met = s['hit1'] >= .7 and s['anchor_recall5'] >= .9 and s['coverage5'] >= .85
    add(('Les repères quantitatifs proposés sont atteints par cette base de comparaison.' if met else 'Cette base de comparaison n’atteint pas tous les repères quantitatifs proposés.') + ' Cela ne suffit pas à qualifier le RAG complet : les contrôles Qwen et les cas critiques restent ouverts.', 'SmallM')
    add(f'Temps observés : chargement {report["load_seconds"]:.1f} s ; encodage/indexation {report["index_seconds"]:.1f} s ; 40 recherches {report["search_seconds"]:.1f} s. Ces durées sont locales et ne comprennent aucun appel Qwen.', 'SmallM')
    story.append(PageBreak())

    add('03 / Diagnostic et réutilisation', 'HeadingM')
    add('Priorités de test', 'SubM')
    add('<b>En-têtes et signatures (ES04, ES30).</b> Le récit remonte, mais pas les champs d’en-tête ou les signatures nécessaires. Pour ES17, le début du bon courrier est retrouvé alors que la période vidéo demandée est dans une autre fenêtre.')
    add('<b>Recoupements incomplets (ES23, ES25, ES27, ES28).</b> Les cinq extraits ne couvrent qu’une des pièces ou versions à comparer. Les fragments répétés d’une même description occupent des places sans apporter la version contradictoire. Pour ES29, un domicile ne remplace pas le champ « lieu de l’entretien ».')
    add('<b>Robustesse et prudence.</b> ES31, la version courte de ES17, retrouve l’ancre attendue ; ES17 échoue à la couvrir. ES32 conserve le fait attendu de ES10. Tester ensuite Qwen sur les demandes sans résultat et les 19 cas critiques : ces contrôles ne sont pas exécutés ici.')
    add('Exécuter de nouveau', 'SubM')
    add('Depuis la racine du projet :<br/><font name="NotoBold">.venv/bin/python experiments/mancha4/run.py --validate-only</font><br/><font name="NotoBold">HF_HUB_OFFLINE=1 .venv/bin/python experiments/mancha4/run.py</font><br/>Puis régénérer le PDF avec <b>experiments/mancha4/report.py</b>.', 'SmallM')
    add('Quand le tunnel Qwen fonctionne, l’option <b>--qwen</b> ajoute les fonctions réelles de reformulation et reranking, avec 30 candidats et cinq sorties. Les résultats sont écrits séparément dans <b>results-qwen.json</b>. Cette option transmet les extraits au Qwen configuré et garde le découpage technique ; elle ne teste pas l’import ou la segmentation Qwen.', 'SmallM')
    add('Dans l’application', 'SubM')
    add('Poser les questions dans le dossier contenant la transcription, relever les cinq sources et le bilan Qwen, puis comparer les réserves au corrigé. Renseigner <b>manual_review</b> dans une copie des résultats : note 0 à 2, erreur critique éventuelle et commentaire. Évaluer les cinq questions sans réponse séparément du score de recherche.', 'SmallM')
    add('Limites du matériau', 'SubM')
    add('Le PDF original contient 80 pages et pèse environ 47 Mio, au-delà des 20 Mo admis par l’import web. Pypdf extrait du texte sur 45 pages ; 35 sont sans texte, ce qui bloque aussi le parcours actuel. L’essai porte sur la transcription fournie. Contrôle visuel ponctuel : p. 7, 9, 19 et 29 ; aucune relecture intégrale du PDF n’est prétendue.', 'SmallM')
    add('Corpus unique, petit jeu construit à partir du même dossier, variantes liées et répétitions : pas de garantie sur d’autres documents. OCR, séparation de dossiers, résistance aux instructions documentaires et génération finale ne sont pas évalués. Les instructions figurant dans les pièces ont été lues comme du contenu documentaire.', 'SmallM')
    add('Traçabilité', 'SubM')
    add('Les empreintes SHA-256 du corpus et des annotations, le profil exact du modèle, les 200 extraits retournés et les résultats par question sont conservés dans <b>experiments/mancha4/results.json</b>. Les corrigés et les citations minimales sont dans <b>questions.json</b>. Aucun index applicatif ni document source n’a été modifié.', 'SmallM')
    story.append(PageBreak())

    add('04 / Questions et corrigés', 'HeadingM')
    add('Les réponses ci-dessous sont des références rédigées à partir de la transcription. Elles ne sont pas des réponses générées par le RAG. Les pages citées renvoient au PDF source.', 'SmallM')
    for index, case in enumerate(cases):
        if index and index % 3 == 0:
            story.append(PageBreak())
            add(f'Questions et corrigés / {case["id"]} à ES{min(index + 3, 40):02}', 'HeadingM')
        row = rows[case['id']]
        pages = sorted({page for group in case['evidence_groups'] for alt in group for page in alt['pages']})
        source_label = ', '.join(map(str, pages)) if pages else 'corpus complet : aucune pièce répondant à la demande'
        critical = ' · CRITIQUE' if case['critical'] else ''
        block = [p(escape(f'{case["id"]} / {case["category"]} · {case["difficulty"]}{critical}'), 'BadgeM')]
        block += [p(escape(case['question_es']), 'QuestionM'),
                  p('<b>Référence (ES).</b> ' + escape(case['expected_answer_es']), 'AnswerM'),
                  p('<b>À contrôler.</b> ' + escape(case['pitfalls_fr']), 'SmallM'),
                  p('<b>Sources, p.</b> ' + escape(source_label), 'SmallM')]
        if row['metrics']:
            m = row['metrics']
            outcome = f'Ancres@5 : {len(m["found_groups"])}/{len(case["evidence_groups"])} groupes ; ancre au rang 1 : {"oui" if m["hit1"] else "non"}.'
            if m['missing_groups']:
                outcome += ' Groupes manquants : ' + ', '.join(map(str, m['missing_groups'])) + ' (voir JSON).'
        else:
            outcome = 'Hors score de recherche : prudence et absence de réponse à vérifier humainement.'
        retrieved = ', '.join(str(r['page_start']) for r in row['results'])
        block.append(p(escape(outcome + ' Pages top 5 : ' + retrieved + '.'), 'SmallM'))
        if case['variant_of']:
            block.append(p('Variante à comparer à <b>' + case['variant_of'] + '</b>.', 'SmallM'))
        block.append(HRFlowable(width='100%', thickness=.5, color=colors.HexColor('#DDE6E9'), spaceBefore=4, spaceAfter=12))
        story.append(KeepTogether(block))

    def frame(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(TEAL)
        canvas.rect(0, A4[1] - 9, A4[0], 9, fill=1, stroke=0)
        canvas.setFont('Noto', 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(45, 25, 'MANCHA 4 / Questions en espagnol / Mesure BGE-M3 locale')
        canvas.drawRightString(A4[0] - 45, 25, str(doc.page))
        canvas.restoreState()

    DEST.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(DEST), pagesize=A4, leftMargin=45, rightMargin=45,
                            topMargin=42, bottomMargin=43,
                            title='Évaluation RAG en espagnol - Mancha 4',
                            author='SPOC - Évaluation documentaire')
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    print(DEST)


if __name__ == '__main__':
    main()
