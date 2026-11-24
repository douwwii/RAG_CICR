"""Mesures sur annotations indépendantes du juge Qwen."""
import math
def metrics(hits,c):
 grades=[c['grades'].get(h['passage_id'],0) for h in hits]
 ideal=sorted(c['grades'].values(),reverse=True)[:5]
 dcg=lambda values:sum((2**v-1)/math.log2(i+2) for i,v in enumerate(values))
 return dict(hit1=bool(grades and grades[0]>=2),ndcg5=dcg(grades)/dcg(ideal) if dcg(ideal) else None,
             coverage5=bool(c['required']) and set(c['required'])<={h['passage_id'] for h in hits},
             answer_passages=sum(g>=2 for g in grades),irrelevant=sum(g==0 for g in grades))
