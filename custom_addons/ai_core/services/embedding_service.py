# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Embedding Service
=================
Generates vector embeddings for text chunks using various backends.

Supported backends:
- OpenAI API (text-embedding-ada-002, text-embedding-3-small, etc.)
- Local mock embedding (for development/testing)
- Pluggable architecture for custom backends

Configuration is stored in ai.vector.index and system parameters.
"""

import json
import logging
import hashlib
import math
import time
from typing import List, Optional

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
    _logger.warning('requests not available. OpenAI embedding will not work.')


class EmbeddingService(models.AbstractModel):
    """Service for generating vector embeddings from text."""

    _name = 'ai.embedding.service'
    _description = 'AI Embedding Service'
    _inherit = 'ai.base.service'

    # ---- Configuration Keys ----
    CONFIG_OPENAI_API_KEY = 'ai_core.openai_api_key'
    CONFIG_OPENAI_MODEL = 'ai_core.embedding_model'
    CONFIG_EMBEDDING_DIMENSIONS = 'ai_core.embedding_dimensions'
    CONFIG_EMBEDDING_BACKEND = 'ai_core.embedding_backend'

    # ---- Main API ----

    @api.model
    def generate_embeddings(self, document, model='text-embedding-ada-002'):
        """
        Generate embeddings for all chunks of a document.

        :param document: ai.document record
        :param model: embedding model name
        :return: list of created ai.embedding record ids
        """
        self.ensure_one()

        chunks = document.chunk_ids
        if not chunks:
            self.log_warning(f'No chunks found for document {document.name}')
            return []

        # Remove any existing embeddings for this document
        document.embedding_ids.unlink()

        # Get the vector index (create default if needed)
        dimensions = document.embedding_dimensions or 1536
        vector_index = document.vector_index_id or \
            self.env['ai.vector.index'].get_or_create_default_index(dimensions, model)

        self.log_info(f'Generating embeddings for {len(chunks)} chunks of {document.name}')

        created_embeddings = []
        batch_size = 20  # Process in batches for API efficiency

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [chunk.content for chunk in batch]

            try:
                vectors = self._generate_embeddings_batch(texts, model)

                for chunk, vector in zip(batch, vectors):
                    if vector:
                        embedding = self.env['ai.embedding'].create({
                            'document_id': document.id,
                            'chunk_id': chunk.id,
                            'vector_index_id': vector_index.id,
                            'vector': self.env['ai.embedding']._vector_to_binary(vector),
                            'vector_dimensions': len(vector),
                            'model_name': model,
                        })
                        created_embeddings.append(embedding)

                self.log_info(f'Processed batch {i // batch_size + 1}: {len(batch)} chunks')

            except Exception as e:
                self.log_error(f'Embedding generation failed for batch: {e}', exc_info=True)
                # Continue with next batch
                continue

        self.log_info(f'Generated {len(created_embeddings)} embeddings')
        return created_embeddings

    # ---- Embedding Generation Backends ----

    @api.model
    def _generate_embeddings_batch(self, texts: List[str], model: str) -> List[Optional[List[float]]]:
        """
        Generate embeddings for a batch of texts.
        Routes to the configured backend.

        :param texts: list of text strings
        :param model: model name
        :return: list of embedding vectors (list of floats) or None on failure
        """
        backend = self._get_backend()
        self.log_info(f'Using embedding backend: {backend}, model: {model}')

        backends = {
            'openai': self._embed_openai,
            'mock': self._embed_mock,
            'local': self._embed_mock,  # Placeholder for local models
        }

        embedder = backends.get(backend, self._embed_mock)
        return embedder(texts, model)

    # ---- OpenAI Backend ----

    @api.model
    def _embed_openai(self, texts: List[str], model: str) -> List[Optional[List[float]]]:
        """Generate embeddings using OpenAI API."""
        if not _HAS_REQUESTS:
            self.log_warning('requests library not available. Using mock embeddings.')
            return self._embed_mock(texts, model)

        api_key = self._get_openai_api_key()
        if not api_key:
            self.log_warning('OpenAI API key not configured. Using mock embeddings.')
            return self._embed_mock(texts, model)

        url = 'https://api.openai.com/v1/embeddings'
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        data = {
            'input': texts,
            'model': model,
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            result = response.json()

            # Parse response
            embeddings = [None] * len(texts)
            for item in result.get('data', []):
                index = item.get('index')
                if index is not None and 0 <= index < len(texts):
                    embeddings[index] = item.get('embedding')

            return embeddings

        except requests.exceptions.Timeout:
            self.log_error('OpenAI API request timed out')
            return self._embed_mock(texts, model)
        except requests.exceptions.RequestException as e:
            self.log_error(f'OpenAI API request failed: {e}')
            return self._embed_mock(texts, model)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            self.log_error(f'Failed to parse OpenAI response: {e}')
            return self._embed_mock(texts, model)

    # ---- Mock/Testing Backend ----

    @api.model
    def _embed_mock(self, texts: List[str], model: str) -> List[Optional[List[float]]]:
        """
        Generate deterministic mock embeddings for development/testing.
        Uses text hash to create a pseudo-random but consistent vector.

        :param texts: list of text strings
        :param model: model name (used to determine dimensions)
        """
        dimensions = self._get_dimensions(model)
        results = []

        for text in texts:
            if not text:
                results.append(None)
                continue

            # Create a deterministic vector from text hash
            hash_obj = hashlib.sha256(text.encode('utf-8'))
            hash_bytes = hash_obj.digest()

            vector = []
            for i in range(dimensions):
                # Use hash bytes cyclically to generate pseudo-random values
                byte_val = hash_bytes[i % 32]
                # Normalize to [-1, 1]
                val = (byte_val / 127.5) - 1.0
                # Add some variation based on position
                val += math.sin(i * 0.1) * 0.1
                vector.append(val)

            # Normalize the vector (unit length for cosine similarity)
            magnitude = math.sqrt(sum(v * v for v in vector))
            if magnitude > 0:
                vector = [v / magnitude for v in vector]

            results.append(vector)

        return results

    # ---- Search Methods ----

    @api.model
    def search_similar(self, query, document_ids=None, limit=5, threshold=0.6):
        """
        Search for similar chunks given a text query.

        :param query: query text string
        :param document_ids: optional list of document IDs to restrict search
        :param limit: max results
        :param threshold: minimum similarity score
        :return: list of dicts with chunk info
        """
        # Generate query embedding
        vectors = self._generate_embeddings_batch([query], self._get_model())
        if not vectors or not vectors[0]:
            self.log_warning('Failed to generate query embedding')
            return []

        query_vector = vectors[0]

        # Search in vector store
        domain = [('active', '=', True)]
        if document_ids:
            domain.append(('document_id', 'in', document_ids))

        embeddings = self.env['ai.embedding'].search(domain)
        return embeddings.search_similar(query_vector, limit=limit, threshold=threshold)

    # ---- Configuration Helpers ----

    @api.model
    def _get_backend(self) -> str:
        """Get the configured embedding backend."""
        param = self.env['ir.config_parameter'].sudo()
        return param.get_param(self.CONFIG_EMBEDDING_BACKEND, 'mock')

    @api.model
    def _get_openai_api_key(self) -> str:
        """Get the OpenAI API key from config."""
        param = self.env['ir.config_parameter'].sudo()
        return param.get_param(self.CONFIG_OPENAI_API_KEY, '')

    @api.model
    def _get_model(self) -> str:
        """Get the configured embedding model."""
        param = self.env['ir.config_parameter'].sudo()
        return param.get_param(self.CONFIG_OPENAI_MODEL, 'text-embedding-ada-002')

    @api.model
    def _get_dimensions(self, model: str = '') -> int:
        """Get vector dimensions for a model."""
        model_dims = {
            'text-embedding-ada-002': 1536,
            'text-embedding-3-small': 1536,
            'text-embedding-3-large': 3072,
        }
        dimensions = model_dims.get(model, 1536)

        # Allow override via config
        param = self.env['ir.config_parameter'].sudo()
        config_dims = param.get_param(self.CONFIG_EMBEDDING_DIMENSIONS, '')
        if config_dims and config_dims.isdigit():
            dimensions = int(config_dims)

        return dimensions

    @api.model
    def configure_backend(self, backend='mock', api_key='', model='text-embedding-ada-002', dimensions=1536):
        """
        Configure the embedding backend through the UI.

        :param backend: 'openai', 'mock', or 'local'
        :param api_key: API key for external services
        :param model: model name
        :param dimensions: vector dimensions
        """
        param = self.env['ir.config_parameter'].sudo()
        param.set_param(self.CONFIG_EMBEDDING_BACKEND, backend)
        param.set_param(self.CONFIG_EMBEDDING_DIMENSIONS, str(dimensions))
        param.set_param(self.CONFIG_OPENAI_MODEL, model)

        if api_key:
            param.set_param(self.CONFIG_OPENAI_API_KEY, api_key)

        self.log_info(f'Configured embedding backend: {backend}, model: {model}')
        return True
