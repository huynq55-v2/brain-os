import streamlit as st
import sqlite3
from storage.sqlite_adapter import init_session_state, load_data_from_db, init_db
from ui.streamlit_views import (
    render_input_data, render_view_knowledge, render_view_entities,
    render_view_relation_types, render_view_relationships, render_view_evidence, 
    render_entity_deduplication, render_ontology_import
)

st.set_page_config(page_title="Brain OS - Knowledge Graph", layout="wide")
st.title("🧠 Brain OS: Knowledge Ontology System")

def main():
    init_db() # Ensure tables exist
    init_session_state()
    # Load data on first run
    if not st.session_state.entities:
        with st.spinner("Loading Knowledge Graph..."):
            load_data_from_db()
    
    # Navigation
    menu = st.sidebar.radio("Mode", [
        "📥 Input Data", 
        "📚 View Knowledge", 
        "🧬 View Entities", 
        "🔗 View Relation Types", 
        "🕸️ View Relationships", 
        "🔍 View Evidence", 
        "⚙️ Ontology Import", 
        "🧩 Entity Deduplication"
    ])
    
    if menu == "⚙️ Ontology Import":
        render_ontology_import()
    elif menu == "📥 Input Data":
        render_input_data()
    elif menu == "📚 View Knowledge":
        render_view_knowledge()
    elif menu == "🧬 View Entities":
        render_view_entities()
    elif menu == "🔗 View Relation Types":
        render_view_relation_types()
    elif menu == "🕸️ View Relationships":
        render_view_relationships()
    elif menu == "🔍 View Evidence":
        render_view_evidence()
    elif menu == "🧩 Entity Deduplication":
        render_entity_deduplication()

if __name__ == "__main__":
    main()