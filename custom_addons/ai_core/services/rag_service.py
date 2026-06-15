# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
RAG Service (Retrieval-Augmented Generation)
=============================================
Orchestrates the retrieval of relevant document chunks and formats
them as context for the AI chat service.

Pipeline:
1. Query embedding generation
2. Vector similarity search
3. Context assembly and ranking
4. Context formatting for LLM prompt
"""

import json
import logging
from typing import List, Optional

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class RagService(models.AbstractModel):
    """Service for Retrieval-Augmented Generation."""

    _name = 'ai.rag.service'
    _description = 'AI RAG Service'
    _inherit = 'ai.base.service'

    # ---- Main API ----

    @api.model
    def retrieve_context(self, query, document_ids=None, top_k=5, threshold=0.6):
        """
        Retrieve relevant context for a query.

        :param query: the user's query text
        :param document_ids: optional list of document IDs to restrict search
        :param top_k: number of chunks to retrieve
        :param threshold: minimum similarity threshold
        :return: dict with retrieved chunks and formatted context
        """
        self.log_info(f'Retrieving context for query: "{query[:50]}..."')

        # Step 1: Search for similar chunks
        EmbeddingService = self.env['ai.embedding.service']
        chunks = EmbeddingService.search_similar(
            query=query,
            document_ids=document_ids,
            limit=top_k,
            threshold=threshold,
        )

        # Step 2: Rerank and format
        if not chunks:
            self.log_info('No relevant chunks found')
            return {
                'chunks': [],
                'context': '',
                'chunk_count': 0,
            }

        # Step 3: Sort by score descending
        chunks.sort(key=lambda x: x.get('score', 0), reverse=True)

        # Step 4: Build formatted context
        context = self._format_context(chunks)

        self.log_info(f'Retrieved {len(chunks)} chunks, context length: {len(context)} chars')

        return {
            'chunks': chunks,
            'context': context,
            'chunk_count': len(chunks),
        }

    @api.model
    def retrieve_context_from_texts(self, query, texts, top_k=5):
        """
        Retrieve relevant chunks from a provided text list (no DB).
        Useful for ad-hoc RAG without stored documents.

        :param query: query text
        :param texts: list of text strings to search
        :param top_k: number of results
        :return: dict with results
        """
        if not texts:
            return {'chunks': [], 'context': '', 'chunk_count': 0}

        # Generate query embedding
        EmbeddingService = self.env['ai.embedding.service']
        vectors = EmbeddingService._generate_embeddings_batch(
            [query], EmbeddingService._get_model()
        )

        if not vectors or not vectors[0]:
            return {'chunks': [], 'context': '', 'chunk_count': 0}

        query_vector = vectors[0]

        # Generate embeddings for all texts
        text_vectors = EmbeddingService._generate_embeddings_batch(
            texts, EmbeddingService._get_model()
        )

        # Compute similarities
        import math

        def cosine_sim(a, b):
            if not a or not b:
                return 0.0
            dot = sum(x * y for x, y in zip(a, b))
            n_a = math.sqrt(sum(x * x for x in a))
            n_b = math.sqrt(sum(y * y for y in b))
            return dot / (n_a * n_b) if n_a and n_b else 0.0

        scored = []
        for i, (text, vec) in enumerate(zip(texts, text_vectors)):
            if vec:
                score = cosine_sim(query_vector, vec)
                scored.append({
                    'index': i,
                    'content': text,
                    'score': score,
                })

        scored.sort(key=lambda x: x['score'], reverse=True)
        top = scored[:top_k]

        context = self._format_context(top)

        return {
            'chunks': top,
            'context': context,
            'chunk_count': len(top),
        }

    @api.model
    def query_with_rag(self, query, document_ids=None, top_k=5, threshold=0.6):
        """
        One-shot: retrieve context and return it ready for LLM.

        :return: dict with query, context, chunks
        """
        result = self.retrieve_context(query, document_ids, top_k, threshold)
        result['query'] = query

        # Build a prompt-ready context string
        if result['context']:
            result['prompt_context'] = (
                'Here is relevant information from the knowledge base:\n\n'
                f'{result["context"]}\n\n'
                'Please answer the user\'s question based on the above context. '
                'If the context doesn\'t contain enough information to answer, '
                'say so and provide a general response.'
            )
        else:
            result['prompt_context'] = (
                'No specific knowledge base results were found for this query. '
                'Please provide a general response based on your training.'
            )

        return result

    # ---- Context Formatting ----

    @api.model
    def _format_context(self, chunks):
        """Format retrieved chunks into a structured context string."""
        if not chunks:
            return ''

        parts = []
        for i, chunk in enumerate(chunks, start=1):
            content = chunk.get('content', '')
            score = chunk.get('score', 0)
            doc_name = chunk.get('document_name', 'Unknown')

            if content:
                parts.append(
                    f'[Source {i}: {doc_name} (relevance: {score:.2f})]\n'
                    f'{content}\n'
                )

        return '\n\n'.join(parts)

    @api.model
    def _format_context_html(self, chunks):
        """Format context as HTML (for UI display)."""
        if not chunks:
            return '<p>No relevant context found.</p>'

        parts = []
        for i, chunk in enumerate(chunks, start=1):
            content = chunk.get('content', '')
            score = chunk.get('score', 0)
            doc_name = chunk.get('document_name', 'Unknown')

            parts.append(
                f'<div class="rag-source">\n'
                f'  <strong>Source {i}:</strong> {doc_name} '
                f'<span class="badge">{(score * 100):.0f}% match</span>\n'
                f'  <p>{content}</p>\n'
                f'</div>'
            )

        return '\n'.join(parts)
