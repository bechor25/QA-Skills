"""Shared pytest fixtures for the qa_agent test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def fastapi_fixture(tmp_path: Path) -> Path:
    """Tiny Python project rooted at tmp_path with FastAPI routes + pyproject."""
    (tmp_path / "pyproject.toml").write_text(
        """[project]
name = "demo"
version = "0.1.0"
dependencies = ["fastapi", "pydantic"]
""",
        encoding="utf-8",
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "main.py").write_text(
        '''from fastapi import FastAPI
app = FastAPI()

@app.get("/users")
async def list_users():
    return []

@app.post("/login")
async def login():
    return {"token": "x"}
''',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def express_fixture(tmp_path: Path) -> Path:
    """Tiny TS/Express project rooted at tmp_path with package.json + a route."""
    (tmp_path / "package.json").write_text(
        '{"name": "demo", "version": "0.1.0", "dependencies": {"express": "^4.0.0"},'
        ' "devDependencies": {"@playwright/test": "^1.40.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "server.ts").write_text(
        '''import express from "express";
const app = express();
app.get("/users", (req, res) => res.json([]));
app.post("/payments/charge", (req, res) => res.json({ ok: true }));
export default app;
''',
        encoding="utf-8",
    )
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "index.tsx").write_text("export default function Home() { return null; }\n", encoding="utf-8")
    (tmp_path / "pages" / "login.tsx").write_text("export default function Login() { return null; }\n", encoding="utf-8")
    return tmp_path
