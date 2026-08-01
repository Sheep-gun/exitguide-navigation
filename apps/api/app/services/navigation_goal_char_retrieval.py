from __future__ import annotations

"""Compact lexical retrieval for open-wording navigation goals.

This module deliberately does not depend on, or alter, the production goal
resolver.  It compiles the reviewed function catalog into a bounded sparse
word/character TF-IDF index and exposes ranked *candidates*.  A conservative
admission gate is included so callers can experiment without treating a
nearest neighbour as an instruction.

The index has three hard memory bounds:

* only ``pre_idf_features`` raw features survive per destination profile;
* only ``max_profile_features`` IDF-ranked features are indexed per profile;
* at most ``max_postings_per_feature`` profiles survive for one feature.

Negated queries are always fail-closed.  Ranked candidates remain observable
for diagnostics, but ``admitted`` is false and the result must not replace an
existing decision.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
import heapq
import json
import math
from pathlib import Path
import re
import sys
import threading
from time import perf_counter
import unicodedata
from typing import Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"


@dataclass(frozen=True)
class CharRetrievalConfig:
    """Capacity and admission limits for the sparse retrieval index."""

    char_ngrams: tuple[int, ...] = (2, 3, 4, 5)
    pre_idf_features: int = 384
    max_profile_features: int = 176
    max_query_features: int = 144
    max_postings_per_feature: int = 64
    max_word_df_ratio: float = 0.38
    max_char_df_ratio: float = 0.22
    min_char_document_frequency: int = 1
    cache_size: int = 512
    admission_score: float = 0.115
    admission_margin: float = 0.035
    admission_evidence: int = 18
    admission_word_evidence: int = 5


@dataclass(frozen=True)
class CharRetrievalCandidate:
    intent_id: str
    terminal_function: str
    score: float
    margin: float
    evidence_count: int
    word_evidence_count: int
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "intent_id": self.intent_id,
            "terminal_function": self.terminal_function,
            "score": self.score,
            "margin": self.margin,
            "evidence_count": self.evidence_count,
            "word_evidence_count": self.word_evidence_count,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class CharRetrievalResult:
    query: str
    candidates: tuple[CharRetrievalCandidate, ...]
    admitted: bool
    reason: str
    negated: bool
    best_score: float
    best_margin: float
    evidence_count: int
    query_feature_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "admitted": self.admitted,
            "reason": self.reason,
            "negated": self.negated,
            "best_score": self.best_score,
            "best_margin": self.best_margin,
            "evidence_count": self.evidence_count,
            "query_feature_count": self.query_feature_count,
        }


@dataclass(frozen=True)
class CharRetrievalStats:
    catalog_version: str
    candidate_count: int
    feature_count: int
    posting_count: int
    maximum_posting_length: int
    maximum_profile_features: int
    build_seconds: float
    estimated_index_bytes: int


@dataclass(frozen=True)
class _DestinationProfile:
    intent_id: str
    terminal_function: str
    ordinal: int
    fields: tuple[tuple[str, float, str], ...]


_NEGATION_PATTERNS = (
    re.compile(r"\b(?:no|not|never|neither|nor|without|instead\s+of)\b", re.IGNORECASE),
    re.compile(r"\b(?:do|does|did|is|are|was|were|should|would|can|could)n['’]?t\b", re.IGNORECASE),
    re.compile(r"(?:아니라|아닌|않(?:고|는|아|으|겠|도록)?|말고|제외|건드리지|하지\s*마|대신)"),
)

_KOREAN_PARTICLES = (
    "으로부터",
    "에게서",
    "한테서",
    "에서는",
    "에서도",
    "으로",
    "에서",
    "에게",
    "한테",
    "처럼",
    "보다",
    "까지",
    "부터",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "로",
    "와",
    "과",
    "도",
    "만",
)

_FEATURE_KIND_WEIGHT = {
    "w": 1.70,
    "b": 1.95,
    "c2": 0.28,
    "c3": 0.48,
    "c4": 0.66,
    "c5": 0.78,
}


class NavigationGoalCharRetriever:
    """Bounded word/character TF-IDF candidate retriever."""

    def __init__(
        self,
        catalog_path: Path = DEFAULT_CATALOG_PATH,
        *,
        config: CharRetrievalConfig | None = None,
    ) -> None:
        self.catalog_path = Path(catalog_path)
        self.config = config or CharRetrievalConfig()
        self._validate_config()
        started = perf_counter()
        self.catalog_version, profiles = _load_destination_profiles(self.catalog_path)
        (
            self._candidates,
            self._idf,
            self._postings,
            maximum_profile_features,
        ) = self._compile(profiles)
        self._cache: dict[tuple[str, int], CharRetrievalResult] = {}
        self._runtime_lock = threading.RLock()
        self._query_count = 0
        self._cache_hit_count = 0
        self._admitted_count = 0
        self._rejection_reasons: Counter[str] = Counter()
        build_seconds = perf_counter() - started
        posting_count = sum(len(values) for values in self._postings.values())
        self._stats = CharRetrievalStats(
            catalog_version=self.catalog_version,
            candidate_count=len(self._candidates),
            feature_count=len(self._postings),
            posting_count=posting_count,
            maximum_posting_length=max(
                (len(values) for values in self._postings.values()), default=0
            ),
            maximum_profile_features=maximum_profile_features,
            build_seconds=build_seconds,
            estimated_index_bytes=_estimated_index_bytes(
                self._candidates, self._idf, self._postings
            ),
        )

    @property
    def stats(self) -> CharRetrievalStats:
        return self._stats

    def runtime_stats(self) -> dict[str, object]:
        with self._runtime_lock:
            return {
                "catalog_version": self.catalog_version,
                "candidate_count": self._stats.candidate_count,
                "feature_count": self._stats.feature_count,
                "posting_count": self._stats.posting_count,
                "estimated_index_bytes": self._stats.estimated_index_bytes,
                "build_seconds": self._stats.build_seconds,
                "query_count": self._query_count,
                "cache_hit_count": self._cache_hit_count,
                "cache_entries": len(self._cache),
                "cache_capacity": self.config.cache_size,
                "admitted_count": self._admitted_count,
                "rejection_reasons": dict(sorted(self._rejection_reasons.items())),
            }

    def retrieve(self, query: str, *, limit: int = 5) -> CharRetrievalResult:
        """Return ranked candidates and a precision-first admission decision."""

        limit = max(1, min(20, int(limit)))
        cache_key = (_query_cache_key(query), limit)
        with self._runtime_lock:
            self._query_count += 1
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache_hit_count += 1
        if cached is not None:
            return cached

        normalized = _normalized_text(query)
        negated = _contains_negation(query)
        if not normalized:
            result = CharRetrievalResult(
                query=query,
                candidates=(),
                admitted=False,
                reason="empty_query",
                negated=negated,
                best_score=0.0,
                best_margin=0.0,
                evidence_count=0,
                query_feature_count=0,
            )
            self._cache_store(cache_key, result)
            return result

        query_features = self._query_features(query)
        if not query_features:
            result = CharRetrievalResult(
                query=query,
                candidates=(),
                admitted=False,
                reason="no_indexed_evidence",
                negated=negated,
                best_score=0.0,
                best_margin=0.0,
                evidence_count=0,
                query_feature_count=0,
            )
            self._cache_store(cache_key, result)
            return result

        query_norm = math.sqrt(sum(weight * weight for _feature, weight in query_features))
        scores: defaultdict[int, float] = defaultdict(float)
        contributions: defaultdict[int, list[tuple[float, str]]] = defaultdict(list)
        word_hits: defaultdict[int, set[str]] = defaultdict(set)
        for feature, query_weight in query_features:
            for candidate_index, profile_weight in self._postings.get(feature, ()):
                contribution = query_weight * profile_weight
                scores[candidate_index] += contribution
                contributions[candidate_index].append((contribution, feature))
                if feature.startswith(("w:", "b:")):
                    word_hits[candidate_index].add(feature)

        ranked = sorted(
            (
                (score / query_norm, candidate_index)
                for candidate_index, score in scores.items()
            ),
            key=lambda item: (-item[0], self._candidates[item[1]][0], self._candidates[item[1]][1]),
        )
        selected = ranked[: max(limit + 1, 2)]
        candidates: list[CharRetrievalCandidate] = []
        for position, (score, candidate_index) in enumerate(selected[:limit]):
            next_score = selected[position + 1][0] if position + 1 < len(selected) else 0.0
            intent_id, terminal_function = self._candidates[candidate_index]
            evidence_rows = sorted(
                contributions[candidate_index], key=lambda item: (-item[0], item[1])
            )
            evidence = tuple(feature for _value, feature in evidence_rows[:12])
            candidates.append(
                CharRetrievalCandidate(
                    intent_id=intent_id,
                    terminal_function=terminal_function,
                    score=round(max(0.0, min(1.0, score)), 6),
                    margin=round(max(0.0, score - next_score), 6),
                    evidence_count=len({feature for _value, feature in evidence_rows}),
                    word_evidence_count=len(word_hits[candidate_index]),
                    evidence=evidence,
                )
            )

        result = self._admission_result(
            query=query,
            candidates=tuple(candidates),
            negated=negated,
            query_feature_count=len(query_features),
        )
        self._cache_store(cache_key, result)
        return result

    def _admission_result(
        self,
        *,
        query: str,
        candidates: tuple[CharRetrievalCandidate, ...],
        negated: bool,
        query_feature_count: int,
    ) -> CharRetrievalResult:
        best = candidates[0] if candidates else None
        best_score = best.score if best else 0.0
        best_margin = best.margin if best else 0.0
        evidence_count = best.evidence_count if best else 0
        if negated:
            admitted, reason = False, "negation_requires_resolution"
        elif best is None:
            admitted, reason = False, "no_candidate"
        elif best.score < self.config.admission_score:
            admitted, reason = False, "score_below_gate"
        elif best.margin < self.config.admission_margin:
            admitted, reason = False, "margin_below_gate"
        elif best.evidence_count < self.config.admission_evidence:
            admitted, reason = False, "insufficient_evidence"
        elif best.word_evidence_count < self.config.admission_word_evidence:
            admitted, reason = False, "no_word_evidence"
        else:
            admitted, reason = True, "precision_gate_passed"
        return CharRetrievalResult(
            query=query,
            candidates=candidates,
            admitted=admitted,
            reason=reason,
            negated=negated,
            best_score=best_score,
            best_margin=best_margin,
            evidence_count=evidence_count,
            query_feature_count=query_feature_count,
        )

    def _query_features(self, query: str) -> tuple[tuple[str, float], ...]:
        weighted = _text_features(query, self.config.char_ngrams)
        available = (
            (feature, intrinsic * self._idf[feature])
            for feature, intrinsic in weighted.items()
            if feature in self._postings
        )
        return tuple(
            heapq.nlargest(
                self.config.max_query_features,
                available,
                key=lambda item: (item[1], item[0]),
            )
        )

    def _compile(
        self, profiles: Sequence[_DestinationProfile]
    ) -> tuple[
        tuple[tuple[str, str], ...],
        Mapping[str, float],
        Mapping[str, tuple[tuple[int, float], ...]],
        int,
    ]:
        preliminary_profiles: list[dict[str, float]] = []
        document_frequency: Counter[str] = Counter()
        category_capacity = {
            "pattern": 112,
            "rule": 96,
            "identity": 112,
            "description": 80,
            "context": 80,
        }
        for profile in profiles:
            by_category: defaultdict[str, dict[str, float]] = defaultdict(dict)
            for text, source_weight, category in profile.fields:
                category_features = by_category[category]
                for feature, intrinsic in _text_features(text, self.config.char_ngrams).items():
                    feature = sys.intern(feature)
                    category_features[feature] = max(
                        category_features.get(feature, 0.0), source_weight * intrinsic
                    )
            weighted: dict[str, float] = {}
            for category, category_features in by_category.items():
                selected_category = heapq.nlargest(
                    category_capacity.get(category, 64),
                    category_features.items(),
                    key=lambda item: (
                        item[0].startswith(("w:", "b:")),
                        item[1],
                        item[0],
                    ),
                )
                for feature, value in selected_category:
                    weighted[feature] = max(weighted.get(feature, 0.0), value)
            if len(weighted) > self.config.pre_idf_features:
                weighted = dict(
                    heapq.nlargest(
                        self.config.pre_idf_features,
                        weighted.items(),
                        key=lambda item: (item[1], item[0]),
                    )
                )
            preliminary_profiles.append(weighted)
            document_frequency.update(weighted)

        candidate_count = max(1, len(profiles))
        idf: dict[str, float] = {}
        for feature, frequency in document_frequency.items():
            is_char = feature.startswith("c")
            ratio = frequency / candidate_count
            if is_char:
                if frequency < self.config.min_char_document_frequency:
                    continue
                if ratio > self.config.max_char_df_ratio:
                    continue
            elif ratio > self.config.max_word_df_ratio:
                continue
            idf[feature] = math.log1p((candidate_count + 1) / (frequency + 0.5))

        postings: defaultdict[str, list[tuple[int, float]]] = defaultdict(list)
        maximum_profile_features = 0
        for candidate_index, weighted in enumerate(preliminary_profiles):
            selected = heapq.nlargest(
                self.config.max_profile_features,
                (
                    (feature, source_weight * idf[feature])
                    for feature, source_weight in weighted.items()
                    if feature in idf
                ),
                key=lambda item: (item[1], item[0]),
            )
            maximum_profile_features = max(maximum_profile_features, len(selected))
            norm = math.sqrt(sum(weight * weight for _feature, weight in selected)) or 1.0
            for feature, weight in selected:
                postings[feature].append((candidate_index, weight / norm))

        bounded_postings: dict[str, tuple[tuple[int, float], ...]] = {}
        for feature, values in postings.items():
            if len(values) > self.config.max_postings_per_feature:
                values = heapq.nlargest(
                    self.config.max_postings_per_feature,
                    values,
                    key=lambda item: (item[1], -item[0]),
                )
            bounded_postings[feature] = tuple(sorted(values))

        # Keep IDF only for features that still have postings.
        bounded_idf = {feature: idf[feature] for feature in bounded_postings}
        candidates = tuple(
            (profile.intent_id, profile.terminal_function) for profile in profiles
        )
        return candidates, bounded_idf, bounded_postings, maximum_profile_features

    def _cache_store(
        self, key: tuple[str, int], result: CharRetrievalResult
    ) -> None:
        with self._runtime_lock:
            # Another thread may have filled this key while retrieval ran.
            # Replacing it is deterministic and does not consume capacity.
            if key not in self._cache and len(self._cache) >= self.config.cache_size:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = result
            if result.admitted:
                self._admitted_count += 1
            else:
                self._rejection_reasons[result.reason] += 1

    def _validate_config(self) -> None:
        config = self.config
        if not config.char_ngrams or any(value < 2 or value > 6 for value in config.char_ngrams):
            raise ValueError("char_ngrams must contain values in [2, 6]")
        if config.pre_idf_features < config.max_profile_features:
            raise ValueError("pre_idf_features must cover max_profile_features")
        if min(
            config.max_profile_features,
            config.max_query_features,
            config.max_postings_per_feature,
            config.cache_size,
        ) <= 0:
            raise ValueError("capacity limits must be positive")
        if not 0.0 < config.max_char_df_ratio <= config.max_word_df_ratio <= 1.0:
            raise ValueError("document-frequency ratios are invalid")


def _load_destination_profiles(
    catalog_path: Path,
) -> tuple[str, tuple[_DestinationProfile, ...]]:
    """Stream only retrieval-owned fields from the large catalog JSON.

    The generated catalog contains tens of thousands of reviewed goal rules.
    Loading its entire JSON object graph more than triples cold-start peak
    memory.  The top-level arrays are therefore decoded one object at a time
    from a read-only memory map.  No JSON semantics are relaxed: each yielded
    object is still parsed by the standard decoder.
    """

    # Small test/extension catalogs may be compact one-line JSON.  Full-load
    # them because their peak is bounded and this preserves format agnosticism;
    # large generated catalogs use the streaming path below.
    if catalog_path.stat().st_size <= 16 * 1024 * 1024:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        functions = {
            str(item["function_id"]): item
            for item in payload.get("functions", ())
            if isinstance(item, Mapping) and item.get("function_id")
        }
        profiles = _destination_profiles_from_sources(
            functions, payload.get("intents", ())
        )
        return str(payload.get("catalog_version", "unknown")), profiles

    functions: dict[str, Mapping[str, object]] = {}
    for item in _iter_json_array_objects(catalog_path, "functions"):
        function_id = str(item.get("function_id", "")).strip()
        if not function_id:
            continue
        functions[function_id] = {
            "function_id": function_id,
            "domain": item.get("domain", ""),
            "name_ko": item.get("name_ko", ""),
            "name_en": item.get("name_en", ""),
            "description": item.get("description", ""),
            "aliases": item.get("aliases", {}),
            "positive_context": item.get("positive_context", ()),
        }

    profiles = _destination_profiles_from_sources(
        functions, _iter_json_array_objects(catalog_path, "intents")
    )
    return _catalog_version(catalog_path), profiles


def _destination_profiles_from_sources(
    functions: Mapping[str, Mapping[str, object]],
    intents: Iterable[object],
) -> tuple[_DestinationProfile, ...]:
    profiles: list[_DestinationProfile] = []
    for intent_ordinal, raw_intent in enumerate(intents):
        if not isinstance(raw_intent, Mapping):
            continue
        intent_id = str(raw_intent.get("intent_id", "")).strip()
        default_terminal = str(raw_intent.get("terminal_function", "")).strip()
        destinations: list[str] = [default_terminal] if default_terminal else []
        rules_by_destination: defaultdict[str, list[str]] = defaultdict(list)
        for rule in raw_intent.get("goal_rules", ()):
            if not isinstance(rule, Mapping):
                continue
            destination = str(rule.get("terminal_function") or default_terminal).strip()
            if destination and destination not in destinations:
                destinations.append(destination)
            terms = rule.get("all_of", ())
            if isinstance(terms, str):
                terms = (terms,)
            joined = " ".join(str(term) for term in terms if str(term).strip())
            if destination and joined:
                rules_by_destination[destination].append(joined)

        patterns = tuple(str(value) for value in raw_intent.get("patterns", ()) if str(value).strip())
        for destination_ordinal, terminal_function in enumerate(destinations):
            definition = functions.get(terminal_function)
            if not intent_id or definition is None:
                continue
            fields: list[tuple[str, float, str]] = []
            if terminal_function == default_terminal:
                fields.extend((pattern, 3.65, "pattern") for pattern in patterns)
            else:
                # Generic intent patterns help recall, but destination-specific
                # rule terms must dominate sibling destinations.
                fields.extend((pattern, 0.65, "pattern") for pattern in patterns)
            if terminal_function != default_terminal:
                fields.extend(
                    (term, 3.25, "rule")
                    for term in rules_by_destination[terminal_function]
                )
            fields.extend(
                (
                    (str(definition.get("name_ko", "")), 3.70, "identity"),
                    (str(definition.get("name_en", "")), 3.70, "identity"),
                    (str(definition.get("description", "")), 1.35, "description"),
                    (
                        terminal_function.replace(".", " ").replace("_", " "),
                        1.25,
                        "identity",
                    ),
                    (
                        str(definition.get("domain", "")).replace("_", " "),
                        0.70,
                        "identity",
                    ),
                )
            )
            aliases = definition.get("aliases", {})
            if isinstance(aliases, Mapping):
                for values in aliases.values():
                    if isinstance(values, str):
                        values = (values,)
                    fields.extend(
                        (str(value), 3.35, "identity")
                        for value in values
                        if str(value).strip()
                    )
            positive_context = definition.get("positive_context", ())
            if isinstance(positive_context, str):
                positive_context = (positive_context,)
            fields.extend(
                (str(value), 2.25, "context")
                for value in positive_context
                if str(value).strip()
            )
            profiles.append(
                _DestinationProfile(
                    intent_id=intent_id,
                    terminal_function=terminal_function,
                    ordinal=intent_ordinal * 16 + destination_ordinal,
                    fields=tuple(
                        (text, weight, category)
                        for text, weight, category in fields
                        if text.strip()
                    ),
                )
            )
    profiles.sort(key=lambda item: (item.ordinal, item.intent_id, item.terminal_function))
    return tuple(profiles)


def _catalog_version(catalog_path: Path) -> str:
    with catalog_path.open("rb") as stream:
        prefix = stream.read(65536)
    match = re.search(rb'"catalog_version"\s*:\s*"([^"\\]+)"', prefix)
    return match.group(1).decode("utf-8") if match else "unknown"


def _iter_json_array_objects(
    catalog_path: Path, key: str
) -> Iterable[Mapping[str, object]]:
    """Yield members of a generated top-level JSON array line by line.

    The catalog materializer emits stable indentation.  Detecting the first
    member's indentation lets the buffered reader find member boundaries
    without a Python byte-by-byte scan and without retaining the 79 MB source.
    JSON string newlines are escaped, so a same-indent closing brace is an
    unambiguous object boundary in this generated artifact.
    """

    encoded_key = json.dumps(key).encode("ascii") + b":"
    found_array = False
    member_prefix: bytes | None = None
    member_lines: list[bytes] = []
    with catalog_path.open("rb") as stream:
        for line in stream:
            stripped = line.lstrip()
            if not found_array:
                if stripped.startswith(encoded_key) and b"[" in stripped:
                    found_array = True
                continue
            if not member_lines:
                if stripped.startswith(b"]"):
                    return
                if not stripped.startswith(b"{"):
                    if stripped.strip(b" \t\r\n,"):
                        raise ValueError(
                            f"catalog array {key} contains a non-object member"
                        )
                    continue
                member_prefix = line[: len(line) - len(stripped)]
                member_lines.append(line)
                # The generated catalog currently uses multi-line objects;
                # accept a one-line member as well for future compact output.
                if stripped.rstrip().rstrip(b",").endswith(b"}"):
                    item = json.loads(b"".join(member_lines).rstrip().rstrip(b","))
                    if not isinstance(item, Mapping):
                        raise ValueError(
                            f"catalog array {key} member is not an object"
                        )
                    yield item
                    member_lines = []
                continue
            member_lines.append(line)
            line_prefix = line[: len(line) - len(stripped)]
            if member_prefix is not None and line_prefix == member_prefix:
                remainder = line[len(member_prefix):].strip()
                if remainder in {b"}", b"},"}:
                    item = json.loads(b"".join(member_lines).rstrip().rstrip(b","))
                    if not isinstance(item, Mapping):
                        raise ValueError(
                            f"catalog array {key} member is not an object"
                        )
                    yield item
                    member_lines = []
        if not found_array:
            raise ValueError(f"catalog key is missing or not an array: {key}")
        if member_lines:
            raise ValueError(f"catalog array {key} is truncated")


def _text_features(text: str, char_ngrams: Iterable[int]) -> dict[str, float]:
    tokens = _unicode_tokens(text)
    if not tokens:
        return {}
    features: dict[str, float] = {}
    word_tokens: list[str] = []
    for token in tokens:
        word_tokens.append(token)
        stem = _strip_korean_particle(token)
        if stem != token:
            word_tokens.append(stem)
    for token in word_tokens:
        features[f"w:{token}"] = _FEATURE_KIND_WEIGHT["w"]
    for left, right in zip(tokens, tokens[1:]):
        features[f"b:{left}|{right}"] = _FEATURE_KIND_WEIGHT["b"]

    # Token-local n-grams avoid accidental cross-word evidence.  A compact
    # whole-phrase pass preserves Korean agglutinative and no-space UI labels.
    compact = "".join(tokens)
    char_sources = tuple(dict.fromkeys((*tokens, compact)))
    for size in char_ngrams:
        kind = f"c{size}"
        intrinsic = _FEATURE_KIND_WEIGHT.get(kind, 0.5)
        for source in char_sources:
            if len(source) < size:
                continue
            for offset in range(len(source) - size + 1):
                features[f"{kind}:{source[offset:offset + size]}"] = intrinsic
    return features


def _unicode_tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    tokens: list[str] = []
    current: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if character.isalnum() or (category.startswith("M") and current):
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def _strip_korean_particle(token: str) -> str:
    if len(token) < 3 or not any("가" <= character <= "힣" for character in token):
        return token
    for particle in _KOREAN_PARTICLES:
        if token.endswith(particle) and len(token) > len(particle) + 1:
            return token[: -len(particle)]
    return token


def _normalized_text(value: str) -> str:
    return " ".join(_unicode_tokens(value))


def _query_cache_key(value: str) -> str:
    # Preserve punctuation so a negated sentence cannot collide with a
    # punctuation-separated positive query after Unicode token normalization.
    normalized = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    punctuation = "".join(
        character for character in normalized if unicodedata.category(character).startswith("P")
    )
    return f"{_normalized_text(normalized)}\x1f{punctuation}"


def _contains_negation(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", str(value))
    return any(pattern.search(normalized) is not None for pattern in _NEGATION_PATTERNS)


def _estimated_index_bytes(
    candidates: Sequence[tuple[str, str]],
    idf: Mapping[str, float],
    postings: Mapping[str, Sequence[tuple[int, float]]],
) -> int:
    """Conservative shallow estimate used for regression monitoring."""

    return (
        sum(sys.getsizeof(item) + sum(sys.getsizeof(value) for value in item) for item in candidates)
        + sum(sys.getsizeof(key) + sys.getsizeof(value) for key, value in idf.items())
        + sum(
            sys.getsizeof(key)
            + sys.getsizeof(values)
            + sum(
                sys.getsizeof(posting)
                + sys.getsizeof(posting[0])
                + sys.getsizeof(posting[1])
                for posting in values
            )
            for key, values in postings.items()
        )
    )


_RETRIEVER_SINGLETON_LOCK = threading.RLock()
_RETRIEVER_SINGLETONS: dict[tuple[str, str], NavigationGoalCharRetriever] = {}
_RETRIEVER_SINGLETON_CAPACITY = 2
_RETRIEVER_BUILD_COUNT = 0
_RETRIEVER_BUILD_FAILURE_COUNT = 0
_RETRIEVER_LAST_BUILD_ERROR = ""


def _retriever_singleton_key(
    catalog_path: Path, catalog_fingerprint: str = ""
) -> tuple[str, str]:
    resolved = Path(catalog_path).resolve()
    fingerprint = str(catalog_fingerprint).strip()
    if not fingerprint:
        stat = resolved.stat()
        fingerprint = f"{stat.st_size}:{stat.st_mtime_ns}"
    return str(resolved), fingerprint


def get_navigation_goal_char_retriever(
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    *,
    catalog_fingerprint: str = "",
) -> NavigationGoalCharRetriever:
    """Return one thread-safe lazy retriever per bounded catalog revision."""

    global _RETRIEVER_BUILD_COUNT
    global _RETRIEVER_BUILD_FAILURE_COUNT
    global _RETRIEVER_LAST_BUILD_ERROR
    key = _retriever_singleton_key(catalog_path, catalog_fingerprint)
    with _RETRIEVER_SINGLETON_LOCK:
        existing = _RETRIEVER_SINGLETONS.get(key)
        if existing is not None:
            return existing
        try:
            retriever = NavigationGoalCharRetriever(Path(catalog_path))
        except Exception as error:
            _RETRIEVER_BUILD_FAILURE_COUNT += 1
            _RETRIEVER_LAST_BUILD_ERROR = type(error).__name__
            raise
        if len(_RETRIEVER_SINGLETONS) >= _RETRIEVER_SINGLETON_CAPACITY:
            _RETRIEVER_SINGLETONS.pop(next(iter(_RETRIEVER_SINGLETONS)))
        _RETRIEVER_SINGLETONS[key] = retriever
        _RETRIEVER_BUILD_COUNT += 1
        _RETRIEVER_LAST_BUILD_ERROR = ""
        return retriever


def navigation_goal_char_retrieval_stats(
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    *,
    catalog_fingerprint: str = "",
) -> dict[str, object]:
    """Expose lazy-build and bounded-cache state without forcing a build."""

    key = _retriever_singleton_key(catalog_path, catalog_fingerprint)
    with _RETRIEVER_SINGLETON_LOCK:
        retriever = _RETRIEVER_SINGLETONS.get(key)
        return {
            "initialized": retriever is not None,
            "build_count": _RETRIEVER_BUILD_COUNT,
            "build_failure_count": _RETRIEVER_BUILD_FAILURE_COUNT,
            "last_build_error": _RETRIEVER_LAST_BUILD_ERROR,
            "active_instances": len(_RETRIEVER_SINGLETONS),
            "instance_capacity": _RETRIEVER_SINGLETON_CAPACITY,
            "runtime": retriever.runtime_stats() if retriever is not None else None,
        }


__all__ = [
    "CharRetrievalCandidate",
    "CharRetrievalConfig",
    "CharRetrievalResult",
    "CharRetrievalStats",
    "NavigationGoalCharRetriever",
    "get_navigation_goal_char_retriever",
    "navigation_goal_char_retrieval_stats",
]
