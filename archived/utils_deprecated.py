import sqlite3
import json
import uuid
import streamlit as st
from typing import List
from datetime import datetime
from client import generate_content
from models import ExtractionResult, SynthesisResult, EntityNode, KnowledgeEntry, ExtractedEntity, ExtractedRelationship, RelationshipType, RelationAssertion

def normalize_entity_name(name: str) -> str:
    return name.lower().strip()

def validate_extracted_relationship(rel: ExtractedRelationship, rel_type: RelationshipType,
                                    source_entity: EntityNode, target_entity: EntityNode) -> bool:
    # 1. Check entity type
    if rel_type.allowed_entity_types:
        src_allowed = rel_type.allowed_entity_types.get("source", [])
        tgt_allowed = rel_type.allowed_entity_types.get("target", [])
        # EntityNode.type is Enum (string value)
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
                # Assuming all schema props are required if strictly defined
                print(f"Missing Property: {key}")
                return False
            if schema.get("type") == "enum":
                if rel.semantic_properties[key] not in schema.get("values", []):
                    print(f"Invalid Enum: {key}={rel.semantic_properties[key]}")
                    return False
    return True

class OntologyRule:
    def __init__(self, id, description, check_fn):
        self.id = id
        self.description = description
        self.check_fn = check_fn
        
    def evaluate(self, rel: ExtractedRelationship, rel_type: RelationshipType, src: EntityNode, tgt: EntityNode):
        return self.check_fn(rel, rel_type, src, tgt)

# Define Rule Functions
def r1_instance_target_concept(rel, rt, s, t):
    if rt.machine_name == "instance_of" and t.type != "Concept": return 0.0, "Target must be Concept"
    return 1.0, None

def r2_subclass_concept(rel, rt, s, t):
    if rt.machine_name == "subclass_of" and (s.type != "Concept" or t.type != "Concept"): return 0.0, "Requires Concept->Concept"
    return 1.0, None

def r3_causal_target_person(rel, rt, s, t):
    if rt.category == "causal" and t.type == "Person": return 0.0, "Causal cannot target Person"
    return 1.0, None

def r5_deterministic_prob(rel, rt, s, t):
    if rt.deterministic:
        prob = rel.semantic_properties.get("probability")
        if isinstance(prob, (int, float)) and prob < 1.0: return 0.0, "Deterministic means prob 1.0"
    return 1.0, None

def r6_temporal_lag(rel, rt, s, t):
    if rt.category == "temporal" and "temporal_lag" not in rel.semantic_properties: return 0.0, "Missing temporal_lag"
    return 1.0, None

def r7_concept_act(rel, rt, s, t):
    if s.type == "Concept" and rt.machine_name in ["causes", "teaches", "performs"]: return 0.0, "Concept cannot Act"
    return 1.0, None

def r8_teaches_agent(rel, rt, s, t):
    if rt.machine_name == "teaches" and s.type not in ["Person", "Organization"]: return 0.0, "Teacher must be Agent"
    return 1.0, None

def r9_evidence_names(rel, rt, s, t):
    span = rel.evidence_span.lower()
    if s.name.lower() not in span or t.name.lower() not in span: return 0.5, "Evidence missing entity names" # Soft penalty
    return 1.0, None

def r10_hypothesis_deterministic(rel, rt, s, t):
    if rel.usage_context == "hypothesis" and rt.deterministic: return 0.0, "Hypothesis cannot be deterministic"
    return 1.0, None

ONTOLOGY_RULES = [
    OntologyRule("R1", "instance_of target Concept", r1_instance_target_concept),
    OntologyRule("R2", "subclass_of requests Concept->Concept", r2_subclass_concept),
    OntologyRule("R3", "Causal cannot target Person", r3_causal_target_person),
    OntologyRule("R5", "Deterministic prob=1.0", r5_deterministic_prob),
    OntologyRule("R6", "Temporal requires lag", r6_temporal_lag),
    OntologyRule("R7", "Concept cannot Act", r7_concept_act),
    OntologyRule("R8", "Teaches requires Agent source", r8_teaches_agent),
    OntologyRule("R9", "Evidence mentions entities", r9_evidence_names),
    OntologyRule("R10", "Hypothesis non-deterministic", r10_hypothesis_deterministic),
]

