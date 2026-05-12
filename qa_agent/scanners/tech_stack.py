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
    """Return merged dependency map across root + all workspace
    package.json files.

    Detects workspaces from (in order):
      * `package.json` ``workspaces`` field (npm/yarn) — array of globs
        or ``{packages: [...]}`` object;
      * ``pnpm-workspace.yaml`` ``packages:`` list (pnpm);
      * ``lerna.json`` ``packages`` field (lerna).

    Falls back to the root ``package.json`` only when nothing else is
    declared. Monorepos benefit; flat single-package repos behave
    exactly as before.
    """
    deps: dict[str, str] = {}
    visited: set[Path] = set()

    root_pkg = root / "package.json"
    root_data = _read_json_safe(root_pkg)
    if root_data is not None:
        _merge_deps(deps, root_data)
        visited.add(root_pkg.resolve())

    globs = _discover_npm_workspace_globs(root, root_data)
    for glob in globs:
        for candidate in _expand_workspace_glob(root, glob):
            pkg = candidate / "package.json"
            if not pkg.exists():
                continue
            real = pkg.resolve()
            if real in visited:
                continue
            visited.add(real)
            data = _read_json_safe(pkg)
            if data is not None:
                _merge_deps(deps, data)
    return deps


def _read_json_safe(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _merge_deps(into: dict[str, str], pkg_data: dict) -> None:
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = pkg_data.get(key) or {}
        if isinstance(section, dict):
            for name, version in section.items():
                # First write wins so root deps take precedence over
                # workspace re-pinning, but missing names get filled
                # from workspaces. Either way every present package
                # is captured.
                into.setdefault(name, version)


def _discover_npm_workspace_globs(root: Path, root_pkg: dict | None) -> list[str]:
    globs: list[str] = []

    if root_pkg is not None:
        ws = root_pkg.get("workspaces")
        if isinstance(ws, list):
            globs.extend(str(x) for x in ws if isinstance(x, str))
        elif isinstance(ws, dict):
            packages = ws.get("packages")
            if isinstance(packages, list):
                globs.extend(str(x) for x in packages if isinstance(x, str))

    pnpm_ws = root / "pnpm-workspace.yaml"
    if pnpm_ws.exists():
        globs.extend(_parse_pnpm_workspace(pnpm_ws))

    lerna = _read_json_safe(root / "lerna.json")
    if lerna and isinstance(lerna.get("packages"), list):
        globs.extend(str(x) for x in lerna["packages"] if isinstance(x, str))

    # de-dupe while keeping order
    seen: set[str] = set()
    deduped: list[str] = []
    for g in globs:
        if g not in seen:
            seen.add(g)
            deduped.append(g)
    return deduped


def _parse_pnpm_workspace(p: Path) -> list[str]:
    """Tiny YAML parser for pnpm-workspace.yaml ``packages:`` list.

    Handles the only shape pnpm produces: a top-level ``packages:`` key
    followed by a list of quoted-or-unquoted glob strings. Avoids a
    PyYAML dependency.
    """
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[str] = []
    in_packages = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        if stripped.startswith("packages:"):
            in_packages = True
            continue
        # Any non-indented key ends the block.
        if in_packages and not line.startswith((" ", "\t", "-")):
            in_packages = False
        if in_packages and stripped.startswith("-"):
            value = stripped[1:].strip().strip("'").strip('"')
            if value:
                out.append(value)
    return out


def _expand_workspace_glob(root: Path, glob: str) -> list[Path]:
    """Expand a workspace glob (e.g. ``apps/*``, ``packages/*/sub``).

    Only directory results are returned. Globs starting with ``!`` are
    treated as negations and skipped (pnpm convention); they are rare
    in practice and not worth re-implementing here.
    """
    if not glob or glob.startswith("!"):
        return []
    # Strip trailing /** so Path.glob picks up the directory itself.
    pattern = glob.rstrip("/")
    try:
        matches = sorted(root.glob(pattern))
    except (OSError, ValueError):
        return []
    return [m for m in matches if m.is_dir()]


def _read_py_deps(root: Path) -> set[str]:
    """Return lowercased python package names listed in any manifest."""
    names: set[str] = set()
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        names.update(_read_pyproject_deps(pyproject))

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


def _normalize_pkg(spec: str) -> str:
    s = spec.strip().strip("'").strip('"')
    for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", ";", " "):
        if sep in s:
            s = s.split(sep, 1)[0]
    return s.strip().lower().split("[")[0]


def _read_pyproject_deps(path: Path) -> set[str]:
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover — py>=3.11 has tomllib
        return set()
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return set()

    out: set[str] = set()
    proj = data.get("project") or {}
    for spec in proj.get("dependencies") or []:
        if isinstance(spec, str):
            out.add(_normalize_pkg(spec))
    optional = proj.get("optional-dependencies") or {}
    for group in optional.values():
        for spec in group or []:
            if isinstance(spec, str):
                out.add(_normalize_pkg(spec))

    # poetry
    poetry = (data.get("tool") or {}).get("poetry") or {}
    for key in ("dependencies", "dev-dependencies", "group"):
        section = poetry.get(key)
        if isinstance(section, dict):
            for name in section.keys():
                if name.lower() != "python":
                    out.add(name.lower())
    return {n for n in out if n}


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
