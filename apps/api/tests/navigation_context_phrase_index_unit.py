from __future__ import annotations

import random
import time
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_function_catalog import (
    DEFAULT_CATALOG_PATH,
    NavigationFunctionCatalog,
    _ContextPhraseIndex,
    _normalize,
)


ContextPairs = Mapping[str, tuple[tuple[str, str], ...]]


def _brute_hits(contexts: ContextPairs, text: str) -> dict[str, tuple[str, ...]]:
    return {
        function_id: hits
        for function_id, pairs in contexts.items()
        if (
            hits := tuple(
                original
                for phrase, original in pairs
                if phrase and phrase in text
            )
        )
    }


def _assert_exact(index: _ContextPhraseIndex, contexts: ContextPairs, text: str) -> None:
    assert index.hits(text) == _brute_hits(contexts, text), text


def _exercise_synthetic_short_and_duplicate_phrases() -> None:
    contexts = {
        "alpha": (
            ("a", "short-a-first"),
            ("ab", "short-ab"),
            ("alphabet", "alphabet"),
            ("alpha", "alpha-first"),
            ("alpha", "alpha-second"),
            ("", "ignored-empty"),
        ),
        "beta": (
            ("b", "short-b"),
            ("bc", "short-bc"),
            ("bet", "bet"),
            (_normalize("계정 설정"), "계정 설정"),
        ),
    }
    index = _ContextPhraseIndex(contexts)
    for text in (
        "",
        "a",
        "ab",
        "xalphabetx",
        "zzbczz",
        _normalize("내 계정 설정 화면"),
        "alphabeta",
    ):
        _assert_exact(index, contexts, text)


def _exercise_canonical_index(
    contexts: ContextPairs,
    index: _ContextPhraseIndex,
    *,
    seed: int,
) -> tuple[int, int]:
    canonical_phrase_count = 0
    flattened: list[str] = []
    aggregate_texts: list[str] = []
    for function_id, pairs in contexts.items():
        nonempty = [phrase for phrase, _original in pairs if phrase]
        flattened.extend(nonempty)
        canonical_phrase_count += len(nonempty)
        if nonempty:
            # Every reviewed phrase is present in at least one exhaustive
            # brute-force parity probe, including cross-boundary accidental
            # substrings produced by joining a function's complete evidence.
            aggregate_texts.append("q".join(nonempty))

        # Separately prove that every individual source phrase reaches its
        # owner and retains duplicate/original evidence ordering.
        for phrase in nonempty:
            expected_owner = tuple(
                original
                for candidate, original in pairs
                if candidate and candidate in phrase
            )
            assert index.hits(phrase).get(function_id, ()) == expected_owner

    representative = [
        "",
        _normalize("settings account privacy security"),
        _normalize("메뉴 계정 개인정보 보안 결제 구독 해지"),
        _normalize("loading error offline retry permission denied"),
        _normalize("selected disabled checked unchecked confirmation"),
        "x" * 256,
    ]
    rng = random.Random(seed)
    noise = ("x", "qz", "123", "메뉴", "screen", "offline", "")
    random_texts: list[str] = []
    if flattened:
        for _ in range(192):
            selected = [rng.choice(flattened) for _ in range(rng.randrange(0, 7))]
            if selected and rng.random() < 0.5:
                phrase = rng.choice(selected)
                if len(phrase) > 3:
                    selected.append(phrase[1:-1])
            selected.extend(rng.choice(noise) for _ in range(rng.randrange(1, 4)))
            rng.shuffle(selected)
            random_texts.append("".join(selected))

    parity_texts = [*aggregate_texts, *representative, *random_texts]
    for text in parity_texts:
        _assert_exact(index, contexts, text)
    return canonical_phrase_count, len(parity_texts)


def main() -> None:
    _exercise_synthetic_short_and_duplicate_phrases()
    started = time.perf_counter()
    with TemporaryDirectory(prefix="egl-context-index-unit-") as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "catalog.sqlite",
            DEFAULT_CATALOG_PATH,
        )
        positive_phrases, positive_texts = _exercise_canonical_index(
            catalog._positive_contexts,
            catalog._positive_context_index,
            seed=0xE611,
        )
        negative_phrases, negative_texts = _exercise_canonical_index(
            catalog._negative_contexts,
            catalog._negative_context_index,
            seed=0xE612,
        )
    print(
        "navigation context phrase index checks ok: "
        f"canonical_phrases={positive_phrases + negative_phrases} "
        f"brute_parity_texts={positive_texts + negative_texts} "
        "short_phrases=true duplicate_order=true exact=true "
        f"elapsed_seconds={time.perf_counter() - started:.3f}"
    )


if __name__ == "__main__":
    main()