def calculate_ontology_confidence(rel: ExtractedRelationship, rel_type: RelationshipType, 
                                  src: EntityNode, tgt: EntityNode) -> float:
    score = 1.0
    reasons = []
    
    for rule in ONTOLOGY_RULES:
        s, reason = rule.evaluate(rel, rel_type, src, tgt)
        if s < 1.0:
            if s == 0.0: score = 0.0 # Hard fail
            else: score = min(score, s) # Soft fail
            if reason: reasons.append(f"{rule.id}: {reason}")
            
    if score < 1.0:
        print(f"⚠️ Ontology Rules: {rel.machine_name} score={score}. Reasons: {reasons}")
    return score

def extract_data(text: str) -> ExtractionResult:
    """Two-Step Extraction: 1. Entities, 2. Relationships"""
    
    # STEP 1: Extract Entities
    prompt_entities = f"""
    Analyze the text: "{text}"
    
    Task: Identify all important entities.
    - Assign a type: Concept, Event, Process, Object, Person, Organization, Place.
    - Provide a brief description and keywords.
    - Identify 'doctrinal_context' if applicable (underlying principle).
    - Identify explicit 'goals' and 'non_goals' if stated.
    - Estimate confidence.
    """
    try:
        # We can use ExtractionResult but ignore relationships
        res_ent = generate_content(prompt_entities, ExtractionResult)
        result1 = ExtractionResult.model_validate_json(res_ent)
    except Exception as e:
        st.error(f"Entity Extraction Error: {e}")
        return ExtractionResult(entities=[], relationships=[])
        
    extracted_entities = result1.entities
    if not extracted_entities:
        return ExtractionResult(entities=[], relationships=[])

    # STEP 2: Extract Relations
    # Build context from extracted entities
    entities_ctx = "\n".join([f"- {e.name} ({e.type})" for e in extracted_entities])
    
    # Get relationship constraints
    type_list = []
    if "relationship_types" in st.session_state and st.session_state.relationship_types:
        for t in st.session_state.relationship_types.values():
            if t.deprecated: continue
            info = f"- {t.machine_name} ({t.category}): {t.description}."
            if t.allowed_entity_types:
                info += f" Source: {t.allowed_entity_types.get('source')}. Target: {t.allowed_entity_types.get('target')}."
            type_list.append(info)
            
    type_constraints = "\n".join(type_list) if type_list else "No predefined types."

    prompt_rels = f"""
    Analyze the text: "{text}"
    
    Given these extracted entities:
    {entities_ctx}
    
    Task: Extract relationships ONLY between these entities.
    - Use ONLY allowed types:
    {type_constraints}
    
    - For each relationship:
      - Fill 'semantic_properties'.
      - Determine 'usage_context' (role).
      - extract 'evidence_span'.
      - assess 'uncertainty' (Low/Medium/High).
      - determine 'axis' (Thematic axis).
      - determine 'polarity' (Positive/Negative/Neutral).
      - Provide confidence.
    """
    try:
        res_rel = generate_content(prompt_rels, ExtractionResult)
        result2 = ExtractionResult.model_validate_json(res_rel)
    except Exception as e:
        st.error(f"Relationship Extraction Error: {e}")
        return ExtractionResult(entities=extracted_entities, relationships=[])

    # Combine
    return ExtractionResult(entities=extracted_entities, relationships=result2.relationships)

def calculate_entity_similarity(e1: EntityNode, e2: EntityNode) -> dict:
    from difflib import SequenceMatcher
    
    # 1. Name Similarity (Weight 50%)
    name_sim = SequenceMatcher(None, e1.name.lower(), e2.name.lower()).ratio()
    
    # 2. Desc Similarity (Weight 30%)
    # Token Jaccard check for speed
    def get_tokens(text): return set(text.lower().split())
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

