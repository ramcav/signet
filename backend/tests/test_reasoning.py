import pytest

from signet.domain import ReasoningTrace, MerkleCommit


def test_commit_deterministic():
    t = ReasoningTrace().append("a").append("b").append("c")
    c1 = t.commit()
    c2 = t.commit()
    assert c1.root == c2.root
    assert len(c1.leaves) == 3


def test_commit_changes_when_step_changes():
    a = ReasoningTrace(steps=("x", "y")).commit()
    b = ReasoningTrace(steps=("x", "z")).commit()
    assert a.root != b.root


def test_commit_single_step():
    c = ReasoningTrace(steps=("only",)).commit()
    assert len(c.root) == 64
    assert len(c.leaves) == 1


def test_commit_empty_raises():
    with pytest.raises(ValueError):
        ReasoningTrace().commit()


def test_odd_leaves_duplicates_last():
    # Known-shape check: root for ("a","b","c") != root for ("a","b","c","c")'s raw concat,
    # but duplicating the last leaf before hashing should produce the same root both ways.
    same = ReasoningTrace(steps=("a", "b", "c")).commit()
    dup = ReasoningTrace(steps=("a", "b", "c", "c")).commit()
    assert same.root == dup.root
