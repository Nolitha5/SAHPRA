"""Tokenizer-aligned, auditable engineering chunks for native BGE/Chroma tests.

This layer does not grant regulatory approval and does not create new facts.
It splits already page-anchored source chunks without crossing their pages.
A FAST tokenizer with offsets is required, so text is an exact substring of the
verified parent chunk and the reported page anchors remain traceable.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from .schemas import RegulatoryChunk


@dataclass(frozen=True)
class TokenIndexConfig:
    model_id: str
    max_model_tokens: int
    window_tokens: int = 384
    overlap_tokens: int = 64
    reserved_tokens: int = 8

    def __post_init__(self):
        if not self.model_id.strip():
            raise ValueError('A tokenizer/model identifier is mandatory')
        if self.max_model_tokens < 16 or self.reserved_tokens < 2:
            raise ValueError('Model limit or special-token reserve invalid')
        if self.window_tokens < 8 or self.window_tokens + self.reserved_tokens > self.max_model_tokens:
            raise ValueError('Chunk + special tokens would exceed model limit')
        if not (0 <= self.overlap_tokens < self.window_tokens):
            raise ValueError('Overlap must be below window size')


def _token_offsets(tokenizer, text: str) -> list[tuple[int, int]]:
    if not getattr(tokenizer, 'is_fast', False):
        raise RuntimeError('Exact anchored splitting requires a fast tokenizer with character offsets')
    encoded = tokenizer(text, add_special_tokens=False, truncation=False,
                        return_offsets_mapping=True, return_attention_mask=False)
    offsets = encoded.get('offset_mapping')
    if offsets is None:
        raise RuntimeError('Tokenizer returned no offset mapping')
    valid = []
    for pair in offsets:
        if len(pair) != 2:
            raise ValueError('Invalid tokenizer offset pair')
        start, end = int(pair[0]), int(pair[1])
        if not (0 <= start < end <= len(text)):
            raise ValueError('Tokenizer offset outside verified source text')
        valid.append((start, end))
    for prev, cur in zip(valid, valid[1:]):
        if cur[0] < prev[0] or cur[1] < prev[1]:
            raise ValueError('Tokenizer offsets out of order')
    return valid


def split_regulatory_chunks(chunks: list[RegulatoryChunk], tokenizer,
                            config: TokenIndexConfig) -> tuple[list[RegulatoryChunk], dict]:
    """Return exact source substrings (same source ID/page), never fabricated paraphrases."""
    created = []
    oversized_parent_chunks = 0
    longest_parent_tokens = 0
    for parent in chunks:
        if parent.page is None or not parent.source_id:
            raise ValueError('Unanchored source chunk refused')
        offsets = _token_offsets(tokenizer, parent.text)
        n_tokens = len(offsets)
        longest_parent_tokens = max(longest_parent_tokens, n_tokens)
        oversized_parent_chunks += n_tokens + config.reserved_tokens > config.max_model_tokens
        if not n_tokens:
            raise ValueError(f'No indexable tokens in parent {parent.chunk_id}')
        idx = 0
        while idx < n_tokens:
            end_idx = min(idx + config.window_tokens, n_tokens)
            first_char = offsets[idx][0]
            last_char = offsets[end_idx - 1][1]
            text = parent.text[first_char:last_char]
            if text not in parent.text:
                raise AssertionError('Exact source text invariant broken')
            digest = hashlib.sha256(f'{parent.chunk_id}|{config.model_id}|'
                                    f'{idx}|{end_idx}|{text}'.encode('utf-8')).hexdigest()
            metadata = dict(parent.metadata)
            metadata.update({'parent_chunk_id': parent.chunk_id,
                             'tokenizer_model': config.model_id,
                             'token_start': idx, 'token_end': end_idx,
                             'source_char_start': first_char, 'source_char_end': last_char,
                             'research_only': True})
            created.append(RegulatoryChunk(
                chunk_id=f'TKN-{digest[:26]}', source_id=parent.source_id, text=text,
                page=parent.page, section=parent.section,
                chunk_kind=parent.chunk_kind, checksum=hashlib.sha256(text.encode()).hexdigest(),
                metadata=metadata))
            if end_idx == n_tokens:
                break
            idx = end_idx - config.overlap_tokens
    if len({c.chunk_id for c in created}) != len(created):
        raise ValueError('Duplicate token chunk IDs; cannot index')
    return created, {'status': 'TOKEN_ALIGNED', 'method': 'fast_tokenizer_character_offsets',
                     'model': config.model_id, 'parent_chunks': len(chunks),
                     'indexed_chunks': len(created),
                     'parent_chunks_over_limit': oversized_parent_chunks,
                     'max_parent_tokens': longest_parent_tokens,
                     'window_tokens': config.window_tokens,
                     'overlap_tokens': config.overlap_tokens,
                     'reserved_tokens': config.reserved_tokens,
                     'page_anchors_preserved': True,
                     'regulatory_approved': False,
                     'warning': 'Research index only: source applicability and expert evidence labels remain pending.'}
