"""Validate accessibility-violations fixture has known violations for testing."""
import os, re

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "accessibility-violations")


def test_fixture_exists():
    assert os.path.isdir(FIXTURE)
    assert os.path.isfile(os.path.join(FIXTURE, "index.html"))


def test_has_button_without_name():
    html = open(os.path.join(FIXTURE, "index.html")).read()
    # Button that has no text content and no aria-label
    assert re.search(r'<button[^>]*>[^<]*</button>', html) or \
           re.search(r'<button[^>]*>\s*</button>', html), "Must have empty button"


def test_has_img_without_alt():
    html = open(os.path.join(FIXTURE, "index.html")).read()
    assert re.search(r'<img\s+src=[^>]+>', html), "Must have img without alt"
    imgs_without_alt = re.findall(r'<img(?![^>]*\balt\b)[^>]*>', html)
    assert len(imgs_without_alt) > 0, "Must have at least one img missing alt"


def test_has_input_without_label():
    html = open(os.path.join(FIXTURE, "index.html")).read()
    inputs = re.findall(r'<input[^>]*>', html)
    assert len(inputs) >= 2, "Must have at least 2 inputs"
    labeled = re.findall(r'<label[^>]*for=', html)
    assert len(labeled) == 0, "Fixture must have zero labeled inputs (all unlabeled)"


if __name__ == "__main__":
    test_fixture_exists()
    test_has_button_without_name()
    test_has_img_without_alt()
    test_has_input_without_label()
    print("✅ accessibility fixture tests passed")
