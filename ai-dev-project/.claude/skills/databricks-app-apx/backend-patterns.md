# Backend Code Patterns for APX

Reference templates for backend development. **Only consult when writing backend code.**

## Pydantic Models (models.py)

### 3-Model Pattern

```python
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional

# Enum for status
class EntityStatus(str, Enum):
    STATUS_1 = "status_1"
    STATUS_2 = "status_2"

# Nested models
class ItemIn(BaseModel):
    name: str
    value: float = Field(gt=0)

class ItemOut(BaseModel):
    id: str
    name: str
    value: float
    created_at: datetime

# Main entity models
class EntityIn(BaseModel):
    """Input for creating entities"""
    title: str
    items: list[ItemIn]
    notes: Optional[str] = None

class EntityOut(BaseModel):
    """Complete entity output"""
    id: str
    entity_number: str
    title: str
    status: EntityStatus
    items: list[ItemOut]
    total: float  # Computed field
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class EntityListOut(BaseModel):
    """Summary for list views (performance)"""
    id: str
    entity_number: str
    title: str
    status: EntityStatus
    total: float
    created_at: datetime
```

## API Routes (router.py)

### Basic CRUD Structure

```python
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from .models import EntityIn, EntityOut, EntityListOut, EntityStatus
from .config import conf
from datetime import datetime
import uuid

api = APIRouter(prefix=conf.api_prefix)

# In-memory storage (replace with database)
_entities_db: dict[str, EntityOut] = {}

# List all
@api.get("/entities", response_model=list[EntityListOut], operation_id="listEntities")
async def list_entities():
    """Get all entities (summary view)"""
    return [
        EntityListOut(
            id=e.id,
            entity_number=e.entity_number,
            title=e.title,
            status=e.status,
            total=e.total,
            created_at=e.created_at,
        )
        for e in sorted(_entities_db.values(), key=lambda x: x.created_at, reverse=True)
    ]

# Get one
@api.get("/entities/{entity_id}", response_model=EntityOut, operation_id="getEntity")
async def get_entity(entity_id: str):
    """Get a specific entity by ID"""
    if entity_id not in _entities_db:
        raise HTTPException(status_code=404, detail="Entity not found")
    return _entities_db[entity_id]

# Create
@api.post("/entities", response_model=EntityOut, operation_id="createEntity")
async def create_entity(entity_in: EntityIn):
    """Create a new entity"""
    entity_id = str(uuid.uuid4())

    # Process items
    items = [
        ItemOut(
            id=str(uuid.uuid4()),
            name=item.name,
            value=item.value,
            created_at=datetime.now()
        )
        for item in entity_in.items
    ]

    # Calculate total
    total = sum(item.value for item in items)

    entity = EntityOut(
        id=entity_id,
        entity_number=f"ENT-{datetime.now().strftime('%Y%m%d')}-{len(_entities_db) + 1:04d}",
        title=entity_in.title,
        status=EntityStatus.STATUS_1,
        items=items,
        total=total,
        notes=entity_in.notes,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    _entities_db[entity_id] = entity
    return entity

# Update
@api.patch("/entities/{entity_id}", response_model=EntityOut, operation_id="updateEntity")
async def update_entity(entity_id: str, entity_update: EntityIn):
    """Update an entity"""
    if entity_id not in _entities_db:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity = _entities_db[entity_id]
    # Apply updates
    entity.title = entity_update.title
    entity.updated_at = datetime.now()

    return entity

# Delete
@api.delete("/entities/{entity_id}", operation_id="deleteEntity")
async def delete_entity(entity_id: str):
    """Delete an entity"""
    if entity_id not in _entities_db:
        raise HTTPException(status_code=404, detail="Entity not found")

    del _entities_db[entity_id]
    return {"message": "Entity deleted successfully"}
```

### Mock Data Initialization

```python
def _init_mock_data():
    """Initialize with sample data"""
    if _entities_db:
        return

    mock_data = [
        {
            "title": "Sample Entity 1",
            "status": EntityStatus.STATUS_1,
            "items": [
                {"name": "Item A", "value": 100.0},
                {"name": "Item B", "value": 50.0},
            ],
            "notes": "Sample note",
        },
        # Add 2-3 more samples
    ]

    for idx, data in enumerate(mock_data):
        entity_id = str(uuid.uuid4())

        items = [
            ItemOut(
                id=str(uuid.uuid4()),
                name=item["name"],
                value=item["value"],
                created_at=datetime.now()
            )
            for item in data["items"]
        ]

        entity = EntityOut(
            id=entity_id,
            entity_number=f"ENT-{datetime.now().strftime('%Y%m%d')}-{idx + 1:04d}",
            title=data["title"],
            status=data["status"],
            items=items,
            total=sum(item.value for item in items),
            notes=data.get("notes"),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        _entities_db[entity_id] = entity

# Call at module level
_init_mock_data()
```

## Naming Conventions

### operation_id → Frontend Hook Name

| operation_id | Generated Hook |
|--------------|----------------|
| `listEntities` | `useListEntities()`, `useListEntitiesSuspense()` |
| `getEntity` | `useGetEntity(id)`, `useGetEntitySuspense(id)` |
| `createEntity` | `useCreateEntity()` |
| `updateEntity` | `useUpdateEntity()` |
| `deleteEntity` | `useDeleteEntity()` |

**Pattern**: Verb + EntityName in camelCase
