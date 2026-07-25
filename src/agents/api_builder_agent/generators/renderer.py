"""Templates-first FastAPI project renderer — turns a planner spec into {path: content} maps.

Phase 2 splits rendering across specialized nodes, so templates are grouped by
responsibility (scaffold / backend / database / testing) and each group renders
independently from the shared build context.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "fastapi"

# Template filename -> output path, grouped by the node responsible for rendering it.
_SCAFFOLD_TEMPLATES = {
    "requirements.txt.jinja": "requirements.txt",
    # Named container-image.jinja (not Dockerfile.jinja) so scanners don't
    # misclassify the template itself as a Dockerfile of this service.
    "container-image.jinja": "Dockerfile",
    "docker-compose.yml.jinja": "docker-compose.yml",
    "env.example.jinja": ".env.example",
    "gitignore.jinja": ".gitignore",
    "README.md.jinja": "README.md",
}
_BACKEND_TEMPLATES = {
    "main.py.jinja": "app/main.py",
    "config.py.jinja": "app/config.py",
    "deps.py.jinja": "app/deps.py",
    "schemas.py.jinja": "app/schemas.py",
    "crud.py.jinja": "app/crud.py",
}
_DATABASE_TEMPLATES = {
    "database.py.jinja": "app/database.py",
    "models.py.jinja": "app/models.py",
}
_TESTING_TEMPLATES = {
    "test_crud.py.jinja": "tests/test_crud.py",
}
_ROUTER_TEMPLATE = "router.py.jinja"          # rendered once per entity
_AUTH_TEMPLATE = ("auth.py.jinja", "app/auth.py")  # rendered only when JWT is requested
_PACKAGE_DIRS = ("app", "app/routers", "tests")


def _snake(name: str) -> str:
    """PascalCase / spaced name -> snake_case identifier."""
    spaced = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    return re.sub(r"[^a-z0-9_]", "_", spaced.lower()).strip("_") or "item"


def _normalize_entity(entity: Any) -> dict:
    """Turn a spec entity (string or dict) into the naming variants templates need."""
    raw = entity if isinstance(entity, str) else entity.get("name", "Item")
    name = re.sub(r"[^A-Za-z0-9]", "", raw.strip()) or "Item"
    snake = _snake(name)
    return {
        "name": name,               # Book
        "snake": snake,             # book
        "plural": f"{snake}s",      # books
        "table": f"{snake}s",       # books
    }


def _build_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        # Escapes only html/xml templates; this project emits none, but the
        # default stays safe if one is ever added.
        autoescape=select_autoescape(),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def build_context(spec: dict) -> dict:
    """Build the shared template context every render group consumes."""
    entities = [_normalize_entity(e) for e in spec.get("entities", [])] or [_normalize_entity("Item")]
    return {
        "project_name": spec.get("project_name", "generated-api"),
        "database": spec.get("database", "postgres"),
        "auth": spec.get("auth"),
        "use_jwt": spec.get("auth") == "jwt",
        "entities": entities,
    }


def _render_templates(templates: dict[str, str], ctx: dict) -> dict[str, str]:
    env = _build_env()
    return {out_path: env.get_template(name).render(**ctx) for name, out_path in templates.items()}


def render_scaffold(ctx: dict) -> dict[str, str]:
    """Project skeleton: infra/config files plus empty package markers."""
    files = _render_templates(_SCAFFOLD_TEMPLATES, ctx)
    for pkg in _PACKAGE_DIRS:
        files[f"{pkg}/__init__.py"] = ""
    return files


def render_backend(ctx: dict) -> dict[str, str]:
    """Application code: core app modules, one router per entity, auth when JWT."""
    files = _render_templates(_BACKEND_TEMPLATES, ctx)

    env = _build_env()
    router_tpl = env.get_template(_ROUTER_TEMPLATE)
    for entity in ctx["entities"]:
        files[f"app/routers/{entity['snake']}.py"] = router_tpl.render(entity=entity, **ctx)

    if ctx["use_jwt"]:
        tpl_name, out_path = _AUTH_TEMPLATE
        files[out_path] = env.get_template(tpl_name).render(**ctx)
    return files


def render_database(ctx: dict) -> dict[str, str]:
    """Persistence layer: engine/session setup and SQLAlchemy models."""
    return _render_templates(_DATABASE_TEMPLATES, ctx)


def render_tests(ctx: dict) -> dict[str, str]:
    """Test suite for the generated project."""
    return _render_templates(_TESTING_TEMPLATES, ctx)


def render_project(spec: dict) -> dict[str, str]:
    """Render the complete project in one call — the composition of all render groups."""
    ctx = build_context(spec)
    return {
        **render_scaffold(ctx),
        **render_backend(ctx),
        **render_database(ctx),
        **render_tests(ctx),
    }
