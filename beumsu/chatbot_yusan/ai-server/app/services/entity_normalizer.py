from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from app.core.config import settings
from app.db.models import HeritageAlias
from app.db.repository import HeritageRepository
from app.schemas.chat import EntityMatch
from app.services.cache.memory_cache import cache
from app.services.translation.glossary import normalize_key


JAMO_BASE = 0xAC00
CHO = 588
JUNG = 28
CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNGSUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONGSUNG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def decompose_jamo(text: str) -> str:
    out = []
    for char in text:
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3:
            offset = code - JAMO_BASE
            out.append(CHOSUNG[offset // CHO])
            out.append(JUNGSUNG[(offset % CHO) // JUNG])
            jong = JONGSUNG[offset % JUNG]
            if jong.strip():
                out.append(jong)
        else:
            out.append(char)
    return "".join(out)


@dataclass
class NormalizationResult:
    original_text: str
    normalized_text: str
    detected_entities: list[EntityMatch]
    query_without_entity_noise: str
    warnings: list[str]


class EntityNormalizer:
    def __init__(self, repo: HeritageRepository):
        self.repo = repo

    def normalize(self, text: str) -> NormalizationResult:
        key = f"normalize:{normalize_key(text)}"
        cached = cache.get(key)
        if cached:
            return cached
        aliases = self.repo.list_aliases()
        matches = self._match_aliases(text, aliases)
        normalized_text = text
        for match in matches:
            normalized_text = re.sub(
                re.escape(match.matched_alias),
                match.official_name_ko,
                normalized_text,
                flags=re.I,
            )
        result = NormalizationResult(
            original_text=text,
            normalized_text=normalized_text,
            detected_entities=matches,
            query_without_entity_noise=self._remove_alias_noise(text, matches),
            warnings=[] if matches else ["no_confident_entity"],
        )
        cache.set(key, result)
        return result

    def _match_aliases(self, text: str, aliases: list[HeritageAlias]) -> list[EntityMatch]:
        query_norm = normalize_key(text)
        candidates = self._candidate_terms(text, query_norm, aliases)
        scored: list[tuple[float, HeritageAlias, str]] = []
        for alias in aliases:
            alias_norm = alias.alias_normalized
            if not alias_norm:
                continue
            if alias_norm in query_norm:
                score = 1.0 * alias.confidence_prior
                matched_text = alias.alias
            else:
                best_candidate = self._best_candidate(alias_norm, candidates)
                direct = difflib.SequenceMatcher(None, best_candidate, alias_norm).ratio()
                jamo = difflib.SequenceMatcher(
                    None,
                    decompose_jamo(best_candidate),
                    decompose_jamo(alias_norm),
                ).ratio()
                contains_bonus = (
                    0.08
                    if len(alias_norm) >= 4
                    and (alias_norm[:4] in query_norm or query_norm[:4] in alias_norm)
                    else 0.0
                )
                score = max(direct, jamo) * alias.confidence_prior + contains_bonus
                matched_text = best_candidate
            if score >= settings.confirm_entity_threshold:
                scored.append((min(score, 1.0), alias, matched_text))

        best_by_entity: dict[str, tuple[float, HeritageAlias, str]] = {}
        for score, alias, matched_text in scored:
            current = best_by_entity.get(alias.heritage_entity_id)
            if current is None or score > current[0]:
                best_by_entity[alias.heritage_entity_id] = (score, alias, matched_text)

        results = []
        sorted_matches = sorted(
            best_by_entity.items(),
            key=lambda item: item[1][0],
            reverse=True,
        )
        if sorted_matches and sorted_matches[0][1][0] >= settings.auto_confirm_entity_threshold:
            sorted_matches = [
                item for item in sorted_matches if item[1][0] >= settings.auto_confirm_entity_threshold
            ]

        for entity_id, (score, alias, matched_text) in sorted_matches:
            entity = self.repo.get_entity(entity_id)
            if entity:
                results.append(
                    EntityMatch(
                        heritage_id=entity.id,
                        official_name_ko=entity.official_name_ko,
                        matched_alias=matched_text or alias.alias,
                        match_type=alias.alias_type if matched_text == alias.alias else "fuzzy",
                        confidence=round(score, 3),
                        confirmation_required=score < settings.auto_confirm_entity_threshold,
                    )
                )
        return results[:3]

    def _candidate_terms(
        self,
        text: str,
        query_norm: str,
        aliases: list[HeritageAlias],
    ) -> set[str]:
        candidates = {query_norm}
        for token in re.split(r"\s+", text):
            token_norm = normalize_key(token)
            if token_norm:
                candidates.add(token_norm)

        max_len = min(20, len(query_norm))
        lengths = {
            len(alias.alias_normalized)
            for alias in aliases
            if alias.alias_normalized and 2 <= len(alias.alias_normalized) <= max_len
        }
        for length in lengths:
            for start in range(0, len(query_norm) - length + 1):
                candidates.add(query_norm[start : start + length])
        return candidates

    def _best_candidate(self, alias_norm: str, candidates: set[str]) -> str:
        alias_jamo = decompose_jamo(alias_norm)
        return max(
            candidates,
            key=lambda candidate: max(
                difflib.SequenceMatcher(None, candidate, alias_norm).ratio(),
                difflib.SequenceMatcher(None, decompose_jamo(candidate), alias_jamo).ratio(),
            ),
        )

    def _remove_alias_noise(self, text: str, matches: list[EntityMatch]) -> str:
        cleaned = text
        for match in matches:
            cleaned = re.sub(re.escape(match.matched_alias), "", cleaned, flags=re.I)
        return cleaned.strip()