def perform_entity_merge(master_id: str, duplicate_id: str):
    """Merge duplicate_id INTO master_id"""
    e1 = st.session_state.entities[master_id]
    e2 = st.session_state.entities[duplicate_id]
    
    # 1. Synthesize Info using LLM
    prompt = f"""
    Merge information from two duplicate entities regarding "{e1.name}".
    
    Entity A: "{e1.description}" (Keywords: {e1.keywords})
    Entity B: "{e2.description}" (Keywords: {e2.keywords})
    
    Task: Write a single, comprehensive description merging details from both. Combined keywords.
    """
    try:
        res = generate_content(prompt, SynthesisResult)
        syn = SynthesisResult.model_validate_json(res)
    except:
        # Fallback
        syn = SynthesisResult(new_description=e1.description, new_keywords=list(set(e1.keywords + e2.keywords)))

    # 2. Database Updates
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Update Relations where duplicate is source
    c.execute("UPDATE relation_assertions SET source_entity_id = ? WHERE source_entity_id = ?", (master_id, duplicate_id))
    # Update Relations where duplicate is target
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
    
    # Update local relationships list to reflect ID changes (simple reload or filter)
    # Reloading relationships is safer or iterating and updating
    for r in st.session_state.relation_assertions:
        if r.source_entity_id == duplicate_id: r.source_entity_id = master_id
        if r.target_entity_id == duplicate_id: r.target_entity_id = master_id
        
    return syn

def synthesize_entity_info(current_entity: EntityNode, new_info: ExtractedEntity) -> SynthesisResult:
    """Merge old and new information"""
    
    prompt = f"""
    Merge knowledge for the entity: "{current_entity.name}".
    
    1. Old data: "{current_entity.description}" (Keywords: {current_entity.keywords})
    2. New data: "{new_info.description}" (Keywords: {new_info.keywords})
    
    Task: Write a new synthesized description, preserving historical information, adding new details, and removing duplicates.
    """
    try:
        response = generate_content(prompt, SynthesisResult)
        return SynthesisResult.model_validate_json(response)
    except Exception as e:
        st.error(f"Merge error: {e}")
        return SynthesisResult(new_description=current_entity.description, new_keywords=current_entity.keywords)

# --- 4. DATABASE (SQLite) ---
DB_PATH = "knowledge_base.db"

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
    except: pass # Probably already renamed or doesn't exist
    
    c.execute('''CREATE TABLE IF NOT EXISTS relation_assertions
                 (id TEXT PRIMARY KEY, knowledge_id TEXT, relationship_type_id TEXT, source_entity_id TEXT, target_entity_id TEXT, 
                  usage_context TEXT, semantic_properties TEXT, evidence_ids TEXT, 
                  extraction_confidence REAL, ontology_confidence REAL, system_confidence REAL, status TEXT, created_at TEXT,
                  axis TEXT, polarity TEXT)''')
    
    # Assertions Migration
    acols = [("extraction_confidence", "REAL"), ("system_confidence", "REAL"), ("ontology_confidence", "REAL"),
             ("axis", "TEXT"), ("polarity", "TEXT")]
    for col, dtype in acols:
        try: c.execute(f"ALTER TABLE relation_assertions ADD COLUMN {col} {dtype}")
        except: pass

    conn.commit()
    conn.close()

# Initialize DB
init_db()

