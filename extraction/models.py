from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from ontology.enums import EntityType, UsageContext, UncertaintyLevel

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
    usage_context: UsageContext = Field(description="Logical role of relation") 
    evidence_span: str = Field(description="EXACT sentence/phrase serving as evidence")
    uncertainty: UncertaintyLevel = Field(description="Uncertainty level", default=UncertaintyLevel.LOW)
    axis: Optional[str] = Field(description="The thematic axis of the relationship", default=None)
    polarity: Optional[str] = Field(description="Positive, Negative, or Neutral", default=None)
    confidence: float = Field(description="Extraction confidence score (0.0 to 1.0)")

class ExtractionResult(BaseModel):
    entities: List[ExtractedEntity]
    relationships: List[ExtractedRelationship] = Field(default_factory=list)

class SynthesisResult(BaseModel):
    new_description: str
    new_keywords: List[str]
