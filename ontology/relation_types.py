from pydantic import BaseModel
from typing import Optional, Dict, List

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
