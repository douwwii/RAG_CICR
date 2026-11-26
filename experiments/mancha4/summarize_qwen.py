"""Compte rendu comparatif des mesures Qwen effectivement exécutées."""
import hashlib
import json
from collections import Counter
from html import escape
from pathlib import Path
from statistics import median

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    base = json.loads((HERE / 'results.json').read_text())
    run = json.loads((HERE / 'results-qwen.json').read_text())
    annotations = json.loads((HERE / 'questions.json').read_text())
    assert run['questions_sha256'] == hashlib.sha256((HERE / 'questions.json').read_bytes()).hexdigest()
    assert run['transcript_sha256'] == base['transcript_sha256']
    assert len(run['rows']) == 40
    rows = run['rows']
    before = {r['id']: r for r in base['rows']}
    stats = Counter(r['reranking']['status'] for r in rows)
    def pct(v):
        return f'{100*v:.1f} %'.replace('.', ',')
    font = Path('/usr/share/fonts/google-noto')
    pdfmetrics.registerFont(TTFont('QN', str(font / 'NotoSans-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('QB', str(font / 'NotoSans-Bold.ttf')))
    navy = colors.HexColor('#173347')
    teal = colors.HexColor('#087F8C')
    styles = {
        'title': ParagraphStyle('title', fontName='QB', fontSize=22, leading=29, textColor=navy, spaceAfter=16),
        'h': ParagraphStyle('h', fontName='QB', fontSize=13, leading=18, textColor=teal, spaceBefore=14, spaceAfter=8),
        'body': ParagraphStyle('body', fontName='QN', fontSize=10, leading=15, textColor=navy, spaceAfter=10),
        'small': ParagraphStyle('small', fontName='QN', fontSize=8, leading=11, textColor=navy, spaceAfter=3),
    }
    def p(text, style='body'):
        return Paragraph(escape(str(text)), styles[style])
    story = []
    def table(data, widths):
        t = Table([[p(c, 'small') for c in row] for row in data], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EEF5F6')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#DDE6E9'))]))
        story.append(t)
    story += [p('Mancha 4 / Test avec Qwen', 'title'), p('Exécution : '+run['executed_at'], 'small')]
    story += [p('Verdict sur les preuves retrouvées', 'h')]
    n=run['summary']['n']
    story += [p(f"Qwen restitue toutes les ancres attendues dans les cinq extraits pour {round(run['summary']['coverage5']*n)}/{n} cas notés, contre {round(base['summary']['coverage5']*n)}/{n} pour BGE-M3 seul. Les cinq questions sans réponse sont évaluées séparément. Les ancres indiquent une couverture documentaire minimale, pas une réponse intégralement correcte.")]
    table([['Mesure','BGE seul','Reformulation + Qwen']]+[[label,pct(base['summary'][key]),pct(run['summary'][key])] for key,label in [('hit1','Ancre au premier rang'),('anchor_recall5','Rappel des ancres à cinq'),('coverage5','Toutes les ancres à cinq')]], [225,110,170])
    story += [p('Fonctionnement effectivement observé', 'h'),p(f"Reclassement : {dict(stats)}. Questions reformulées avec un texte différent : {sum(r['query'] != r['question_es'] for r in rows)}/40. Ce nombre ne distingue pas une reformulation volontairement identique d'un repli. Durée médiane par question : {median(r['seconds'] for r in rows):.1f} s ; durée cumulée des 40 recherches : {run['search_seconds']:.1f} s.")]
    improved=[r['id'] for r in rows if r['metrics'] and r['metrics']['coverage5'] and not before[r['id']]['metrics']['coverage5']]
    regressed=[r['id'] for r in rows if r['metrics'] and not r['metrics']['coverage5'] and before[r['id']]['metrics']['coverage5']]
    story += [p('Cas devenus complets : '+(', '.join(improved) or 'aucun')+'.'),p('Cas devenus incomplets : '+(', '.join(regressed) or 'aucun')+'.')]
    story += [p('Périmètre', 'h'),p('Modèle : qwen3.8:27b-mlx, sans délai maximal de réponse, à la demande de l’utilisateur. Fonctions réelles de reformulation et de reranking, 30 candidats, cinq sorties. Corpus et découpage technique identiques à l’essai BGE. Aucun index applicatif modifié. La segmentation Qwen et le parcours web ne sont pas testés. Le prototype sélectionne des extraits et rédige des justifications de pertinence ; il ne produit pas de réponse finale.')]
    for start in (0,20):
        story += [PageBreak(),p(f'Résultats détaillés / {start+1} à {start+20}', 'title')]
        data=[['Cas','BGE seul','Après reformulation','Après Qwen','Bilan Qwen']]
        for row in rows[start:start+20]:
            def label(m):
                return 'Hors score' if m is None else ('Complet' if m['coverage5'] else f"Partiel ({m['anchor_recall5']:.0%})")
            data.append([row['id'],label(before[row['id']]['metrics']),label(row['baseline_metrics']),label(row['metrics']),(row['assessment'] or {}).get('coverage','indisponible')])
        table(data,[45,100,125,110,125])
        story += [Spacer(1,12),p('« Complet » signifie que toutes les ancres annotées sont présentes, et non que toutes les réserves ont été comprises. « Direct », « partial », « none » et « contradictory » sont les jugements de Qwen, pas des notes humaines.', 'small')]
    review_path = HERE / 'review-qwen.json'
    if review_path.exists():
        review=json.loads(review_path.read_text())
        story += [PageBreak(),p('Contrôle qualitatif des justifications', 'title'),p(review['scope'])]
        for item in review['findings']:
            story += [p(item['cases']+' / '+item['verdict'],'h'),p(item['detail'])]
        story += [p('Conclusion', 'h'),p(review['conclusion'])]
    destination=ROOT / 'output/pdf/evaluation-qwen-mancha4.pdf'
    def frame(canvas,doc):
        canvas.setFillColor(teal);canvas.rect(0,A4[1]-8,A4[0],8,fill=1,stroke=0)
        canvas.setFont('QN',8);canvas.setFillColor(navy)
        canvas.drawString(45,25,'SPOC / Mancha 4 / Comparaison BGE et Qwen')
        canvas.drawRightString(A4[0]-45,25,str(doc.page))
    SimpleDocTemplate(str(destination),pagesize=A4,leftMargin=45,rightMargin=45,topMargin=43,bottomMargin=45,title='Mancha 4 - Évaluation Qwen').build(story,onFirstPage=frame,onLaterPages=frame)
    print(destination)


if __name__ == '__main__':
    main()
