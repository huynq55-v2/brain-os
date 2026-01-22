def get_entity_extraction_prompt(text: str) -> str:
    return f"""
    Analyze the text: "{text}"
    
    Task: Identify all important entities.
    - Assign a type: Concept, Event, Process, Object, Person, Organization, Place.
    - Provide a brief description and keywords.
    - Identify 'doctrinal_context' if applicable (underlying principle).
    - Identify explicit 'goals' and 'non_goals' if stated.
    - Estimate confidence.
    """

def get_relation_extraction_prompt(text: str, entities_ctx: str, type_constraints: str) -> str:
    return f"""
    Analyze the text: "{text}"
    
    Given these extracted entities:
    {entities_ctx}
    
    Task: Extract relationships ONLY between these entities.
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
    
    IMPORTANT NEGATIVE CONSTRAINTS:
    - DISTINGUISH between a COMMAND/ADVICE ("Practice absorption!") and a FACTUAL ACTION ("He performed absorption"). 
    - If the text is an imperative or advice, DO NOT use factual relationship types like 'performs' or 'causes' implying the action already happened.
    - Instead, use a relevant type if available (like 'teaches', 'mentions') or skip if no suitable type exists.
    - If you extract 'performs', the evidence MUST show the entity actually doing it, not just being told to do it.
    """

def get_combined_extraction_prompt(text: str, type_constraints: str) -> str:
    return f"""
    Analyze the text: "{text}"
    
    Task 1: Identify all important entities.
    - Assign a type: Concept, Event, Process, Object, Person, Organization, Place.
    - Provide a brief description and keywords.
    - Identify 'doctrinal_context' if applicable (underlying principle).
    - Identify explicit 'goals' and 'non_goals' if stated.
    - Estimate confidence.
    
    Task 2: Extract relationships BETWEEN the entities you just identified.
    - Use ONLY allowed types for relationships:
    {type_constraints}
    
    - For each relationship:
      - Fill 'semantic_properties'.
      - Determine 'usage_context'. Allowed values: definition, doctrinal_claim, historical_report, observation, hypothesis, interpretation, comparison, refutation.
      - extract 'evidence_span'.
      - assess 'uncertainty' (Low/Medium/High).
      - determine 'axis' (Thematic axis).
      - determine 'polarity' (Positive/Negative/Neutral).
      - Provide confidence.
    
    IMPORTANT NEGATIVE CONSTRAINTS:
    - DISTINGUISH between a COMMAND/ADVICE ("Practice absorption!") and a FACTUAL ACTION ("He performed absorption"). 
    - If the text is an imperative or advice, DO NOT use factual relationship types like 'performs' or 'causes' implying the action already happened.
    - Instead, use a relevant type if available (like 'teaches', 'mentions') or skip if no suitable type exists.
    - If you extract 'performs', the evidence MUST show the entity actually doing it, not just being told to do it.
    """
