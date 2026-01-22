import sqlite3
import json
import uuid
import streamlit as st
from datetime import datetime
from typing import List

from ontology.schema import EntityNode, KnowledgeEntry, Evidence, RelationAssertion
from ontology.relation_types import RelationshipType
from ontology.enums import EntityType
from extraction.extractor import extract_data
from extraction.synthesis import synthesize_entity_info
from extraction.similarity import normalize_entity_name
from extraction.models import SynthesisResult
from validation.relation_validator import validate_extracted_relationship
from validation.ontology_confidence import calculate_ontology_confidence

DB_PATH = "knowledge_base.db"

def init_session_state():
    if "entities" not in st.session_state: st.session_state.entities = {}
    if "knowledges" not in st.session_state: st.session_state.knowledges = []
    if "relationship_types" not in st.session_state: st.session_state.relationship_types = {}
    if "evidence" not in st.session_state: st.session_state.evidence = {}
    if "relation_assertions" not in st.session_state: st.session_state.relation_assertions = []

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS entities
                 (id TEXT PRIMARY KEY, name TEXT, description TEXT, keywords TEXT, source_knowledge_ids TEXT)''')
    
    # Entitiy Migrations
    cols = [
        ("type", "TEXT"), ("confidence", "REAL"),
        ("doctrinal_context", "TEXT"), ("goals", "TEXT"), ("non_goals", "TEXT")
    ]
    for col, dtype in cols:
        try: c.execute(f"ALTER TABLE entities ADD COLUMN {col} {dtype}")
        except: pass

    c.execute('''CREATE TABLE IF NOT EXISTS knowledge
                 (id TEXT PRIMARY KEY, content_raw TEXT, timestamp TEXT, related_entity_ids TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS evidence
                 (id TEXT PRIMARY KEY, source_knowledge_id TEXT, text_span TEXT)''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS relationship_types
                 (id TEXT PRIMARY KEY, machine_name TEXT, description TEXT, category TEXT, 
                  directional INTEGER, deterministic INTEGER, allowed_entity_types TEXT, properties_schema TEXT,
                  version TEXT, deprecated INTEGER)''')

    # Rename old table if exists
    try:
        c.execute("ALTER TABLE relationship_instances RENAME TO relation_assertions")
    except: pass

    c.execute('''CREATE TABLE IF NOT EXISTS relation_assertions 
                 (id TEXT PRIMARY KEY, knowledge_id TEXT, relationship_type_id TEXT, 
                  source_entity_id TEXT, target_entity_id TEXT, usage_context TEXT, 
                  semantic_properties TEXT, evidence_ids TEXT, extraction_confidence REAL, 
                  system_confidence REAL, status TEXT, created_at TEXT)''')

    # Relation Migrations
    r_cols = [("ontology_confidence", "REAL"), ("axis", "TEXT"), ("polarity", "TEXT")]
    for col, dtype in r_cols:
        try: c.execute(f"ALTER TABLE relation_assertions ADD COLUMN {col} {dtype}")
        except: pass

    # Seed Default Relationships
    c.execute("SELECT count(*) FROM relationship_types")
    if c.fetchone()[0] == 0:
        defaults = [
            ("is_a", "Hierarchical classification (A is a type of B)", "hierarchical"),
            ("part_of", "Compositional relationship (A is part of B)", "hierarchical"),
            ("causes", "Causal link (A causes B)", "causal"),
            ("associated_with", "General correlation or association", "associative"),
            ("teaches", "Didactic component", "social"),
            ("performs", "Action execution", "action"),
            ("instance_of", "Specific instance of a concept", "hierarchical"),
            ("subclass_of", "Specific subclass of a concept", "hierarchical"),
        ]
        for name, desc, cat in defaults:
            rid = str(uuid.uuid4())
            c.execute("INSERT INTO relationship_types (id, machine_name, description, category, directional, deterministic) VALUES (?, ?, ?, ?, 1, 0)", 
                      (rid, name, desc, cat))
    
    conn.commit()
    conn.close()

def load_data_from_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 0. Load Evidence
    c.execute("SELECT * FROM evidence")
    st.session_state.evidence = {row['id']: row['text_span'] for row in c.fetchall()}

    # 1. Load Types
    c.execute("SELECT * FROM relationship_types")
    r_types = {}
    for row in c.fetchall():
        try:allowed = json.loads(row['allowed_entity_types']) if row['allowed_entity_types'] else None
        except: allowed = None
        try: props = json.loads(row['properties_schema']) if row['properties_schema'] else None
        except: props = None
        
        rt = RelationshipType(
            id=row['id'], machine_name=row['machine_name'], description=row['description'],
            category=row['category'] if row['category'] else "General",
            directional=bool(row['directional']), deterministic=bool(row['deterministic']),
            allowed_entity_types=allowed, properties_schema=props,
            version=row['version'] if 'version' in row.keys() and row['version'] else "1.0",
            deprecated=bool(row['deprecated']) if 'deprecated' in row.keys() and row['deprecated'] else False
        )
        r_types[row['id']] = rt
    st.session_state.relationship_types = r_types

    # 2. Load Entities
    c.execute("SELECT * FROM entities")
    entities = {}
    for row in c.fetchall():
        # Handle JSON fields
        goals = json.loads(row['goals']) if 'goals' in row.keys() and row['goals'] else []
        non_goals = json.loads(row['non_goals']) if 'non_goals' in row.keys() and row['non_goals'] else []
        
        ent = EntityNode(
            id=row['id'], name=row['name'], 
            type=row['type'] if row['type'] else EntityType.CONCEPT,
            description=row['description'], keywords=json.loads(row['keywords']),
            source_knowledge_ids=json.loads(row['source_knowledge_ids']),
            doctrinal_context=row['doctrinal_context'] if 'doctrinal_context' in row.keys() else None,
            goals=goals, non_goals=non_goals
        )
        entities[row['id']] = ent
    st.session_state.entities = entities

    # 3. Load Knowledge
    c.execute("SELECT * FROM knowledge")
    knowledges = []
    for row in c.fetchall():
        k = KnowledgeEntry(
            id=row['id'], content_raw=row['content_raw'], 
            timestamp=datetime.fromisoformat(row['timestamp']),
            related_entity_ids=json.loads(row['related_entity_ids'])
        )
        knowledges.append(k)
    st.session_state.knowledges = knowledges
    
    # 4. Load Relations
    c.execute("SELECT * FROM relation_assertions")
    # Need to verify if table is correct (migration happened in init_db)
    relations = []
    for row in c.fetchall():
        ev_ids = json.loads(row['evidence_ids']) if row['evidence_ids'] else []
        oc = row['ontology_confidence'] if 'ontology_confidence' in row.keys() and row['ontology_confidence'] is not None else 1.0
        axis = row['axis'] if 'axis' in row.keys() else None
        polarity = row['polarity'] if 'polarity' in row.keys() else None

        ri = RelationAssertion(
            id=row['id'], knowledge_id=row['knowledge_id'], relationship_type_id=row['relationship_type_id'],
            source_entity_id=row['source_entity_id'], target_entity_id=row['target_entity_id'],
            usage_context=row['usage_context'], 
            semantic_properties=json.loads(row['semantic_properties']),
            evidence_ids=ev_ids,
            extraction_confidence=row['extraction_confidence'], ontology_confidence=oc,
            system_confidence=row['system_confidence'], status=row['status'],
            created_at=row['created_at'], axis=axis, polarity=polarity
        )
        relations.append(ri)
    st.session_state.relation_assertions = relations
    
    conn.close()

def create_relationship_type(machine_name, description):
    # Check if exists
    for r in st.session_state.relationship_types.values():
        if r.machine_name == machine_name:
            st.warning(f"Type '{machine_name}' already exists.")
            return

    new_id = str(uuid.uuid4())
    rt = RelationshipType(id=new_id, machine_name=machine_name, description=description, category="General")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO relationship_types (id, machine_name, description, category, directional, deterministic) 
                 VALUES (?, ?, ?, ?, ?, ?)''', 
              (new_id, machine_name, description, "General", 1, 0))
    conn.commit()
    conn.close()
    
    st.session_state.relationship_types[new_id] = rt
    st.success(f"Created relationship type: {machine_name}")

