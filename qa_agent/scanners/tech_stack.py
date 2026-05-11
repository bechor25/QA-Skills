"""Tech-stack detector.

Augments a ProjectMap with detected frameworks. Reads project manifests
(package.json, pyproject.toml, pom.xml, build.gradle*) and a few signature
files. Confidence is heuristic: presence in deps = 0.9, presence as
filename only (e.g. next.config.js) = 0.6.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..shared.logging import get_logger
from ..shared.paths import project_root
from ..state import schemas

log = get_logger("qa_agent.scanners.tech_stack")


# Framework signatures.
# - language: which language bucket the framework lives in
# - npm_packages: any of these in package.json → match
# - py_packages: any of these in pyproject/requirements → match
# - java_artifacts: any of these substrings in pom.xml or build.gradle → match
# - files: any of these files at project root → weaker signal
_FRAMEWORKS: list[dict] = [
    {
        "name": "Express",
        "language": "javascript",
        "npm_packages": ["express"],
        "files": [],
    },
    {
        "name": "NestJS",
        "language": "typescript",
        "npm_packages": ["@nestjs/core", "@nestjs/common"],
        "files": ["nest-cli.json"],
    },
    {
        "name": "Next.js",
        "language": "typescript",
        "npm_packages": ["next"],
        "files": ["next.config.js", "next.config.ts", "next.config.mjs"],
    },
    {
        "name": "Nuxt",
        "language": "typescript",
        "npm_packages": ["nuxt"],
        "files": ["nuxt.config.ts", "nuxt.config.js"],
    },
    {
        "name": "Vite",
        "language": "javascript",
        "npm_packages": ["vite"],
        "files": ["vite.config.ts", "vite.config.js"],
    },
    {
        "name": "React",
        "language": "javascript",
        "npm_packages": ["react"],
    },
    {
        "name": "Vue",
        "language": "javascript",
        "npm_packages": ["vue"],
    },
    {
        "name": "Svelte",
        "language": "javascript",
        "npm_packages": ["svelte"],
    },
    {
        "name": "Angular",
        "language": "typescript",
        "npm_packages": ["@angular/core"],
    },
    {
        "name": "FastAPI",
        "language": "python",
        "py_packages": ["fastapi"],
    },
    {
        "name": "Django",
        "language": "python",
        "py_packages": ["django"],
        "files": ["manage.py"],
    },
    {
        "name": "Flask",
        "language": "python",
        "py_packages": ["flask"],
    },
    {
        "name": "Starlette",
        "language": "python",
        "py_packages": ["starlette"],
    },
    {
        "name": "SpringBoot",
        "language": "java",
        "java_artifacts": ["spring-boot"],
    },
    {
        "name": "Quarkus",
        "language": "java",
        "java_artifacts": ["quarkus"],
    },
    {
        "name": "Playwright",
        "language": "typescript",
        "npm_packages": ["@playwright/test", "playwright"],
        "py_packages": ["playwright"],
    },
    {
        "name": "Jest",
        "language": "javascript",
        "npm_packages": ["jest", "@jest/core"],
        "files": ["jest.config.js", "jest.config.ts"],
    },
    {
        "name": "Vitest",
        "language": "typescript",
        "npm_packages": ["vitest"],
        "files": ["vitest.config.ts", "vitest.config.js"],
    },
    {
        "name": "pytest",
        "language": "python",
        "py_packages": ["pytest"],
        "files": ["pytest.ini", "conftest.py"],
    },
]


def scan_tech_stack(project: str | Path | None, pm: schemas.ProjectMap) -> schemas.ProjectMap:
    """Return a new ProjectMap with frameworks populated."""
    root = project_root(project)

    npm_deps = _read_npm_deps(root)
    py_deps = _read_py_deps(root)
    java_deps = _read_java_deps(root)
    files_present = {f.name for f in root.iterdir() if f.is_file()}

    detected: list[schemas.FrameworkEntry] = []
    for fw in _FRAMEWORKS:
        evidence: list[str] = []
        confidence = 0.0

        for pkg in fw.get("npm_packages", []) or []:
            if pkg in npm_deps:
                evidence.append(f"npm:{pkg}@{npm_deps[pkg]}")
                confidence = max(confidence, 0.9)
        for pkg in fw.get("py_packages", []) or []:
            if pkg.lower() in py_deps:
                evidence.append(f"py:{pkg}")
                confidence = max(confidence, 0.9)
        for artifact in fw.get("java_artifacts", []) or []:
            if any(artifact in d for d in java_deps):
                evidence.append(f"java:{artifact}")
                confidence = max(confidence, 0.85)
        for fname in fw.get("files", []) or []:
            if fname in files_present:
                evidence.append(f"file:{fname}")
                confidence = max(confidence, 0.6)

        if confidence > 0:
            detected.append(
                schemas.FrameworkEntry(
                    name=fw["name"],
                    language=fw["language"],
                    confidence=confidence,
                    evidence=evidence,
                )
            )

    log.info("tech_stack: detected %d frameworks", len(detected))
    return pm.model_copy(update={"frameworks": detected})


def _read_npm_deps(root: Path) -> dict[str, str]:
    p = root / "package.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    deps = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = data.get(key) or {}
        if isinstance(section, dict):
            deps.update(section)
    return deps


def _read_py_deps(root: Path) -> set[str]:
    """Return lowercased python package names listed in any manifest."""
    names: set[str] = set()
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            text = ""
        # Cheap parse — we only care which package names appear.
        for line in text.splitlines():
            ls = line.strip().strip(",").strip('"').strip("'")
            if not ls or ls.startswith("#"):
                continue
            # take only the package portion before any version spec.
            for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", ";"):
                if sep in ls:
                    ls = ls.split(sep, 1)[0]
            ls = ls.strip().lower()
            if ls and ls[0].isalpha():
                names.add(ls.split("[")[0])

    for req_name in ("requirements.txt", "requirements-dev.txt", "dev-requirements.txt"):
        req = root / req_name
        if not req.exists():
            continue
        try:
            for line in req.read_text(encoding="utf-8").splitlines():
                ls = line.strip()
                if not ls or ls.startswith("#") or ls.startswith("-"):
                    continue
                for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", ";"):
                    if sep in ls:
                        ls = ls.split(sep, 1)[0]
                names.add(ls.strip().lower().split("[")[0])
        except OSError:
            pass
    return names


def _read_java_deps(root: Path) -> list[str]:
    """Return raw dependency strings from pom.xml / build.gradle*.

    The detector only needs substring matching, so we return the raw text
    lines that look like dependencies.
    """
    out: list[str] = []
    for name in ("pom.xml", "build.gradle", "build.gradle.kts"):
        p = root / name
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if any(keyword in line for keyword in ("groupId", "artifactId", "implementation", "compile ")):
                out.append(line.strip())
    return out
