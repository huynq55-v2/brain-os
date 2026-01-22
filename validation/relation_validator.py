from extraction.models import ExtractedRelationship
from ontology.relation_types import RelationshipType
from ontology.schema import EntityNode

def validate_extracted_relationship(rel: ExtractedRelationship, rel_type: RelationshipType,
                                    source_entity: EntityNode, target_entity: EntityNode) -> bool:
    # 1. Check entity type
    if rel_type.allowed_entity_types:
        src_allowed = rel_type.allowed_entity_types.get("source", [])
        tgt_allowed = rel_type.allowed_entity_types.get("target", [])
        # EntityNode.type is Enum
        if source_entity.type not in src_allowed: 
             print(f"Source Type Mismatch: {source_entity.type} not in {src_allowed}")
             return False
        if target_entity.type not in tgt_allowed:
             print(f"Target Type Mismatch: {target_entity.type} not in {tgt_allowed}")
             return False

    # 2. Check semantic properties schema
    if rel_type.properties_schema:
        for key, schema in rel_type.properties_schema.items():
            if key not in rel.semantic_properties:
                print(f"Missing Property: {key}")
                return False
            if schema.get("type") == "enum":
                if rel.semantic_properties[key] not in schema.get("values", []):
                    print(f"Invalid Enum: {key}={rel.semantic_properties[key]}")
                    return False
    return True

from validation.rules_registry import VALIDATION_RULES
# Import rules to ensure they are registered
import validation.validation_rules
from validation.ontology_confidence import calculate_ontology_confidence

def run_all_validation_rules(rel: ExtractedRelationship) -> bool:
    """Run all registered validation rules."""
    for rule in VALIDATION_RULES:
        if not rule(rel):
            return False
    return True

def full_relation_validation(rel: ExtractedRelationship, rel_type: RelationshipType, 
                             source_entity: EntityNode, target_entity: EntityNode) -> bool:
    """
    Master validation pipeline:
    1. Registered Validation Rules (Pre-check)
    2. Ontology Confidence Scoring (Must be >= 0.5)
    3. Schema Validation (Types, Properties)
    """
    
    # 1. Pre-validation rules (Hard blocks like 'is_a' misuse, question evidence)
    if not run_all_validation_rules(rel):
        return False

    # 2. Ontology Confidence
    # We use a threshold of 0.5 as established in sqlite_adapter
    conf = calculate_ontology_confidence(rel, rel_type, source_entity, target_entity)
    if conf < 0.5:
        print(f"⛔ Ontology Confidence Rejected: {conf}")
        return False

    # 3. Schema / Type Validation
    if not validate_extracted_relationship(rel, rel_type, source_entity, target_entity):
        return False

    return True
