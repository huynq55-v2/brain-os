from typing import Callable, Tuple, List, Optional
from extraction.models import ExtractedRelationship
from ontology.relation_types import RelationshipType
from ontology.schema import EntityNode

class OntologyRule:
    def __init__(self, id, description, check_fn):
        self.id = id
        self.description = description
        self.check_fn = check_fn
        
    def evaluate(self, rel: ExtractedRelationship, rel_type: RelationshipType, src: EntityNode, tgt: EntityNode):
        return self.check_fn(rel, rel_type, src, tgt)

# Lists to hold registered rules
ONTOLOGY_CONSTRAINTS = []
HEURISTIC_RULES = []
EVIDENCE_RULES = []

def register_rule(target_list):
    def decorator(fn):
        # Infer ID from function name (e.g., r1_... -> R1)
        # If strict format r<number>_name, use R<number>. Else use full name.
        parts = fn.__name__.split('_')
        if parts and parts[0].startswith('r') and parts[0][1:].isdigit():
             rule_id = parts[0].upper()
             # Fallback description from function name if docstring missing
             default_desc = " ".join(parts[1:]).replace('_', ' ').capitalize()
        else:
             rule_id = fn.__name__
             default_desc = fn.__name__

        description = fn.__doc__.strip() if fn.__doc__ else default_desc
        
        target_list.append(OntologyRule(rule_id, description, fn))
        return fn
    return decorator

# Wrappers for specific lists
def ontology_constraint(fn):
    return register_rule(ONTOLOGY_CONSTRAINTS)(fn)

def heuristic_rule(fn):
    return register_rule(HEURISTIC_RULES)(fn)

def evidence_rule(fn):
    return register_rule(EVIDENCE_RULES)(fn)

# --- HARD CONSTRAINTS ---

@ontology_constraint
def r1_instance_target_concept(rel, rt, s, t):
    """Instance_of target Concept"""
    if rt.machine_name == "instance_of" and t.type != "Concept": return 0.0, "Target must be Concept"
    return 1.0, None

@ontology_constraint
def r2_subclass_concept(rel, rt, s, t):
    """Subclass_of requests Concept->Concept"""
    if rt.machine_name == "subclass_of" and (s.type != "Concept" or t.type != "Concept"): return 0.0, "Requires Concept->Concept"
    return 1.0, None

@ontology_constraint
def r5_deterministic_prob(rel, rt, s, t):
    """Deterministic prob=1.0"""
    if rt.deterministic:
        prob = rel.semantic_properties.get("probability")
        if isinstance(prob, (int, float)) and prob < 1.0: return 0.0, "Deterministic means prob 1.0"
    return 1.0, None

@ontology_constraint
def r6_temporal_lag(rel, rt, s, t):
    """Temporal requires lag"""
    if rt.category == "temporal" and "temporal_lag" not in rel.semantic_properties: return 0.0, "Missing temporal_lag"
    return 1.0, None

@ontology_constraint
def r10_hypothesis_deterministic(rel, rt, s, t):
    """Hypothesis non-deterministic"""
    # Note: usage_context is now an Enum in ExtractedRelationship
    if rel.usage_context.value == "hypothesis" and rt.deterministic: return 0.0, "Hypothesis cannot be deterministic"
    return 1.0, None

# --- HEURISTIC RULES (Soft) ---

@heuristic_rule
def r3_causal_target_person(rel, rt, s, t):
    """Causal cannot target Person"""
    if rt.category == "causal" and t.type == "Person": return 0.5, "Causal target Person (Heuristic)"
    return 1.0, None

@heuristic_rule
def r7_concept_act(rel, rt, s, t):
    """Concept cannot Act"""
    if s.type == "Concept" and rt.machine_name in ["causes", "teaches", "performs"]: return 0.5, "Concept cannot Act (Heuristic)"
    return 1.0, None

@heuristic_rule
def r8_teaches_agent(rel, rt, s, t):
    """Teaches requires Agent source"""
    if rt.machine_name == "teaches" and s.type not in ["Person", "Organization"]: return 0.5, "Teacher must be Agent (Heuristic)"
    return 1.0, None

@heuristic_rule
def r4_imperative_evidence(rel, rt, s, t):
    """Imperative evidence vs performs"""
    # Detect imperative cues in English
    span_lower = rel.evidence_span.lower()
    imperative_cues = ["practice ", "do not ", "don't ", "try to ", "let us ", "you must ", "should "]
    if rt.machine_name == "performs" and any(cue in span_lower for cue in imperative_cues):
        return 0.3, "Imperative/Advice evidence implies no factual 'performs'"
    return 1.0, None

@heuristic_rule
def r11_is_a_evidence_check(rel, rt, s, t):
    """Evidence must explicitly indicate type"""
    if rt.machine_name == "is_a":
        evidence = (rel.evidence_span or "").lower()
        type_words = ["is a", "belongs to", "type of", "kind of", "class of"]
        if not any(w in evidence for w in type_words):
            return 0.0, "Evidence does not support is_a"
    return 1.0, None

# --- EVIDENCE RULES ---

@evidence_rule
def r9_evidence_names(rel, rt, s, t):
    """Evidence mentions entities"""
    span = rel.evidence_span.lower()
    if s.name.lower() not in span or t.name.lower() not in span: return 0.6, "Evidence missing entity names"
    return 1.0, None
