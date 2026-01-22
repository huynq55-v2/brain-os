import streamlit as st
import json
import sqlite3
import uuid
import itertools
from storage.sqlite_adapter import (
    save_knowledge_flow, create_relationship_type, update_relationship_type, 
    delete_relationship_type, perform_entity_merge, load_data_from_db, DB_PATH
)
from extraction.similarity import calculate_entity_similarity

def render_input_data():
    st.subheader("Input new knowledge into the system")
    txt_input = st.text_area("Enter text, notes, or documents:", height=200)
    
    if st.button("Process & Save to KB", type="primary"):
        if not txt_input:
            st.warning("Please enter some content!")
        else:
            with st.spinner("Brain OS is thinking..."):
                save_knowledge_flow(txt_input)

def render_view_knowledge():
    st.subheader("Raw Knowledge Base")
    if not st.session_state.knowledges:
        st.info("No data available.")
        return
    
    for k in reversed(st.session_state.knowledges):
        with st.expander(f"📄 Knowledge ID: {k.id[:8]}... ({k.timestamp.strftime('%H:%M %d/%m')})"):
            st.markdown(f"**Original Content:**")
            st.info(k.content_raw)
            
            st.markdown("**Related Entities:**")
            cols = st.columns(4)
            for i, ent_id in enumerate(k.related_entity_ids):
                ent = st.session_state.entities.get(ent_id)
                if ent:
                    cols[i % 4].button(f"🧬 {ent.name}", key=f"btn_k_{k.id}_{ent_id}", disabled=True)
            
            # Show relationships
            if st.session_state.get("relation_assertions"):
                k_rels = [u for u in st.session_state.relation_assertions if u.knowledge_id == k.id]
                if k_rels:
                    st.markdown("**Relationships Extracted:**")
                    for rel in k_rels:
                        r_type = st.session_state.relationship_types.get(rel.relationship_type_id)
                        r_name = r_type.machine_name if r_type else "Unknown"
                        
                        src = st.session_state.entities.get(rel.source_entity_id)
                        tgt = st.session_state.entities.get(rel.target_entity_id)
                        src_name = src.name if src else "?"
                        tgt_name = tgt.name if tgt else "?"
                        
                        st.caption(f"🔗 **{src_name}** _{r_name}_ **{tgt_name}**")

def render_view_entities():
    st.subheader("Entity Knowledge Graph")
    
    col_search, col_stats = st.columns([3, 1])
    with col_search:
        search_query = st.text_input("🔍 Search Entities (Name or Keywords):", placeholder="Type to filter...")
    with col_stats:
        st.metric("Total Entities", len(st.session_state.entities))

    all_entities = list(st.session_state.entities.values())
    if search_query:
        query = search_query.lower()
        filtered_entities = [
            e for e in all_entities 
            if query in e.name.lower() or any(query in k.lower() for k in e.keywords)
        ]
    else:
        filtered_entities = all_entities
        
    if not filtered_entities:
        st.info("No entities found.")
    else:
        ITEMS_PER_PAGE = 10
        total_items = len(filtered_entities)
        total_pages = (total_items - 1) // ITEMS_PER_PAGE + 1
        
        if "entity_page" not in st.session_state: st.session_state.entity_page = 1
        if st.session_state.entity_page > total_pages: st.session_state.entity_page = max(1, total_pages)
        
        current_page = st.session_state.entity_page
        start_idx = (current_page - 1) * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
        
        st.caption(f"Showing **{start_idx + 1}-{end_idx}** of **{total_items}** results")
        
        page_items = filtered_entities[start_idx:end_idx]
        
        for ent in page_items:
            with st.expander(f"🧬 **{ent.name}**"):
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.markdown(f"**ID:** `{ent.id}`")
                    st.markdown("**Keywords:**")
                    st.write(", ".join([f"`{k}`" for k in ent.keywords]))
                    
                    if ent.doctrinal_context:
                        st.markdown("**Doctrinal Context:**")
                        st.caption(ent.doctrinal_context)
                    if ent.goals:
                        st.markdown("**Goals:**")
                        for g in ent.goals: st.caption(f"🎯 {g}")
                    if ent.non_goals:
                        st.markdown("**Non-Goals:**")
                        for ng in ent.non_goals: st.caption(f"🚫 {ng}")

                with c2:
                    st.markdown("**Description:**")
                    st.info(ent.description)
                    st.markdown(f"**References:** Found in {len(ent.source_knowledge_ids)} documents")
        
        # Pagination Controls
        if total_pages > 1:
            st.divider()
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                if st.button("◀️ Previous", disabled=(current_page == 1), key="btn_prev_ent"):
                    st.session_state.entity_page -= 1
                    st.rerun()
            with c2:
                st.markdown(f"<center>Page {current_page} of {total_pages}</center>", unsafe_allow_html=True)
            with c3:
                if st.button("Next ▶️", disabled=(current_page == total_pages), key="btn_next_ent"):
                    st.session_state.entity_page += 1
                    st.rerun()