def update_relationship_type(id, description):
    if id in st.session_state.relationship_types:
        st.session_state.relationship_types[id].description = description
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE relationship_types SET description = ? WHERE id = ?", (description, id))
        conn.commit()
        conn.close()
        st.success("Updated!")

def delete_relationship_type(type_id):
    if type_id in st.session_state.relationship_types:
        del st.session_state.relationship_types[type_id]
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM relationship_types WHERE id = ?", (type_id,))
        # Delete dependencies
        c.execute("DELETE FROM relation_assertions WHERE relationship_type_id = ?", (type_id,))
        conn.commit()
        conn.close()
        
        # Update session state relations
        st.session_state.relation_assertions = [u for u in st.session_state.relation_assertions if u.relationship_type_id != type_id]
        st.success("Deleted type and associated instances.")

def save_knowledge_flow(text: str):
    # 1. Extract
    result = extract_data(text)
    if not result.entities:
        st.warning("No entities found.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Buffers for atomic session update
    new_entities_buffer = {}
    new_relations_buffer = []
    new_evidence_buffer = {}
    
    try:
        # 2. Save Knowledge Entry
        new_knowledge = KnowledgeEntry(content_raw=text)
        
        # 3. Process Entities
        final_entity_ids = []
        entity_name_map = {} # norm_name -> id
        entity_conf_map = {} # norm_name -> confidence
    
        progress_text = "Saving entities..."
        my_bar = st.progress(0, text=progress_text)
        total_ent = len(result.entities)

        for idx, raw in enumerate(result.entities):
            norm_name = normalize_entity_name(raw.name)
            entity_conf_map[norm_name] = raw.confidence
            
            # ALWAYS CREATE NEW (Immutable Extraction Pattern)
            new_id = str(uuid.uuid4())
            
            # Insert
            c.execute('''INSERT INTO entities (id, name, type, description, keywords, source_knowledge_ids, confidence, doctrinal_context, goals, non_goals)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (new_id, raw.name, raw.type.value, raw.description, json.dumps(raw.keywords), json.dumps([new_knowledge.id]), raw.confidence,
                       raw.doctrinal_context, json.dumps(raw.goals), json.dumps(raw.non_goals)))
            
            final_entity_ids.append(new_id)
            current_id = new_id
            
            # Prepare Session Object
            new_entity = EntityNode(
                id=new_id,
                name=raw.name,
                type=raw.type,
                description=raw.description,
                keywords=raw.keywords,
                source_knowledge_ids=[new_knowledge.id],
                doctrinal_context=raw.doctrinal_context,
                goals=raw.goals,
                non_goals=raw.non_goals
            )
            new_entities_buffer[new_id] = new_entity
            
            # Map for relationship resolution
            entity_name_map[norm_name] = current_id
            my_bar.progress((idx + 1) / total_ent, text=f"Saved entity: {raw.name}")

        my_bar.empty()

        # B. Process Relationships
        for rel in result.relationships:
            # 1. Find Type
            rel_type_id = None
            rel_type_obj = None
            for rtid, rt in st.session_state.relationship_types.items():
                if rt.machine_name == rel.machine_name:
                    rel_type_id = rtid
                    rel_type_obj = rt
                    break
            
            if not rel_type_id:
                st.warning(f"⏩ Skipping unknown relationship type: {rel.machine_name}")
                continue

            # 2. Resolve IDs (using normalized names)
            src_norm = normalize_entity_name(rel.source_entity)
            tgt_norm = normalize_entity_name(rel.target_entity)
            
            src_id = entity_name_map.get(src_norm)
            tgt_id = entity_name_map.get(tgt_norm)
            
            if not src_id or not tgt_id:
                # Try simple match if normalized failed (fallback)
                continue

            # 3. Attributes & Validation
            # NOTE: We must check session state AND our new buffer.
            # But new entities are only in buffer.
            # So usage of st.session_state.entities.get(src_id) fails if src_id is new.
            # We must check new_entities_buffer first.
            
            src_ent = new_entities_buffer.get(src_id) or st.session_state.entities.get(src_id)
            tgt_ent = new_entities_buffer.get(tgt_id) or st.session_state.entities.get(tgt_id)
            
            # --- FULL VALIDATION PIPELINE ---
            # Using the new master validation function that combines rules, ontology confidence, and schema checks.
            from validation.relation_validator import full_relation_validation, calculate_ontology_confidence
            
            if not full_relation_validation(rel, rel_type_obj, src_ent, tgt_ent):
                st.warning(f"❌ Rejected {rel.machine_name}: Validation Pipeline Failed.")
                continue

            # 4. Confidence Calculation (Re-calculate for storage, though validated above)
            src_conf = entity_conf_map.get(src_norm, 1.0)
            tgt_conf = entity_conf_map.get(tgt_norm, 1.0)
            
            # Re-fetch for system confidence (full_validation returns bool, so we recalc score)
            ontology_conf = calculate_ontology_confidence(rel, rel_type_obj, src_ent, tgt_ent)
            
            # (Rejection block removed as it's covered in full_relation_validation)
            
            system_conf = min(rel.confidence, src_conf, tgt_conf, ontology_conf)
            
            # 5. Create Evidence
            ev_id = str(uuid.uuid4())
            c.execute("INSERT INTO evidence (id, source_knowledge_id, text_span) VALUES (?, ?, ?)",
                      (ev_id, new_knowledge.id, rel.evidence_span))
            
            # Buffer Evidence
            new_evidence_buffer[ev_id] = rel.evidence_span
            
            usage_id = str(uuid.uuid4())
            props_json = json.dumps(rel.semantic_properties)
            ev_ids_json = json.dumps([ev_id])
            created_ts = datetime.now().isoformat()
            
            c.execute('''INSERT INTO relation_assertions 
                         (id, knowledge_id, relationship_type_id, source_entity_id, target_entity_id, usage_context, semantic_properties, evidence_ids, 
                          extraction_confidence, ontology_confidence, system_confidence, status, created_at, axis, polarity)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (usage_id, new_knowledge.id, rel_type_id, src_id, tgt_id, rel.usage_context.value, props_json, ev_ids_json, 
                       rel.confidence, ontology_conf, system_conf, "extracted", created_ts, rel.axis, rel.polarity))
            
            # Buffer Relation
            ra = RelationAssertion(
                 id=usage_id, knowledge_id=new_knowledge.id, relationship_type_id=rel_type_id,
                 source_entity_id=src_id, target_entity_id=tgt_id, usage_context=rel.usage_context.value,
                 semantic_properties=rel.semantic_properties, evidence_ids=[ev_id], 
                 extraction_confidence=rel.confidence, ontology_confidence=ontology_conf, system_confidence=system_conf, 
                 status="extracted", created_at=created_ts, axis=rel.axis, polarity=rel.polarity
            )
            new_relations_buffer.append(ra)
            # We also need to buffer evidence map
            # evidence_buffer[ev_id] = rel.evidence_span

        # 4. Save Knowledge
        c.execute('''INSERT INTO knowledge (id, content_raw, timestamp, related_entity_ids)
                     VALUES (?, ?, ?, ?)''',
                  (new_knowledge.id, new_knowledge.content_raw, str(new_knowledge.timestamp), json.dumps(final_entity_ids)))
        
        conn.commit()
        
        # --- ATOMIC SESSION UPDATE ---
        st.session_state.entities.update(new_entities_buffer)
        st.session_state.relation_assertions.extend(new_relations_buffer)
        st.session_state.knowledges.append(new_knowledge)
        
        if "evidence" in st.session_state:
            st.session_state.evidence.update(new_evidence_buffer)
        else:
            st.session_state.evidence = new_evidence_buffer.copy()
        
        st.success("Knowledge processed and saved successfully!")
        
    except Exception as e:
        conn.rollback()
        st.error(f"Transaction Failed: {e}")
    finally:
        conn.close()

def perform_entity_merge(master_id: str, duplicate_id: str):
    """Merge duplicate_id INTO master_id"""
    e1 = st.session_state.entities[master_id]
    e2 = st.session_state.entities[duplicate_id]
    
    # Needs ExtractedEntity-like object for synthesis? No, SynthesisResult works on strings.
    # We call synthesis on e1 and e2.
    # Wait, synthesis takes (EntityNode, ExtractedEntity).
    # Here we have two EntityNodes.
    # I should adjust synthesize_entity_info to accept two generic objects/dicts?
    # Or just construct a dummy ExtractedEntity.
    # Refactoring synthesis to take Strings is better.
    # In my new synthesis.py, I defined: synthesize_entity_info(current_entity: EntityNode, new_info: ExtractedEntity)
    # I can create a temporary ExtractedEntity from e2. (Adapter pattern)
    
    from extraction.models import ExtractedEntity
    e2_adapter = ExtractedEntity(
        name=e2.name, type=e2.type, description=e2.description, keywords=e2.keywords, confidence=1.0 # Dummy
    )
    
    syn = synthesize_entity_info(e1, e2_adapter)
    
    # 2. Database Updates
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Update Relations
    c.execute("UPDATE relation_assertions SET source_entity_id = ? WHERE source_entity_id = ?", (master_id, duplicate_id))
    c.execute("UPDATE relation_assertions SET target_entity_id = ? WHERE target_entity_id = ?", (master_id, duplicate_id))
    
    # Update Knowledge Links
    new_src_ids = list(set(e1.source_knowledge_ids + e2.source_knowledge_ids))
    
    # Update Master Entity
    c.execute("UPDATE entities SET description = ?, keywords = ?, source_knowledge_ids = ? WHERE id = ?",
              (syn.new_description, json.dumps(syn.new_keywords), json.dumps(new_src_ids), master_id))
              
    # Delete Duplicate Entity
    c.execute("DELETE FROM entities WHERE id = ?", (duplicate_id,))
    
    conn.commit()
    conn.close()
    
    # 3. Session Update
    e1.description = syn.new_description
    e1.keywords = syn.new_keywords
    e1.source_knowledge_ids = new_src_ids
    st.session_state.entities[master_id] = e1
    del st.session_state.entities[duplicate_id]
    
    for r in st.session_state.relation_assertions:
        if r.source_entity_id == duplicate_id: r.source_entity_id = master_id
        if r.target_entity_id == duplicate_id: r.target_entity_id = master_id
        
    return syn
