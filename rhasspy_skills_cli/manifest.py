from typing import Any, Dict, Optional, List
from pydantic.main import BaseModel

class Manifest(BaseModel):
    name: str
    slug: str
    version: str
    internet_access: bool = False
    description: Optional[str]
    image: Optional[str]
    languages: Optional[List[str]]
    auto_train: bool = True
    topic_access: Optional[Dict[str, int]]
    default_config: Optional[Dict[str, Any]]
    schema_config: Optional[Dict[str, Any]]