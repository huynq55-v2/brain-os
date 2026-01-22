def get_combined_extraction_prompt(text: str, type_constraints: str) -> str:
    return f"""
    Analyze the text: "{text}"
    
    You are an expert Knowledge Graph Engineer performing "Epistemic Extraction".
    
    ### PHASE 1: ENTITY EXTRACTION
    Task: Identify all important entities.
    - Assign a type: Concept, Event, Process, Object, Person, Organization, Place.
    - Provide a brief description and keywords.
    - Identify 'doctrinal_context' if applicable (underlying principle).
    - Identify explicit 'goals' and 'non_goals' if stated.
    - Estimate confidence.
    
    ### PHASE 2: RELATIONSHIP EXTRACTION
    
    #### STEP 0: EPISTEMIC ANALYSIS (MANDATORY)
    Before extracting any relationship, classify each relevant sentence into ONE of:
    - **factual_assertion** (states something is the case)
    - **definition** (explicitly defines a term)
    - **instruction / command / advice**
    - **question / inquiry**
    - **comparison / contrast**
    - **refutation / denial**
    - **report of belief or teaching** (someone claims X)

    DO NOT extract factual relationships from:
    - questions
    - commands or advice
    - hypothetical or illustrative examples
    unless the text EXPLICITLY states the fact as true.

    #### RELATION EXTRACTION RULES:
    - Only extract ontology relationships from:
      - **factual_assertion**
      - **explicit_definition**
    
    - If the sentence is:
      - **instruction / advice** → DO NOT use relations like 'performs', 'causes', 'is_a'.
      - **question** → DO NOT assert the relation as true.
      - **report of belief** → mark 'usage_context' as 'doctrinal_claim' and reduce confidence.
    
    - If unsure whether the action actually occurred, DO NOT extract the relation.

    #### IMPORTANT DISTINCTIONS:
    1. **"Teaches" vs "Student of"**:
       - "X teaches Y" requires evidence that X actively instructs Y.
       - Phrases like "student of", "pupil of", or questions about teaching DO NOT imply an actual teaching event (do not use 'teaches').
    
    2. **STRICT RULE FOR is_a / instance_of**:
       - Only extract 'is_a' / 'instance_of' if the evidence contains explicit definitional language (e.g., "X is a Y", "X refers to Y", "X is defined as Y").
       - Definition-style explanations answering "how" or "in what way" WITHOUT explicit class assignment must NOT be mapped to 'is_a'.

    Task: Extract relationships BETWEEN the entities you just identified following the rules above.
    - Use ONLY allowed types:
    {type_constraints}
    
    - For each relationship:
      - Fill 'semantic_properties'.
      - Determine 'usage_context'. Allowed values: definition, doctrinal_claim, historical_report, observation, hypothesis, interpretation, comparison, refutation.
      - extract 'evidence_span'.
      - assess 'uncertainty' (Low/Medium/High).
      - determine 'axis' (Thematic axis).
      - determine 'polarity' (Positive/Negative/Neutral).
      - Provide confidence.
    """
