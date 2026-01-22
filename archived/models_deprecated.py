from client import generate_content
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from enum import Enum

class EntityType(str, Enum):
    CONCEPT = "Concept"
    EVENT = "Event"
    PROCESS = "Process"
    OBJECT = "Object"
    PERSON = "Person"
    ORGANIZATION = "Organization"
    PLACE = "Place"

class EntityNode(BaseModel):
    id: Optional[str] = None
    name: str
    type: EntityType
    description: str
    keywords: List[str]
    source_knowledge_ids: List[str] = Field(default_factory=list)
    doctrinal_context: Optional[str] = None
    goals: List[str] = Field(default_factory=list)
    non_goals: List[str] = Field(default_factory=list)

class KnowledgeEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content_raw: str = Field(..., description="Original content")
    timestamp: datetime = Field(default_factory=datetime.now)
    related_entity_ids: List[str] = Field(default_factory=list, description="List of entity IDs extracted")



class RelationshipType(BaseModel):
    id: Optional[str] = None
    machine_name: str
    description: str
    category: str
    directional: bool = True
    deterministic: bool = False
    allowed_entity_types: Optional[Dict[str, List[str]]] = None
    properties_schema: Optional[Dict[str, dict]] = None
    version: str = "1.0"
    deprecated: bool = False

class Evidence(BaseModel):
    id: Optional[str] = None
    source_knowledge_id: str
    text_span: str

class ExtractedEntity(BaseModel):
    name: str = Field(description="Name of the entity")
    type: EntityType = Field(description="Type of the entity")
    description: str = Field(description="Brief description of the entity context")
    keywords: List[str] = Field(description="List of relevant keywords")
    confidence: float = Field(description="Confidence score of extraction (0.0 to 1.0)")
    doctrinal_context: Optional[str] = Field(None, description="The doctrinal context or underlying principle")
    goals: List[str] = Field(default_factory=list, description="Explicit goals or objectives")
    non_goals: List[str] = Field(default_factory=list, description="Explicit non-goals or constraints")

class ExtractedRelationship(BaseModel):
    machine_name: str = Field(description="The machine_name of the relationship type")
    source_entity: str = Field(description="Name of source entity")
    target_entity: str = Field(description="Name of target entity")
    semantic_properties: Dict[str, Any] = Field(description="Properties values based on schema")
    usage_context: str = Field(description="Logical role of relation (e.g. scientific_claim, observation, opinion, hypothesis)")
    evidence_span: str = Field(description="EXACT sentence/phrase serving as evidence")
    uncertainty: str = Field(description="Uncertainty level (Low, Medium, High)", default="Low")
    axis: Optional[str] = Field(description="The thematic axis of the relationship", default=None)
    polarity: Optional[str] = Field(description="Positive, Negative, or Neutral", default=None)
    confidence: float = Field(description="Extraction confidence score (0.0 to 1.0)")

class RelationAssertion(BaseModel):
    id: Optional[str] = None
    knowledge_id: str
    relationship_type_id: str
    source_entity_id: str
    target_entity_id: str
    semantic_properties: Dict[str, Any] = Field(default_factory=dict)
    evidence_ids: List[str] = Field(default_factory=list)
    
    axis: Optional[str] = None
    polarity: Optional[str] = None
    
    extraction_confidence: float = 0.0
    ontology_confidence: float = 0.0
    system_confidence: float = 0.0
    status: str = "extracted"
    created_at: Optional[str] = None
    usage_context: Optional[str] = None

class ExtractionResult(BaseModel):
    entities: List[ExtractedEntity]
    relationships: List[ExtractedRelationship] = Field(default_factory=list)

class SynthesisResult(BaseModel):
    new_description: str
    new_keywords: List[str]
