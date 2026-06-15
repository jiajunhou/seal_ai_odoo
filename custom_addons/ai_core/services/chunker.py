# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Chunker Service
===============
Splits document text into manageable chunks for embedding.

Strategies:
- recursive: Recursively splits by separators (paragraphs -> sentences -> words)
- token: Splits by approximate token count (~4 chars per token)
- semantic: Splits by paragraph/section boundaries
- fixed: Splits into fixed-size chunks with optional overlap
"""

import logging
import re
from typing import List, Optional

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ChunkerService(models.AbstractModel):
    """Service for splitting document text into chunks."""

    _name = 'ai.chunker.service'
    _description = 'AI Document Chunker Service'
    _inherit = 'ai.base.service'

    # Default separators for recursive splitting (ordered by priority)
    RECURSIVE_SEPARATORS = ['\n\n\n', '\n\n', '\n', '. ', '! ', '? ', ', ', ' ', '']

    # ---- Main API ----

    @api.model
    def chunk_document(self, document, strategy='recursive', chunk_size=512, chunk_overlap=50):
        """
        Split a document's text into chunks.

        :param document: ai.document record
        :param strategy: chunking strategy ('recursive', 'token', 'semantic', 'fixed')
        :param chunk_size: target size per chunk (in characters or tokens)
        :param chunk_overlap: overlap between consecutive chunks (chars)
        :return: list of created ai.chunk record ids
        """
        self.ensure_one()

        text = document.raw_text
        if not text:
            self.log_warning(f'Document {document.name} has no raw text to chunk.')
            return []

        # Remove existing chunks if re-chunking
        document.chunk_ids.unlink()

        self.log_info(f'Chunking document: {document.name} (strategy: {strategy}, size: {chunk_size})')

        # Select strategy
        strategy_map = {
            'recursive': self._chunk_recursive,
            'token': self._chunk_by_tokens,
            'semantic': self._chunk_semantic,
            'fixed': self._chunk_fixed,
        }
        chunker = strategy_map.get(strategy, self._chunk_recursive)
        chunk_texts = chunker(text, chunk_size, chunk_overlap)

        # Create chunk records
        chunks = self._create_chunks(document, chunk_texts, strategy)

        self.log_info(f'Created {len(chunks)} chunks for document {document.name}')
        return chunks

    # ---- Chunking Strategies ----

    @api.model
    def _chunk_recursive(self, text, chunk_size, chunk_overlap):
        """
        Recursive chunking: split by largest separator first,
        then recursively on smaller separators if chunks are too large.
        """
        return self._recursive_split(text, self.RECURSIVE_SEPARATORS, chunk_size, chunk_overlap)

    @api.model
    def _recursive_split(self, text, separators, chunk_size, chunk_overlap):
        """Recursive splitting implementation."""
        chunks = []
        current_chunk = ''
        separator = separators[0] if separators else ''

        if not separator:
            # No more separators, split by exact size
            return self._chunk_fixed(text, chunk_size, chunk_overlap)

        segments = text.split(separator)

        for segment in segments:
            if not segment.strip():
                continue

            if len(current_chunk) + len(separator) + len(segment) <= chunk_size:
                current_chunk = current_chunk + separator + segment if current_chunk else segment
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())

                # Check if single segment exceeds chunk size
                if len(segment) > chunk_size:
                    # Recursively split with next separator
                    sub_chunks = self._recursive_split(
                        segment, separators[1:], chunk_size, chunk_overlap
                    )
                    chunks.extend(sub_chunks)
                    current_chunk = ''
                else:
                    current_chunk = segment

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk.strip())

        # Apply overlap by merging chunks if needed
        return self._apply_overlap(chunks, chunk_overlap)

    @api.model
    def _chunk_by_tokens(self, text, chunk_size, chunk_overlap):
        """
        Token-aware chunking: estimates tokens (~4 chars per token)
        and splits at natural boundaries near the token limit.
        """
        # Convert chunk_size (tokens) to approximate character count
        char_size = chunk_size * 4
        char_overlap = chunk_overlap * 4

        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = ''

        for sentence in sentences:
            if not sentence.strip():
                continue

            if len(current_chunk) + len(sentence) <= char_size:
                current_chunk = current_chunk + ' ' + sentence if current_chunk else sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # If single sentence is too long, split it further
                if len(sentence) > char_size:
                    sub_chunks = self._chunk_fixed(sentence, char_size, char_overlap)
                    chunks.extend(sub_chunks)
                    current_chunk = ''
                else:
                    current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return self._apply_overlap(chunks, char_overlap)

    @api.model
    def _chunk_semantic(self, text, chunk_size, chunk_overlap):
        """
        Semantic chunking: splits by paragraphs/sections.
        Respects natural document structure.
        """
        # Split by double newlines (paragraphs)
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        chunks = []
        current_chunk = ''

        for para in paragraphs:
            if not para:
                continue

            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk = current_chunk + '\n\n' + para if current_chunk else para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(para) > chunk_size:
                    # Long paragraph, split by sentences
                    sub_chunks = self._chunk_by_tokens(para, chunk_size, chunk_overlap)
                    chunks.extend(sub_chunks)
                    current_chunk = ''
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        return self._apply_overlap(chunks, chunk_overlap)

    @api.model
    def _chunk_fixed(self, text, chunk_size, chunk_overlap):
        """
        Fixed-size chunking: splits text into chunks of exact size
        with optional overlap.
        """
        if not text:
            return []

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + chunk_size, text_len)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += chunk_size - chunk_overlap if chunk_overlap else chunk_size

        return chunks

    # ---- Helper Methods ----

    @api.model
    def _apply_overlap(self, chunks, overlap):
        """Apply overlap between consecutive chunks."""
        if overlap <= 0 or len(chunks) <= 1:
            return chunks

        overlapped = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                overlapped.append(chunk)
            else:
                # Add suffix from previous chunk
                prev_chunk = chunks[i - 1]
                overlap_text = prev_chunk[-min(overlap, len(prev_chunk)):]
                overlapped.append(overlap_text + chunk)

        return overlapped

    @api.model
    def _create_chunks(self, document, chunk_texts, strategy):
        """Create ai.chunk records from chunk texts."""
        chunks = self.env['ai.chunk']
        for i, chunk_text in enumerate(chunk_texts, start=1):
            if not chunk_text or not chunk_text.strip():
                continue
            chunk = self.env['ai.chunk'].create({
                'document_id': document.id,
                'sequence': i,
                'content': chunk_text.strip(),
                'chunk_strategy': strategy,
                'page_number': 0,
            })
            chunks |= chunk
        return chunks

    @api.model
    def chunk_text(self, text, strategy='recursive', chunk_size=512, chunk_overlap=50):
        """
        Chunk arbitrary text without creating DB records.
        Useful for query chunking in RAG.

        :return: list of chunk text strings
        """
        strategy_map = {
            'recursive': self._chunk_recursive,
            'token': self._chunk_by_tokens,
            'semantic': self._chunk_semantic,
            'fixed': self._chunk_fixed,
        }
        chunker = strategy_map.get(strategy, self._chunk_recursive)
        return chunker(text, chunk_size, chunk_overlap)
