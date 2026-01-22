import re
from difflib import SequenceMatcher
from ontology.schema import EntityNode

def normalize_entity_name(name: str) -> str:
    return name.lower().strip()

def get_tokens(text):
    # Simple regex word tokenizer
    return set(re.findall(r'\b\w+\b', text.lower()))

def calculate_entity_similarity(e1: EntityNode, e2: EntityNode) -> dict:
    # 1. Name Similarity (Weight 50%)
    name_sim = SequenceMatcher(None, e1.name.lower(), e2.name.lower()).ratio()
    
    # 2. Desc Similarity (Weight 30%)
    d1 = get_tokens(e1.description)
    d2 = get_tokens(e2.description)
    
    if not d1 or not d2: desc_sim = 0.0
    else: desc_sim = len(d1 & d2) / len(d1 | d2)
    
    # 3. Keywords Similarity (Weight 20%)
    k1 = set([k.lower() for k in e1.keywords])
    k2 = set([k.lower() for k in e2.keywords])
    if not k1 or not k2: kw_sim = 0.0
    else: kw_sim = len(k1 & k2) / len(k1 | k2)
    
    total = (name_sim * 0.5) + (desc_sim * 0.3) + (kw_sim * 0.2)
    return {
        "total": total,
        "name": name_sim,
        "desc": desc_sim,
        "keywords": kw_sim
    }
