"""Bornes proposées par Qwen, contenu reconstruit exclusivement depuis la source."""
import re
from segmentation_schemas import SegmentationProposal


def recover_boundaries(source, response):
    proposal = SegmentationProposal.model_validate_json(response)
    positions = [i for i, char in enumerate(source) if not char.isspace()]
    compact = ''.join(source[i] for i in positions)
    starts, cursor, gaps = [], 0, []
    for p in proposal.passages:
        text = ''.join(p.text.split())
        if not text:
            raise ValueError('Proposition vide.')
        at = compact.find(text, cursor)
        if at < 0:
            raise ValueError('Texte modifié ou ordre incohérent.')
        gaps.append(at - cursor)
        starts.append(positions[at])
        cursor = at + len(text)
    bounds = [0, *starts[1:], len(source)]
    items = [dict(title=p.title, text=source[a:b], start=a, end=b)
             for p,a,b in zip(proposal.passages,bounds[:-1],bounds[1:],strict=True)]
    # Un intertitre isolé accompagne le passage suivant, indépendamment des questions.
    result = []
    pending = None
    for p in items:
        if pending:
            p = dict(p, start=pending['start'], text=source[pending['start']:p['end']])
            pending = None
        if len(p['text'].strip()) < 120 and not re.search(r'[.!?][\s]*$', p['text']):
            pending = p
        else:
            result.append(p)
    if pending:
        if result:
            result[-1] = dict(result[-1], end=pending['end'], text=source[result[-1]['start']:pending['end']])
        else:
            result.append(pending)
    assert ''.join(p['text'] for p in result) == source
    return result, sum(gaps) + len(compact) - cursor
