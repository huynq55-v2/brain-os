import streamlit as st
from textwrap import dedent
from client import generate_content
from extraction.models import SynthesisResult, ExtractedEntity
from ontology.schema import EntityNode

def synthesize_entity_info(current_entity: EntityNode, new_info: ExtractedEntity) -> SynthesisResult:
    """Merge old and new information"""
    
    prompt = dedent(f"""
        Merge knowledge for the entity: "{current_entity.name}".
        
        1. Old data: "{current_entity.description}" 
           (Keywords: {current_entity.keywords})
        2. New data: "{new_info.description}" 
           (Keywords: {new_info.keywords})
        
        Task: Write a new synthesized description, preserving historical information, adding new details, and removing duplicates.
    """).strip()
    
    response = ""
    try:
        response = generate_content(prompt, SynthesisResult)
        return SynthesisResult.model_validate_json(response)
    except Exception as e:
        print(f"DEBUG: Synthesis Failed. Raw response: {response[:500]}")
        st.error(f"Merge error: {e}")
        return SynthesisResult(new_description=current_entity.description, new_keywords=current_entity.keywords)
