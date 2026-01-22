import streamlit as st
from client import generate_content
from .models import ExtractionResult
from .prompts import get_entity_extraction_prompt, get_relation_extraction_prompt

def _build_type_constraints() -> str:
    type_list = []
    if "relationship_types" in st.session_state and st.session_state.relationship_types:
        for t in st.session_state.relationship_types.values():
            if t.deprecated: continue
            info = f"- {t.machine_name} ({t.category}): {t.description}."
            if t.allowed_entity_types:
                info += f" Source: {t.allowed_entity_types.get('source')}. Target: {t.allowed_entity_types.get('target')}."
            type_list.append(info)
    return "\n".join(type_list) if type_list else "No predefined types."

def extract_data(text: str) -> ExtractionResult:
    """Two-Step Extraction: 1. Entities, 2. Relationships"""
    
    # STEP 1: Extract Entities
    prompt_entities = get_entity_extraction_prompt(text)
    
    res_ent = ""
    try:
        res_ent = generate_content(prompt_entities, ExtractionResult)
        result1 = ExtractionResult.model_validate_json(res_ent)
    except Exception as e:
        print(f"DEBUG: Entity Extraction Failed. Raw response start: {res_ent[:500]}")
        st.error(f"Entity Extraction Error: {e}")
        return ExtractionResult(entities=[], relationships=[])
        
    extracted_entities = result1.entities
    if not extracted_entities:
        return ExtractionResult(entities=[], relationships=[])

    # STEP 2: Extract Relations
    entities_ctx = "\n".join([f"- {e.name} ({e.type})" for e in extracted_entities])
    type_constraints = _build_type_constraints()
    
    prompt_rels = get_relation_extraction_prompt(text, entities_ctx, type_constraints)
    
    res_rel = ""
    try:
        res_rel = generate_content(prompt_rels, ExtractionResult)
        result2 = ExtractionResult.model_validate_json(res_rel)
    except Exception as e:
        print(f"DEBUG: Relation Extraction Failed. Raw response start: {res_rel[:500]}")
        st.error(f"Relationship Extraction Error: {e}")
        return ExtractionResult(entities=extracted_entities, relationships=[])

    # Combine
    return ExtractionResult(entities=extracted_entities, relationships=result2.relationships)
