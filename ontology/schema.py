from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from .enums import EntityType

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

class Evidence(BaseModel):
    id: Optional[str] = None
    source_knowledge_id: str
    text_span: str

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