def load_data_from_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Load Entities
    c.execute("SELECT * FROM entities")
    rows = c.fetchall()
    st.session_state.entities = {}
    for row in rows:
        try:
            kws = json.loads(row['keywords'])
            src_ids = json.loads(row['source_knowledge_ids'])
        except:
            kws = []
            src_ids = []
            
        ent = EntityNode(
            id=row['id'],
            name=row['name'],
            type=row['type'] if 'type' in row.keys() and row['type'] else "Concept", # Default to Concept if missing
            description=row['description'],
            keywords=kws,
            source_knowledge_ids=src_ids,
            doctrinal_context=row['doctrinal_context'] if 'doctrinal_context' in row.keys() else None,
            goals=json.loads(row['goals']) if 'goals' in row.keys() and row['goals'] else [],
            non_goals=json.loads(row['non_goals']) if 'non_goals' in row.keys() and row['non_goals'] else []
        )
        st.session_state.entities[row['id']] = ent
        
    # Load Knowledge
    c.execute("SELECT * FROM knowledge")
    k_rows = c.fetchall()
    st.session_state.knowledges = []
    
    for row in k_rows:
        try:
             # Handle timestamp string back to datetime if needed, or keep as string/object
             # In models.py KnowledgeEntry uses datetime, but here we read string
             # For simplicity in UI, we might need to parse it or let Pydantic handle it if we reconstruct object
             # We entered it as str(timestamp) in DB.
             
             # Attempt to parse timestamp
             from datetime import datetime
             try:
                 ts = datetime.fromisoformat(row['timestamp'])
             except:
                 ts = datetime.now()

             rel_ids = json.loads(row['related_entity_ids'])
             
             k = KnowledgeEntry(
                 id=row['id'],
                 content_raw=row['content_raw'],
                 timestamp=ts,
                 related_entity_ids=rel_ids
             )
             st.session_state.knowledges.append(k)
        except Exception as e:
            print(f"Error loading knowledge {row['id']}: {e}")

    # Load Relationships
    c.execute("SELECT * FROM relationship_types")
    st.session_state.relationship_types = {row['id']: RelationshipType(
        id=row['id'], 
        machine_name=row['machine_name'], 
        description=row['description'],
        category=row['category'],
        directional=bool(row['directional']),
        deterministic=bool(row['deterministic']),
        allowed_entity_types=json.loads(row['allowed_entity_types']) if row['allowed_entity_types'] else {},
        properties_schema=json.loads(row['properties_schema']) if row['properties_schema'] else {},
        version=row['version'] if 'version' in row.keys() and row['version'] else "1.0",
        deprecated=bool(row['deprecated']) if 'deprecated' in row.keys() and row['deprecated'] else False
    ) for row in c.fetchall()}
    
    # Load Evidence FIRST
    c.execute("SELECT * FROM evidence")
    st.session_state.evidence = {row['id']: row['text_span'] for row in c.fetchall()}

    c.execute("SELECT * FROM relation_assertions")
    st.session_state.relation_assertions = [RelationAssertion(
        id=row['id'], knowledge_id=row['knowledge_id'], relationship_type_id=row['relationship_type_id'],
        source_entity_id=row['source_entity_id'], target_entity_id=row['target_entity_id'], 
        usage_context=row['usage_context'],
        semantic_properties=json.loads(row['semantic_properties']) if row['semantic_properties'] else {},
        evidence_ids=json.loads(row['evidence_ids']) if row['evidence_ids'] else [],
        extraction_confidence=row['extraction_confidence'] if 'extraction_confidence' in row.keys() and row['extraction_confidence'] else 0.0,
        ontology_confidence=row['ontology_confidence'] if 'ontology_confidence' in row.keys() and row['ontology_confidence'] else 0.0,
        system_confidence=row['system_confidence'] if 'system_confidence' in row.keys() and row['system_confidence'] else 0.0,
        status=row['status'] if row['status'] else "extracted",
        created_at=row['created_at'],
        axis=row['axis'] if 'axis' in row.keys() else None,
        polarity=row['polarity'] if 'polarity' in row.keys() else None
    ) for row in c.fetchall()]

    conn.close()

def init_session_state():
    init_db()
    # Initialize Session State with defaults first to prevent AttributeError
    if "knowledges" not in st.session_state: st.session_state.knowledges = []
    if "entities" not in st.session_state: st.session_state.entities = {}
    if "relationship_types" not in st.session_state: st.session_state.relationship_types = {}
    if "relation_assertions" not in st.session_state: st.session_state.relation_assertions = []
    if "evidence" not in st.session_state: st.session_state.evidence = {}

    # Only load if empty (or force reload logic could be added)
    # Actually, we might want to load if it's potentially empty from default
    # But for now, let's try loading if knowledges is empty
    if not st.session_state.knowledges and not st.session_state.entities:
        try:
            load_data_from_db()
        except Exception as e:
            print(f"Error loading database: {e}")
            st.error(f"Error loading database: {e}")

