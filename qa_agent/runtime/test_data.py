"""Test data strategy detection.

Reads project metadata (dependencies, manifests, schema files) and
decides how generated tests should isolate state between runs. Output
is a TestDataPlan saved at state/test_data_plan.json which scaffolds
import into the generated test files.

The detection is deliberately conservative: when in doubt, choose
`api-fixtures` so tests create whatever they need via the public API
and clean up in teardown. That works on every project.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..state import schemas


_ORM_MARKERS_NODE = {
    "prisma": {
        "packages": {"@prisma/client", "prisma"},
        "files": ["prisma/schema.prisma", "packages/database/prisma/schema.prisma"],
    },
    "typeorm": {"packages": {"typeorm"}, "files": []},
    "sequelize": {"packages": {"sequelize", "sequelize-typescript"}, "files": []},
    "drizzle": {"packages": {"drizzle-orm"}, "files": []},
    "mongoose": {"packages": {"mongoose"}, "files": []},
}

_ORM_MARKERS_PY = {
    "sqlalchemy": {"packages": {"sqlalchemy", "SQLAlchemy"}, "files": []},
    "django-orm": {"packages": {"django", "Django"}, "files": ["manage.py"]},
    "tortoise": {"packages": {"tortoise-orm"}, "files": []},
}


def detect_test_data_plan(project_root: Path, project_map: schemas.ProjectMap) -> schemas.TestDataPlan:
    """Inspect the project and emit a fixture strategy plan."""
    pkg_path = project_root / "package.json"
    py_pkgs = _collect_python_packages(project_root)
    node_pkgs = _collect_node_packages(pkg_path)

    # Node ORMs first (Candidate_Mngmnt and similar JS/TS projects).
    for orm, markers in _ORM_MARKERS_NODE.items():
        if node_pkgs & set(markers["packages"]):
            return _build_node_plan(orm, project_root, markers["files"])

    for orm, markers in _ORM_MARKERS_PY.items():
        if py_pkgs & set(markers["packages"]):
            return _build_py_plan(orm, project_root, markers["files"])

    # Default: API-level fixtures via the SUT itself.
    return schemas.TestDataPlan(
        built_at=datetime.now(timezone.utc),
        orm="none",
        strategy="api-fixtures",
        helper_import='import { useApiFixtures } from "../helpers/api-fixtures";',
        setup_call="const fx = await useApiFixtures(app)",
        teardown_call="await fx.cleanup()",
        notes=(
            "No ORM detected. Body authors must create test data via the "
            "public API in arrange and delete in teardown."
        ),
    )


# ---------------------------------------------------------------------
# Plan builders
# ---------------------------------------------------------------------

def _build_node_plan(orm: str, project_root: Path, schema_files: list[str]) -> schemas.TestDataPlan:
    now = datetime.now(timezone.utc)
    if orm == "prisma":
        return schemas.TestDataPlan(
            built_at=now,
            orm="prisma",
            strategy="transactional",
            helper_import='import { withTransaction } from "../helpers/prisma-fixtures";',
            setup_call="const tx = await withTransaction()",
            teardown_call="await tx.rollback()",
            notes=(
                "Prisma detected. Tests run inside a transaction that "
                "rolls back in teardown so the DB stays clean. Helper "
                "must be authored once at tests/qa-agent/helpers/prisma-fixtures.ts."
            ),
        )
    if orm == "typeorm":
        return schemas.TestDataPlan(
            built_at=now,
            orm="typeorm",
            strategy="truncate",
            helper_import='import { resetDataSource } from "../helpers/typeorm-fixtures";',
            setup_call="await resetDataSource()",
            teardown_call="",
            notes="TypeORM detected. Helper truncates entity tables between tests.",
        )
    if orm == "sequelize":
        return schemas.TestDataPlan(
            built_at=now,
            orm="sequelize",
            strategy="transactional",
            helper_import='import { useTxn } from "../helpers/sequelize-fixtures";',
            setup_call="const t = await useTxn()",
            teardown_call="await t.rollback()",
            notes="Sequelize detected. Transactional fixture per test.",
        )
    if orm == "drizzle":
        return schemas.TestDataPlan(
            built_at=now,
            orm="drizzle",
            strategy="truncate",
            helper_import='import { resetDb } from "../helpers/drizzle-fixtures";',
            setup_call="await resetDb()",
            teardown_call="",
            notes="Drizzle ORM detected. Helper truncates between tests.",
        )
    if orm == "mongoose":
        return schemas.TestDataPlan(
            built_at=now,
            orm="mongoose",
            strategy="truncate",
            helper_import='import { dropCollections } from "../helpers/mongo-fixtures";',
            setup_call="await dropCollections()",
            teardown_call="",
            notes="Mongoose detected. Helper drops collections between tests.",
        )
    return schemas.TestDataPlan(built_at=now, orm="none", strategy="api-fixtures")


def _build_py_plan(orm: str, project_root: Path, schema_files: list[str]) -> schemas.TestDataPlan:
    now = datetime.now(timezone.utc)
    if orm == "sqlalchemy":
        return schemas.TestDataPlan(
            built_at=now,
            orm="sqlalchemy",
            strategy="transactional",
            helper_import="from tests.qa_agent.helpers.sa_fixtures import db_session",
            setup_call="session = db_session()",
            teardown_call="session.rollback()",
            notes="SQLAlchemy detected. Function-scoped session, rolled back after each test.",
        )
    if orm == "django-orm":
        return schemas.TestDataPlan(
            built_at=now,
            orm="django-orm",
            strategy="transactional",
            helper_import="import pytest\nfrom pytest_django.fixtures import db",
            setup_call="",
            teardown_call="",
            notes="Django ORM detected. Use pytest-django's `db` fixture (transactional).",
        )
    if orm == "tortoise":
        return schemas.TestDataPlan(
            built_at=now,
            orm="tortoise",
            strategy="truncate",
            helper_import="from tests.qa_agent.helpers.tortoise_fixtures import reset_db",
            setup_call="await reset_db()",
            teardown_call="",
            notes="Tortoise ORM detected. Helper truncates models between tests.",
        )
    return schemas.TestDataPlan(built_at=now, orm="none", strategy="api-fixtures")


# ---------------------------------------------------------------------
# Package collection
# ---------------------------------------------------------------------

def _collect_node_packages(pkg_json: Path) -> set[str]:
    if not pkg_json.is_file():
        return set()
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        out.update((data.get(key) or {}).keys())
    return out


def _collect_python_packages(project_root: Path) -> set[str]:
    out: set[str] = set()
    pyproject = project_root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
        for name in ("sqlalchemy", "django", "tortoise-orm"):
            if name in text:
                out.add(name)
    requirements = project_root / "requirements.txt"
    if requirements.is_file():
        for line in requirements.read_text(encoding="utf-8", errors="ignore").splitlines():
            pkg = line.split("=", 1)[0].split(">", 1)[0].split("<", 1)[0].strip().lower()
            if pkg:
                out.add(pkg)
    return out