def render_view_relation_types():
    st.subheader("Semantic Relationship Registry (Schema)")
    
    with st.expander("➕ Define New Relationship Type", expanded=False):
         st.info("For complex types with schemas, please use the JSON Import tab.")
         with st.form("create_rel_form"):
            new_machine = st.text_input("Machine Name (snake_case)", placeholder="e.g. is_a")
            new_desc = st.text_area("Description", placeholder="Describes a relationship...")
            submitted = st.form_submit_button("Create Definition")
            if submitted:
                create_relationship_type(new_machine, new_desc)

    st.divider()
    if not st.session_state.get("relationship_types"):
        st.info("No relationships defined.")
    else:
        for r_type in list(st.session_state.relationship_types.values()):
            with st.expander(f"🔗 **{r_type.machine_name}** ({r_type.category})"):
                st.markdown(f"_{r_type.description}_")
                c1, c2 = st.columns([4, 1])
                with c1:
                    new_desc_input = st.text_area("Update Description", value=r_type.description, key=f"desc_{r_type.id}")
                    if st.button("Save", key=f"save_{r_type.id}"):
                        update_relationship_type(r_type.id, new_desc_input)
                with c2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Delete", key=f"del_{r_type.id}", type="primary"):
                        delete_relationship_type(r_type.id)
                
                instances = [u for u in st.session_state.relation_assertions if u.relationship_type_id == r_type.id]
                st.caption(f"Total Instances: **{len(instances)}**")

