# Flask-Restless-NG Development Guide

## Project Overview

Flask-Restless-NG is a Flask extension that generates **JSON API v1.0 compliant** RESTful endpoints from SQLAlchemy models. This is a performance-focused fork of Flask-Restless with 2-5x faster serialization and support for modern Flask/SQLAlchemy versions.

**Key Architectural Principles:**
- JSON API specification compliance is mandatory (validate responses with `tests/helpers.py::validate_schema()`)
- Content-Type must be `application/vnd.api+json` for all JSON API requests/responses
- Performance optimization through `@lru_cache` decorators on SQLAlchemy introspection helpers in `flask_restless/helpers.py`
- Separation of concerns: serialization, routing (views), and model introspection are distinct layers

## Core Architecture

### Component Hierarchy
```
APIManager (manager.py)
  └─> Creates Blueprint with API/RelationshipAPI views (views/*.py)
       ├─> Serializer/Deserializer (serialization.py)
       ├─> Search/filtering (search.py)
       └─> SQLAlchemy helpers (helpers.py)
```

### Key Files and Responsibilities

**`manager.py` - APIManager class:**
- Entry point: `APIManager.create_api(model, methods=['GET', 'POST', ...])`
- Manages model registry (`created_apis_for` dict maps model → APIInfo)
- URL generation: `url_for(model, resource_id=..., relation_name=..., relationship=True)`
- Default URL pattern: `/api/{collection_name}` (configurable via `url_prefix`)

**`serialization.py` - JSON API serialization:**
- `DefaultSerializer.__call__(instance, only=...)` → JSON API resource object
- `DefaultDeserializer.__call__(data)` → SQLAlchemy model instance
- Resource object structure: `{'type': collection_name, 'id': pk, 'attributes': {...}, 'relationships': {...}}`
- Uses APIManager registry to resolve relationship types via `collection_name(model)`

**`views/resources.py` - API class (primary resources):**
- CRUD operations: `get()`, `post()`, `patch()`, `delete()`
- Handles collections (`/api/people`) and single resources (`/api/people/1`)
- Related resource fetching: `/api/people/1/articles`

**`views/relationships.py` - RelationshipAPI class:**
- Relationship link operations: `/api/people/1/relationships/articles`
- Supports GET, POST, PATCH, DELETE on relationship linkage

**`views/base.py` - APIBase:**
- Preprocessor/postprocessor support (per-method hooks)
- Pagination, filtering, sparse fieldsets, inclusion of related resources
- Error handling with JSON API error format

**`search.py` - Query building:**
- Filter DSL: `{'name': 'age', 'op': 'gt', 'val': 21}`
- Operators in `OPERATORS` dict: `eq`, `ne`, `gt`, `lt`, `like`, `in`, `has`, `any`, etc.
- Sorting: `sort=name,-age` (minus prefix for descending)

**`helpers.py` - SQLAlchemy introspection:**
- Heavily cached with `@lru_cache()` to avoid repeated introspection
- `get_relations(model)` → relationship properties
- `primary_key_names(model)` → list of PK column names
- `get_related_model(model, relation_name)` → related model class

## Development Workflows

### Running Tests
```bash
# Run all tests (excludes integration by default)
make test  # or: pytest tests/

# Run integration tests (requires Docker with MariaDB)
make integration

# Run tests across Python versions
make tox  # or: tox
```

### Code Quality
```bash
make check  # Runs: isort, flake8, mypy, tox, integration

# Individual checks:
make isort   # Import sorting (line_length=160, force_single_line=True)
make flake8  # Linting (max-line-length=160, ignore E124,E127,W503,W504)
make mypy    # Type checking with SQLAlchemy plugin
```

### Test Structure
- Base class: `tests/conftest.py::BaseTestClass` sets up SQLite engine, scoped sessions
- Fixture methods: `setup_method()` creates Flask app and test client, `teardown_method()` closes session
- Helper assertions: `parse_and_validate_response()`, `fetch_and_validate()`, `post_and_validate()`
- JSON API schema validation: Every test response is validated against JSON API spec

## Project-Specific Conventions

### Preprocessors and Postprocessors
Pattern for request/response hooks (see `manager.py` and `views/base.py`):
```python
preprocessors = {
    'GET_COLLECTION': [func1, func2],  # Called before GET on collections
    'POST_RESOURCE': [...],             # Called before POST
    # Other keys: PATCH_RESOURCE, DELETE_RESOURCE, GET_RELATIONSHIP, etc.
}
postprocessors = {
    'GET_COLLECTION': [func],  # Called after successful GET
}
```
Preprocessors can modify request parameters or abort; postprocessors run after response creation.

### Collection Names and URL Patterns
- By default: model class name lowercased and pluralized (e.g., `Person` → `person`)
- Override with `manager.create_api(Person, collection_name='people')`
- URLs: `/{url_prefix}/{collection_name}` (default: `/api/person`)
- Relationship URLs: `/api/person/1/relationships/articles` (linkage) vs `/api/person/1/articles` (related resources)

### Serialization Patterns
When implementing custom serializers:
1. Inherit from `Serializer`/`Deserializer` abstract base classes
2. Override abstract methods: `__call__()`, `serialize()`, `deserialize()`
3. Access API manager via `self.api_manager` to resolve collection names
4. Pass to `create_api(Model, serializer=CustomSerializer, deserializer=CustomDeserializer)`

### Error Handling
Always use JSON API error format (see `views/base.py::error()` and `error_response()`):
```python
return error_response(status_code, detail='Error message', source={'pointer': '/data/attributes/name'})
```
Common exceptions: `ProcessingException`, `SerializationException`, `DeserializationException`

### Performance Considerations
- Serialization is a hot path: avoid repeated model introspection (use `@lru_cache`)
- Batch-load relationships with `selectinload()` when including related resources
- The `changes_on_update()` helper (in `views/helpers.py`) detects if model has side-effects to optimize PATCH responses

### Type Hints
- Uses `typing` module extensively (see `typehints.py` for custom types)
- ResponseTuple: `Tuple[Union[Dict, Response], int, Dict]` (data, status, headers)
- Type checking enforced via mypy with SQLAlchemy plugin

### Compatibility Notes
- Supports Flask 2.2-3.0, SQLAlchemy 1.4.18-2.0.x, Python 3.8-3.12
- Handles both SQLAlchemy 1.x and 2.x imports (see try/except blocks for `ObjectAssociationProxyInstance`)
- Uses SQLAlchemy `future=True` mode in tests for 2.0 compatibility
- JSON API version implemented: **1.0** (stored in `views/base.py::JSONAPI_VERSION`)

## Common Patterns

### Adding a New View Method
1. Add method to `API` or `RelationshipAPI` class in `views/`
2. Wire preprocessor/postprocessor keys (e.g., `GET_COLLECTION`, `POST_RESOURCE`)
3. Use `@with_preprocessors` and `@with_postprocessors` decorators
4. Return `ResponseTuple` or use `error_response()` for errors
5. Add corresponding tests in `tests/test_jsonapi/` following JSON API spec sections

### Implementing Custom Filters
Extend `search.py::OPERATORS` dict with new operator functions:
```python
OPERATORS['my_op'] = lambda field, value, name: field.custom_filter(value)
```

### Working with Relationships
- Use `get_relations(model)` to introspect relationships
- Check relationship direction: `rel.direction == MANYTOONE`
- Resolve related model: `get_related_model(model, 'articles')`
- Association proxies: Use `get_related_association_proxy_model(proxy)`
