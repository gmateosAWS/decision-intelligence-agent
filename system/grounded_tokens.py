"""
system/grounded_tokens.py
--------------------------
Spec-driven vocabulary guardrail (item 5.9).

Builds an allowed-token vocabulary from the active spec at runtime
(decision_variables + target_variables + derived_metrics + all aliases)
and exposes two checking modes:

  validate_strict(token, vocab)
      Blocking: raises UngroundedTokenError when *token* is not in the
      vocabulary.  Called by the planner before forwarding params to a tool.

  check_observational(tokens, vocab)
      Non-blocking: returns a list of UngroundedMention for any token not
      in the vocabulary.  Called by the judge to annotate answers without
      blocking execution.

Design rules (Directive 1 + Directive 4):
  - ALL grounding logic reads from the spec at runtime.
    No hardcoded business names are EVER allowed in this module.
  - This module lives in system/, not agents/, so skills and MCP tools
    can import it without coupling to the Decision Agent.
  - Vocabulary is cached per spec.version to avoid rebuilding on every call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from spec.spec_loader import OrganizationalModelSpec

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Vocabulary:
    """
    Immutable set of recognised token strings for a given spec version.

    *tokens* contains canonical names AND aliases, all lowercased for
    case-insensitive matching.
    """

    spec_version: str
    tokens: frozenset[str]


@dataclass
class UngroundedMention:
    """One token that was found in the output but not in the vocabulary."""

    token: str
    context: str = ""  # optional surrounding context for diagnostics


class UngroundedTokenError(ValueError):
    """Raised by validate_strict() when a token is outside the vocabulary."""

    def __init__(self, token: str, vocab: Vocabulary) -> None:
        self.token = token
        self.vocab = vocab
        super().__init__(
            f"Token '{token}' is not in the spec vocabulary for "
            f"spec v{vocab.spec_version}. "
            "Use an exact variable name or alias from the spec."
        )


# ---------------------------------------------------------------------------
# Vocabulary cache (keyed by spec.version; not lru_cache because
# OrganizationalModelSpec is a mutable dataclass — not hashable)
# ---------------------------------------------------------------------------

_vocab_cache: dict[str, Vocabulary] = {}


def build_vocabulary(spec: "OrganizationalModelSpec") -> Vocabulary:
    """
    Build a Vocabulary from a spec instance.

    Collects every canonical name and alias from:
      - decision_variables (name + aliases)
      - target_variables (name + aliases)
      - derived_metrics (id + name + aliases)

    All tokens are lowercased for case-insensitive matching.
    Returns a cached Vocabulary when spec.version was seen before.
    """
    version = spec.version
    if version in _vocab_cache:
        return _vocab_cache[version]

    raw_tokens: set[str] = set()

    for dv in spec.decision_variables:
        raw_tokens.add(dv.name)
        raw_tokens.update(dv.aliases)

    for tv in spec.target_variables:
        raw_tokens.add(tv.name)
        raw_tokens.update(tv.aliases)

    for dm in spec.derived_metrics:
        raw_tokens.add(dm.id)
        raw_tokens.add(dm.name)
        raw_tokens.update(dm.aliases)

    vocab = Vocabulary(
        spec_version=version,
        tokens=frozenset(t.lower() for t in raw_tokens if t),
    )
    _vocab_cache[version] = vocab
    return vocab


def get_vocabulary(spec: "OrganizationalModelSpec") -> Vocabulary:
    """Return the cached Vocabulary for *spec*, building it on first call."""
    return build_vocabulary(spec)


def invalidate_vocabulary_cache() -> None:
    """Clear the vocabulary cache — for tests and spec hot-reload."""
    _vocab_cache.clear()


# ---------------------------------------------------------------------------
# Checking functions
# ---------------------------------------------------------------------------


def validate_strict(token: str, vocab: Vocabulary) -> None:
    """
    Blocking check: raise UngroundedTokenError if *token* is not in the
    vocabulary.

    Matching is case-insensitive.  The caller (planner) must catch
    UngroundedTokenError and return a clarification state dict instead of
    forwarding the tool call.
    """
    if token.lower() not in vocab.tokens:
        raise UngroundedTokenError(token, vocab)


def check_observational(
    tokens: Iterable[str],
    vocab: Vocabulary,
    context: str = "",
) -> list[UngroundedMention]:
    """
    Non-blocking check: return a list of UngroundedMention for any token
    in *tokens* that is NOT in the vocabulary.

    Matching is case-insensitive.  The caller (judge) logs the mentions as
    a warning prefix but does NOT block the answer.
    """
    mentions: list[UngroundedMention] = []
    for token in tokens:
        if token.lower() not in vocab.tokens:
            mentions.append(UngroundedMention(token=token, context=context))
    return mentions
