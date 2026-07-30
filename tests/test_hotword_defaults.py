"""Prepacked term list: helpful by default, never at the user's expense.

The term box shipped empty, and the field audit measured the cost — "Antler"
spoken 33 times and spelled right 4, "MENAP" 14 times and right 0. Shipping a
curated list fixes that, but it borrows from a hard 50-pair server budget, so the
one thing that must never happen is a shipped default pushing out something the
user typed.
"""
from app.config import (DEFAULT_TERMS, HOTWORDS_LIMIT, merge_hotwords,
                        parse_hotwords)


def test_defaults_ride_along_with_the_user_list():
    merged = merge_hotwords("Antler\nMENAP=MENAP")
    assert merged["Antler"] == "Antler"
    assert merged["MENAP"] == "MENAP"
    assert "Anthropic" in merged        # from DEFAULT_TERMS


def test_defaults_pin_each_term_to_itself():
    merged = merge_hotwords("")
    assert all(merged[t] == t for t in DEFAULT_TERMS)


def test_switching_the_list_off_leaves_only_the_user_terms():
    assert merge_hotwords("Antler", builtin=False) == {"Antler": "Antler"}
    assert merge_hotwords("", builtin=False) == {}


def test_user_spelling_wins_over_a_shipped_default():
    """Someone who wants "NVIDIA" rendered their way must not be overridden by
    our own entry for the same name."""
    merged = merge_hotwords("NVIDIA=Nvidya")
    assert merged["NVIDIA"] == "Nvidya"


def test_the_cap_only_ever_drops_shipped_defaults():
    user = "\n".join(f"Term{i}" for i in range(48))
    merged = merge_hotwords(user)
    assert len(merged) == HOTWORDS_LIMIT
    kept_user = [k for k in merged if k.startswith("Term")]
    assert len(kept_user) == 48        # every one the user typed survived


def test_a_full_user_list_leaves_no_room_and_that_is_fine():
    user = "\n".join(f"Term{i}" for i in range(HOTWORDS_LIMIT + 10))
    merged = merge_hotwords(user)
    assert len(merged) == HOTWORDS_LIMIT
    assert all(k.startswith("Term") for k in merged)


def test_parser_rules_still_hold_through_the_merge():
    merged = merge_hotwords("# a comment\n\n  Spaced  \nA=B", builtin=False)
    assert merged == {"Spaced": "Spaced", "A": "B"}
    assert parse_hotwords("# only a comment") == {}


def test_shipped_defaults_avoid_ordinary_words():
    """A hotword biases recognition toward the term, so pinning a word that is
    also ordinary speech would corrupt normal sentences — the opposite of the
    point. This is the guard for anyone adding to the list later."""
    ordinary = {"meta", "apple", "oracle", "slack", "notion", "square", "stripe?",
                "amazon", "windows", "word", "teams", "zoom", "bank", "chrome"}
    for term in DEFAULT_TERMS:
        assert term.lower() not in ordinary, f"{term} is also an ordinary word"
    assert len(DEFAULT_TERMS) == len(set(DEFAULT_TERMS)), "duplicate default term"
    assert len(DEFAULT_TERMS) < HOTWORDS_LIMIT, "defaults alone must not fill the budget"
