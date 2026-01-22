from validation.rules_registry import register_rule
from extraction.models import ExtractedRelationship

@register_rule
def block_invalid_is_a(rel: ExtractedRelationship):
    if rel.machine_name == "is_a":
        evidence = (rel.evidence_span or "").lower()
        type_words = ["is a", "belongs to", "type of", "kind of", "class of"]
        if not any(w in evidence for w in type_words):
            print(f"⚠️ Blocked invalid is_a: {rel.machine_name} evidence={evidence[:50]}...")
            return False
    return True

@register_rule
def block_question_evidence(rel: ExtractedRelationship):
    text = (rel.evidence_span or "").strip()
    if text.endswith("?") or text.lower().startswith(("does", "is", "are", "can")):
        print(f"⚠️ Block relation from question evidence: {text[:50]}...")
        return False
    return True