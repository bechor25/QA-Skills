"""Validate that env-broken fixture correctly lacks jest — env-validator must detect this."""
import json, os

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "env-broken-typescript")


def test_fixture_exists():
    assert os.path.isdir(FIXTURE)
    assert os.path.isfile(os.path.join(FIXTURE, "package.json"))


def test_package_json_missing_jest():
    with open(os.path.join(FIXTURE, "package.json")) as f:
        pkg = json.load(f)
    all_deps = {}
    all_deps.update(pkg.get("dependencies", {}))
    all_deps.update(pkg.get("devDependencies", {}))
    assert "jest" not in all_deps, "Fixture should NOT have jest — it's the 'broken env' fixture"
    assert "vitest" not in all_deps


def test_no_node_modules():
    nm = os.path.join(FIXTURE, "node_modules")
    assert not os.path.isdir(nm), "node_modules must not exist in broken fixture"


if __name__ == "__main__":
    test_fixture_exists()
    test_package_json_missing_jest()
    test_no_node_modules()
    print("✅ env-validator fixture tests passed")