def render_view_relationships():
    st.subheader("Relationship Instances (Knowledge Graph)")
    if not st.session_state.relation_assertions:
        st.info("No relationship instances extracted yet.")
        return

    col_filter, col_stats = st.columns([3, 1])
    with col_filter:
        type_opts = sorted(list(set([st.session_state.relationship_types[u.relationship_type_id].machine_name for u in st.session_state.relation_assertions if u.relationship_type_id in st.session_state.relationship_types])))
        sel_types = st.multiselect("Filter by Type", type_opts)
    
    filtered = st.session_state.relation_assertions
    if sel_types:
        valid_ids = [tid for tid, t in st.session_state.relationship_types.items() if t.machine_name in sel_types]
        filtered = [u for u in filtered if u.relationship_type_id in valid_ids]
    
    with col_stats:
        st.metric("Total Relations", len(filtered))
    
    # Pagination
    ITEMS_PER_PAGE = 20
    total_items = len(filtered)
    total_pages = max(1, (total_items - 1) // ITEMS_PER_PAGE + 1)
    
    if "rel_page" not in st.session_state: st.session_state.rel_page = 1
    if st.session_state.rel_page > total_pages: st.session_state.rel_page = 1
    
    curr = st.session_state.rel_page
    start = (curr - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    
    st.caption(f"Showing {start+1}-{min(end, total_items)} of {total_items}")
    
    for u in filtered[start:end]:
        r_type = st.session_state.relationship_types.get(u.relationship_type_id)
        r_name = r_type.machine_name if r_type else "Unknown"
        src = st.session_state.entities.get(u.source_entity_id)
        tgt = st.session_state.entities.get(u.target_entity_id)
        src_name = src.name if src else "?"
        tgt_name = tgt.name if tgt else "?"
        
        with st.expander(f"{src_name} ➡️ {r_name} ➡️ {tgt_name}"):
            c1, c2 = st.columns(2)
            with c1:
                # Evidence Lookup
                if u.evidence_ids:
                    for eid in u.evidence_ids:
                        txt = st.session_state.evidence.get(eid, "Missing")
                        st.markdown(f"**Evidence:** \"{txt}\"")
                else:
                    st.write("No evidence linked.")
                    
                st.caption(f"Role: {u.usage_context}")
            with c2:
                st.write(f"**Sys Conf:** {u.system_confidence:.2f}")
                st.caption(f"Extract Conf: {u.extraction_confidence:.2f}")
                st.caption(f"Ontology Conf: {u.ontology_confidence:.2f}")
                if u.axis: st.caption(f"📐 Axis: {u.axis}")
                if u.polarity: st.caption(f"🧭 Polarity: {u.polarity}")
                st.caption(f"Created: {u.created_at}")

    # Pager
    if total_pages > 1:
        st.divider()
        c1, c2, c3 = st.columns([1, 2, 1])
        if c1.button("Prev", key="rp_prev", disabled=curr==1):
            st.session_state.rel_page -= 1
            st.rerun()
        c2.markdown(f"<center>Page {curr}/{total_pages}</center>", unsafe_allow_html=True)
        if c3.button("Next", key="rp_next", disabled=curr==total_pages):
            st.session_state.rel_page += 1
            st.rerun()

def render_view_evidence():
    st.subheader("Extraction Evidence Registry")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT count(*) FROM evidence")
    total = c.fetchone()[0]
    
    page = st.number_input("Page", 1, max(1, (total//10)+1), 1)
    offset = (page-1)*10
    
    c.execute("SELECT * FROM evidence LIMIT 10 OFFSET ?", (offset,))
    rows = c.fetchall()
    
    st.caption(f"Total Evidence: {total}")
    for row in rows:
        with st.expander(f"Evidence: {row['text_span'][:50]}..."):
            st.write(f"**Full Span:** {row['text_span']}")
            st.caption(f"Source ID: {row['source_knowledge_id']}")
    conn.close()

def render_entity_deduplication():
    st.subheader("Entity Identification & Deduplication")
    if st.button("Run Similarity Scan"):
         ents = list(st.session_state.entities.values())
         if len(ents) < 2:
             st.info("Not enough entities.")
         else:
             found = []
             bar = st.progress(0)
             pairs = list(itertools.combinations(ents, 2))
             total = len(pairs)
             
             for i, (e1, e2) in enumerate(pairs):
                 if i % 10 == 0: bar.progress(i/total)
                 scores = calculate_entity_similarity(e1, e2)
                 if scores["total"] > 0.6: # Threshold
                     found.append((e1, e2, scores))
             bar.empty()
             
             if not found:
                 st.success("No duplicates found.")
             else:
                 for e1, e2, scores in found:
                     with st.container():
                         st.markdown(f"**Cluster:** {e1.name} ↔ {e2.name} (Score: {scores['total']:.2f})")
                         c1, c2 = st.columns(2)
                         with c1: st.info(e1.description)
                         with c2: st.info(e2.description)
                         
                         if st.button(f"Merge {e2.name} -> {e1.name}", key=f"merge_{e1.id}_{e2.id}"):
                             perform_entity_merge(e1.id, e2.id)
                             st.success("Merged!")
                             st.rerun()
                         st.divider()

def render_ontology_import():
    st.subheader("Import Relationship Types via JSON")
    uploaded_file = st.file_uploader("Upload 'relation_types.json'", type=["json"])
    
    if uploaded_file:
        if st.button("Process Import"):
            try:
                data = json.load(uploaded_file)
                types = data.get("relation_types", [])
                
                conn = sqlite3.connect(DB_PATH)
                # Need Row factory
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                
                count = 0
                for rt in types:
                    machine_name = rt['machine_name']
                    target_ver = rt.get('version', "1.0")
                    
                    c.execute("SELECT * FROM relationship_types WHERE machine_name = ?", (machine_name,))
                    existing_rows = c.fetchall()
                    
                    existing_match = None
                    # conn.row_factory = sqlite3.Row # Ensure (Removed redundant)
                    for r in existing_rows:
                        # row object access
                        r_ver = r['version'] if 'version' in r.keys() and r['version'] else "1.0"
                        if r_ver == target_ver:
                            existing_match = r
                            break
                    
                    props = json.dumps(rt.get('properties_schema', {}))
                    allowed = json.dumps(rt.get('allowed_entity_types', {}))
                    
                    if existing_match:
                        # Update
                        c.execute('''UPDATE relationship_types 
                                     SET description=?, category=?, directional=?, deterministic=?, allowed_entity_types=?, properties_schema=?, deprecated=?
                                     WHERE id=?''',
                                  (rt['description'], rt.get('category'), rt.get('directional', True), 
                                   rt.get('deterministic', False), allowed, props, rt.get('deprecated', False), existing_match['id']))
                    else:
                        # Deprecate old
                        if existing_rows:
                            c.execute("UPDATE relationship_types SET deprecated=1 WHERE machine_name=?", (machine_name,))
                        
                        new_id = str(uuid.uuid4())
                        c.execute('''INSERT INTO relationship_types 
                                     (id, machine_name, description, category, directional, deterministic, allowed_entity_types, properties_schema, version, deprecated)
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                  (new_id, machine_name, rt['description'], rt.get('category'), 
                                   rt.get('directional', True), rt.get('deterministic', False), allowed, props, target_ver, rt.get('deprecated', False)))
                        count += 1
                        
                conn.commit()
                conn.close()
                st.success(f"Imported/Updated {count} types.")
                st.cache_data.clear()
                # Reload data cleanly
                load_data_from_db()
                st.rerun()
                
            except Exception as e:
                st.error(f"Import failed: {e}")
