import streamlit as st
from client import generate_content
from .models import ExtractionResult
from .prompts import get_entity_extraction_prompt, get_relation_extraction_prompt, get_combined_extraction_prompt

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
    """Combined Extraction: Entities and Relationships in one pass"""
    
    # Combined Extraction Step
    prompt_combined = get_combined_extraction_prompt(text, _build_type_constraints())
    
    res_combined = ""
    try:
        res_combined = generate_content(prompt_combined, ExtractionResult)
        result = ExtractionResult.model_validate_json(res_combined)
        return result
    except Exception as e:
        print(f"DEBUG: Combined Extraction Failed. Raw response start: {res_combined[:500]}")
        st.error(f"Extraction Error: {e}")
        return ExtractionResult(entities=[], relationships=[])
