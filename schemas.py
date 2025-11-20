"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# Business Analysis App Schemas

class Dataset(BaseModel):
    """
    Datasets uploaded by users
    Collection name: "dataset"
    """
    name: str = Field(..., description="Dataset display name")
    columns: List[Dict[str, Any]] = Field(default_factory=list, description="Column metadata: name, type")
    sample: List[Dict[str, Any]] = Field(default_factory=list, description="Sample rows for preview")
    row_count: int = Field(0, description="Approximate number of rows parsed")

class Chart(BaseModel):
    """
    Saved chart configurations
    Collection name: "chart"
    """
    dataset_id: str = Field(..., description="Related dataset id (string)")
    title: str = Field(..., description="Chart title")
    chart_type: str = Field(..., description="Chart type: bar, line, pie, scatter")
    x: str = Field(..., description="X-axis column")
    y: Optional[str] = Field(None, description="Y-axis column (for aggregations)")
    agg: Optional[str] = Field(None, description="Aggregation: sum, avg, count, min, max")
    options: Dict[str, Any] = Field(default_factory=dict, description="Chart options")

class Dashboard(BaseModel):
    """
    Dashboards that group charts
    Collection name: "dashboard"
    """
    name: str
    description: Optional[str] = None
    chart_ids: List[str] = Field(default_factory=list)

class Insight(BaseModel):
    """
    AI-generated text insights for a dataset
    Collection name: "insight"
    """
    dataset_id: str
    summary: str
    details: List[str] = Field(default_factory=list)

# Example schemas kept for reference
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = None
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True

# Note: The Flames database viewer will automatically:
# 1. Read these schemas from GET /schema endpoint
# 2. Use them for document validation when creating/editing
# 3. Handle all database operations (CRUD) directly
# 4. You don't need to create any database endpoints!
