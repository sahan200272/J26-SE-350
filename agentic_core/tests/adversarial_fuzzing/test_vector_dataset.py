"""Structure checks for the frozen path-traversal vectors (RP-16, section 4c).

These tests only look at the DATA. They never run a vector against the guard.
"""

from collections import Counter

from agentic_core.tests.adversarial_fuzzing.vectors import fingerprint, load_vectors

# Frozen before the first run. If a vector changes, this value must change on
# purpose, and the change will show in git history.
FROZEN_FINGERPRINT = "f32ddcd869d4a14b380724a7f3fccc65aa8ef48cf3ab47e9708422c4d3a449f5"

CATEGORIES = {
    "dot_dot_slash", "windows_backslash", "absolute_path", "root_override", "null_byte",
    "url_encoding", "double_encoding", "overlong_unicode", "unicode_lookalike",
    "windows_special", "name_and_case", "control_chars", "length", "symlink",
}
SETUPS = {None, "symlink_in_zone", "symlink_zone"}
ORIGINS = {"public_example", "assistant_composed"}


def test_there_are_exactly_50_vectors_with_unique_ids():
    vectors = load_vectors()
    assert len(vectors) == 50
    assert [v["id"] for v in vectors] == [f"PT-{i:02d}" for i in range(1, 51)]


def test_every_vector_has_the_expected_fields_and_values():
    for v in load_vectors():
        assert set(v) == {"id", "category", "vector", "setup", "string_origin", "basis"}
        assert isinstance(v["vector"], str) and v["vector"] != ""
        assert v["category"] in CATEGORIES
        assert v["setup"] in SETUPS
        assert v["string_origin"] in ORIGINS
        assert isinstance(v["basis"], str) and v["basis"]


def test_dataset_covers_many_categories_and_is_honest_about_origin():
    vectors = load_vectors()
    assert {v["category"] for v in vectors} == CATEGORIES
    origins = Counter(v["string_origin"] for v in vectors)
    assert origins == {"public_example": 10, "assistant_composed": 40}


def test_symlink_vectors_are_the_only_ones_with_a_setup():
    for v in load_vectors():
        assert (v["setup"] is not None) == (v["category"] == "symlink")


def test_vectors_are_unchanged_since_they_were_frozen():
    assert fingerprint(load_vectors()) == FROZEN_FINGERPRINT