from extraction.models import ExtractedRelationship
from ontology.relation_types import RelationshipType
from ontology.schema import EntityNode
from ontology.ontology_rules import ONTOLOGY_CONSTRAINTS, HEURISTIC_RULES, EVIDENCE_RULES

def calculate_ontology_confidence(rel: ExtractedRelationship, rel_type: RelationshipType, 
                                  src: EntityNode, tgt: EntityNode) -> float:
    score = 1.0
    reasons = []
    
    # 1. Hard Constraints
    for rule in ONTOLOGY_CONSTRAINTS:
        s, reason = rule.evaluate(rel, rel_type, src, tgt)
        if s == 0.0:
            # Immediate rejection
            print(f"⛔ Constraint Violated: {rule.id}: {reason}")
            return 0.0 
        
        if s < 1.0:
             score = min(score, s)
             if reason: reasons.append(f"[Constraint] {rule.id}: {reason}")

    # 2. Heuristics
    for rule in HEURISTIC_RULES:
        s, reason = rule.evaluate(rel, rel_type, src, tgt)
        if s < 1.0:
            score = min(score, s)
            if reason: reasons.append(f"[Heuristic] {rule.id}: {reason}")

    # 3. Evidence
    for rule in EVIDENCE_RULES:
        s, reason = rule.evaluate(rel, rel_type, src, tgt)
        if s < 1.0:
             # Evidence rules might be softer, but we use min for now strictly
             score = min(score, s)
             if reason: reasons.append(f"[Evidence] {rule.id}: {reason}")

    if score < 1.0:
        print(f"⚠️ Ontology Confidence: {rel.machine_name} score={score}. Reasons: {reasons}")
    return score