def save_knowledge_flow(text_input):
    # 1. Create Knowledge Entry
    new_knowledge = KnowledgeEntry(content_raw=text_input)
    
    # 2. Extract raw data
    result = extract_data(text_input)
    
    # 3. Connect to DB
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    final_entity_ids = []
    entity_name_map = {} # Map normalized name -> ID
    entity_conf_map = {} # Map normalized name -> confidence

    # A. Process Entities
    for raw in result.entities:
        norm_name = normalize_entity_name(raw.name)
        entity_conf_map[norm_name] = raw.confidence
        
        # ALWAYS CREATE NEW (Immutable Extraction Pattern)
        st.toast(f"✨ Creating new: {raw.name}")
        new_id = str(uuid.uuid4())
        current_id = new_id
        new_src_ids = [new_knowledge.id]
        
        c.execute('''INSERT INTO entities (id, name, type, description, keywords, source_knowledge_ids, confidence, doctrinal_context, goals, non_goals)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (new_id, raw.name, raw.type, raw.description, json.dumps(raw.keywords), json.dumps(new_src_ids), raw.confidence,
                   raw.doctrinal_context, json.dumps(raw.goals), json.dumps(raw.non_goals)))
        final_entity_ids.append(new_id)

        # Update Session State for UI
        new_entity = EntityNode(
            id=new_id,
            name=raw.name,
            type=raw.type,
            description=raw.description,
            keywords=raw.keywords,
            source_knowledge_ids=new_src_ids,
            doctrinal_context=raw.doctrinal_context,
            goals=raw.goals,
            non_goals=raw.non_goals
        )
        st.session_state.entities[new_id] = new_entity
        
        # Map for relationship resolution
        entity_name_map[norm_name] = current_id

    # B. Process Relationships
    for rel in result.relationships:
        # 1. Find Type
        # Allow matching by machine_name
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
        
        if src_norm not in entity_name_map:
             # Try DB lookup if missed? Or skip.
             # Ideally extract_data extracts both.
             # Check DB for pre-existing entities not extracted? Prompt says "Ensure Source and Target are extracted".
             # We can try to resolve if ID is missing (fallback)
             pass 
        
        src_id = entity_name_map.get(src_norm)
        tgt_id = entity_name_map.get(tgt_norm)
        
        if not src_id or not tgt_id:
            st.warning(f"⏩ Skipping relation {rel.machine_name}: Entities not resolved ({rel.source_entity} -> {rel.target_entity})")
            continue

        # 3. Attributes & Validation
        src_ent = st.session_state.entities.get(src_id)
        tgt_ent = st.session_state.entities.get(tgt_id)
        
        if not validate_extracted_relationship(rel, rel_type_obj, src_ent, tgt_ent):
            st.warning(f"❌ Validation Logic Failed for {rel.machine_name} between {src_ent.name} and {tgt_ent.name}")
            continue

        # 4. Confidence Calculation
        src_conf = entity_conf_map.get(src_norm, 1.0)
        tgt_conf = entity_conf_map.get(tgt_norm, 1.0)
        
        # OC Logic
        ontology_conf = calculate_ontology_confidence(rel, rel_type_obj, src_ent, tgt_ent)
        
        # REJECT if OC is low
        if ontology_conf < 0.5:
             st.error(f"⛔ Rejected {rel.machine_name} ({src_ent.name}->{tgt_ent.name}) due to Ontology Violation (OC={ontology_conf})")
             continue
        
        system_conf = min(rel.confidence, src_conf, tgt_conf, ontology_conf)
        
        # 5. Create Evidence
        ev_id = str(uuid.uuid4())
        c.execute("INSERT INTO evidence (id, source_knowledge_id, text_span) VALUES (?, ?, ?)",
                  (ev_id, new_knowledge.id, rel.evidence_span))
        
        # Sync Session
        if "evidence" not in st.session_state: st.session_state.evidence = {}
        st.session_state.evidence[ev_id] = rel.evidence_span
        
        usage_id = str(uuid.uuid4())
        props_json = json.dumps(rel.semantic_properties)
        ev_ids_json = json.dumps([ev_id])
        created_ts = datetime.now().isoformat()
        
        c.execute('''INSERT INTO relation_assertions 
                     (id, knowledge_id, relationship_type_id, source_entity_id, target_entity_id, usage_context, semantic_properties, evidence_ids, 
                      extraction_confidence, ontology_confidence, system_confidence, status, created_at, axis, polarity)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (usage_id, new_knowledge.id, rel_type_id, src_id, tgt_id, rel.usage_context, props_json, ev_ids_json, 
                   rel.confidence, ontology_conf, system_conf, "extracted", created_ts, rel.axis, rel.polarity))
        
        # Update Session
        st.session_state.relation_assertions.append(RelationAssertion(
             id=usage_id, knowledge_id=new_knowledge.id, relationship_type_id=rel_type_id,
             source_entity_id=src_id, target_entity_id=tgt_id, usage_context=rel.usage_context,
             semantic_properties=rel.semantic_properties, evidence_ids=[ev_id], 
             extraction_confidence=rel.confidence, ontology_confidence=ontology_conf, system_confidence=system_conf, 
             status="extracted", created_at=created_ts, axis=rel.axis, polarity=rel.polarity
        ))

    # 4. Save Knowledge
    c.execute('''INSERT INTO knowledge (id, content_raw, timestamp, related_entity_ids)
                 VALUES (?, ?, ?, ?)''',
              (new_knowledge.id, new_knowledge.content_raw, str(new_knowledge.timestamp), json.dumps(final_entity_ids)))
    
    conn.commit()
    conn.close()
    
    # Update Session State
    new_knowledge.related_entity_ids = final_entity_ids
    st.session_state.knowledges.append(new_knowledge)
    
    st.success("Knowledge saved and Knowledge Graph (SQLite) updated!")

