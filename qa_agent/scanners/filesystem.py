"""Filesystem scanner.

Walks the project tree, classifies files by language, flags test files,
and produces the file list that everything else (deps, AST, API/UI
scanners) iterates over.
"""

from __future__ import annotations

import fnmatch
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ..shared.config import load_config
from ..shared.logging import get_logger
from ..shared.paths import project_root
from ..state import schemas

log = get_logger("qa_agent.scanners.filesystem")


# Extension → canonical language name. Multi-extension languages
# (Java/Kotlin/Scala) keep separate entries because downstream parsers
# care about the distinction.
_EXT_LANG: dict[str, str] = {
    # JS/TS
    ".ts": "typescript",
    ".tsx": "typescript",
    ".cts": "typescript",
    ".mts": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".cjs": "javascript",
    ".mjs": "javascript",
    # Python
    ".py": "python",
    ".pyi": "python",
    # Java family
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    # Web
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".vue": "vue",
    ".svelte": "svelte",
    # Configs we still want to know about
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".xml": "xml",
}

# Filenames (not extensions) that map to a language even without an extension.
_BASENAME_LANG: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "make",
    "requirements.txt": "python-requirements",
    "package.json": "node-manifest",
    "pyproject.toml": "python-manifest",
    "pom.xml": "maven-manifest",
    "build.gradle": "gradle-manifest",
    "build.gradle.kts": "gradle-manifest",
    "settings.gradle": "gradle-manifest",
    "settings.gradle.kts": "gradle-manifest",
}

# Substrings/segments that mark a file as a test file.
_TEST_PATH_MARKERS: tuple[str, ...] = (
    "/tests/",
    "/test/",
    "/__tests__/",
    "/spec/",
    "/e2e/",
)
_TEST_BASENAME_PATTERNS: tuple[str, ...] = (
    "test_*.py",
    "*_test.py",
    "*.test.ts",
    "*.test.tsx",
    "*.test.js",
    "*.test.jsx",
    "*.spec.ts",
    "*.spec.tsx",
    "*.spec.js",
    "*.spec.jsx",
    "*Test.java",
    "*Tests.java",
)


def scan_filesystem(project: str | Path | None = None) -> schemas.ProjectMap:
    """Walk the project and return a populated ProjectMap.

    The returned model has files, language counts, and detected package
    managers filled in. Frameworks are not detected here — that's the
    job of `tech_stack.scan_tech_stack` which consumes this output.
    """
    cfg = load_config(project)
    root = project_root(project)
    ignore_dirs = set(cfg.get("scan", {}).get("ignore_dirs", []))
    max_size = int(cfg.get("scan", {}).get("max_file_size_bytes", 524288))
    follow_symlinks = bool(cfg.get("scan", {}).get("follow_symlinks", False))

    log.info("filesystem: scanning %s (ignore=%d dirs)", root, len(ignore_dirs))
    files: list[schemas.FileEntry] = []
    languages: dict[str, int] = {}

    for entry in _walk(root, ignore_dirs, follow_symlinks):
        try:
            size = entry.stat().st_size
        except OSError:
            continue
        if size > max_size and _classify_language(entry) not in {
            "node-manifest", "python-manifest", "maven-manifest", "gradle-manifest"
        }:
            # large source files are kept but downstream parsers may skip
            pass

        lang = _classify_language(entry)
        if lang is None:
            continue
        rel = entry.relative_to(root).as_posix()
        is_test = _is_test_file(rel, entry.name)
        files.append(
            schemas.FileEntry(
                path=rel,
                language=lang,
                size_bytes=size,
                is_test=is_test,
            )
        )
        languages[lang] = languages.get(lang, 0) + 1

    package_managers = _detect_package_managers(root)
    log.info(
        "filesystem: %d files, %d languages, package managers=%s",
        len(files),
        len(languages),
        package_managers,
    )

    return schemas.ProjectMap(
        project_root=str(root),
        scanned_at=datetime.now(timezone.utc),
        languages=languages,
        files=files,
        frameworks=[],  # filled later by tech_stack
        package_managers=package_managers,
    )


def _walk(root: Path, ignore_dirs: set[str], follow_symlinks: bool) -> Iterable[Path]:
    """Yield every file under root, pruning ignored directories."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]
        # Allow some dotted dirs through (.github is useful)
        # but skip any hidden dir starting with `.` to keep scans light.
        for name in filenames:
            if name.startswith(".") and name not in {".env.example"}:
                continue
            yield Path(dirpath) / name


def _classify_language(path: Path) -> str | None:
    base = path.name
    if base in _BASENAME_LANG:
        return _BASENAME_LANG[base]
    suffix = path.suffix.lower()
    return _EXT_LANG.get(suffix)


def _is_test_file(rel_path: str, basename: str) -> bool:
    lower = rel_path.lower()
    if any(marker in lower for marker in _TEST_PATH_MARKERS):
        return True
    return any(fnmatch.fnmatch(basename, pat) for pat in _TEST_BASENAME_PATTERNS)


def _detect_package_managers(root: Path) -> list[str]:
    found: list[str] = []
    if (root / "package-lock.json").exists():
        found.append("npm")
    if (root / "pnpm-lock.yaml").exists():
        found.append("pnpm")
    if (root / "yarn.lock").exists():
        found.append("yarn")
    if (root / "bun.lockb").exists():
        found.append("bun")
    if (root / "pyproject.toml").exists() and (root / "poetry.lock").exists():
        found.append("poetry")
    elif (root / "pyproject.toml").exists():
        found.append("pip")
    if (root / "requirements.txt").exists() and "pip" not in found:
        found.append("pip")
    if (root / "pom.xml").exists():
        found.append("maven")
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        found.append("gradle")
    return found