def create_relationship_type(machine_name, description):
    """Create a new relationship type"""
    # Validation
    if not machine_name:
        st.error("Machine Name is required.")
        return

    # Check duplicate
    current_types = st.session_state.relationship_types.values()
    if any(t.machine_name == machine_name for t in current_types):
        st.error(f"Relationship type '{machine_name}' already exists.")
        return

    new_id = str(uuid.uuid4())
    # category etc are optional/default
    new_type = RelationshipType(id=new_id, machine_name=machine_name, description=description, category="General")
    
    # DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO relationship_types (id, machine_name, description, category, directional, deterministic) VALUES (?, ?, ?, ?, ?, ?)",
              (new_id, machine_name, description, "General", 1, 0))
    conn.commit()
    conn.close()
    
    # Session
    st.session_state.relationship_types[new_id] = new_type
    st.success(f"Created relationship type: {machine_name}")

def delete_relationship_type(type_id):
    """Delete a relationship type"""
    if type_id not in st.session_state.relationship_types:
        return

    # DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM relationship_types WHERE id = ?", (type_id,))
    # Optional: Delete instances too?
    c.execute("DELETE FROM relation_assertions WHERE relationship_type_id = ?", (type_id,))
    conn.commit()
    conn.close()
    
    # Session
    del st.session_state.relationship_types[type_id]
    # Remove instances from session
    st.session_state.relation_assertions = [u for u in st.session_state.relation_assertions if u.relationship_type_id != type_id]
    
    st.rerun()

def update_relationship_type(type_id, description):
    """Update description of a relationship type"""
    if type_id not in st.session_state.relationship_types:
        return

    # DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE relationship_types SET description = ? WHERE id = ?", (description, type_id))
    conn.commit()
    conn.close()
    
    # Session
    st.session_state.relationship_types[type_id].description = description
    st.toast("Updated description!")