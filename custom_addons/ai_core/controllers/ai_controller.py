# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
AI REST API Controller
======================
Provides REST API endpoints for AI chat functionality.

Endpoints:
- POST /api/ai/chat          - Main AI chat endpoint
- POST /api/ai/chat/stream   - Streaming chat (SSE)
- GET  /api/ai/health        - Health check
- GET  /api/ai/conversations  - List conversations
- POST /api/ai/search        - Semantic search
"""

import json
import logging
from datetime import datetime

from odoo import http, _
from odoo.http import request, Response
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class AiChatController(http.Controller):
    """REST API controller for AI chat and related functionality."""

    # ---- Auth Helpers ----

    def _get_json_data(self):
        """Parse JSON request data."""
        try:
            raw_data = request.httprequest.data
            if raw_data:
                return json.loads(raw_data)
            return {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _error_response(self, message, code=400):
        """Return a standardized error response."""
        return {
            'jsonrpc': '2.0',
            'error': {
                'code': code,
                'message': message,
            },
        }

    def _success_response(self, data):
        """Return a standardized success response."""
        return {
            'jsonrpc': '2.0',
            'result': data,
        }

    # ============================================================
    # POST /api/ai/chat
    # ============================================================

    @http.route('/api/ai/chat', type='http', auth='user', methods=['POST'], csrf=False, cors='*')
    def chat(self):
        """
        Main AI Chat API endpoint.

        Request body (JSON):
        {
            "conversation_id": int (optional, creates new if omitted),
            "message": "User message text",
            "use_rag": bool (optional, default: true),
            "use_crm_context": bool (optional, default: true),
            "model": "model-name" (optional),
            "temperature": float (optional),
            "max_tokens": int (optional)
        }

        Response:
        {
            "jsonrpc": "2.0",
            "result": {
                "conversation_id": int,
                "user_message": { "content": "...", "create_date": "..." },
                "ai_message": {
                    "content": "...",
                    "model": "gpt-4o-mini",
                    "tokens_used": 123,
                    "rag_context_used": true,
                    "crm_context_used": true,
                    "response_time_ms": 1500
                },
                "rag_sources": [ ... ]  // if RAG was used
            }
        }
        """
        try:
            data = self._get_json_data()
            message = data.get('message', '').strip()
            if not message:
                return Response(
                    json.dumps(self._error_response('Message cannot be empty', 400)),
                    content_type='application/json',
                    status=400,
                )

            # Get or create conversation
            conversation_id = data.get('conversation_id')
            if conversation_id:
                conversation = request.env['ai.conversation'].sudo().browse(conversation_id)
                if not conversation.exists():
                    return Response(
                        json.dumps(self._error_response('Conversation not found', 404)),
                        content_type='application/json',
                        status=404,
                    )
            else:
                conversation = request.env['ai.conversation'].sudo().create({
                    'name': f'Chat {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                    'user_id': request.env.user.id,
                })

            # Apply optional overrides
            if data.get('model'):
                conversation.model_name = data['model']
            if data.get('temperature') is not None:
                conversation.temperature = float(data['temperature'])
            if data.get('max_tokens'):
                conversation.max_tokens = int(data['max_tokens'])
            if data.get('use_rag') is not None:
                conversation.use_rag = bool(data['use_rag'])
            if data.get('use_crm_context') is not None:
                conversation.use_crm_context = bool(data['use_crm_context'])

            # Link documents if provided
            if data.get('document_ids'):
                documents = request.env['ai.document'].sudo().browse(data['document_ids'])
                if documents:
                    conversation.document_ids = [(6, 0, documents.ids)]

            # Link partners if provided
            if data.get('partner_ids'):
                partners = request.env['res.partner'].sudo().browse(data['partner_ids'])
                if partners:
                    conversation.partner_ids = [(6, 0, partners.ids)]

            # Link sale orders if provided
            if data.get('sale_order_ids'):
                orders = request.env['sale.order'].sudo().browse(data['sale_order_ids'])
                if orders:
                    conversation.sale_order_ids = [(6, 0, orders.ids)]

            # Send message and get response
            result = conversation.send_message(
                content=message,
                use_rag=data.get('use_rag', conversation.use_rag),
                use_crm_context=data.get('use_crm_context', conversation.use_crm_context),
            )

            # Add conversation_id to response
            response_data = {
                'conversation_id': conversation.id,
                **result,
            }

            # Include RAG source info if available
            if result.get('ai_message', {}).get('rag_context_used'):
                rag_sources = conversation._get_rag_context(message)
                if rag_sources:
                    response_data['rag_sources'] = [
                        {
                            'content': s.get('content', '')[:200],
                            'document': s.get('document_name', ''),
                            'score': round(s.get('score', 0), 3),
                        }
                        for s in rag_sources[:5]
                    ]

            return Response(
                json.dumps(self._success_response(response_data)),
                content_type='application/json',
                status=200,
            )

        except UserError as e:
            return Response(
                json.dumps(self._error_response(str(e), 400)),
                content_type='application/json',
                status=400,
            )
        except AccessError as e:
            return Response(
                json.dumps(self._error_response('Access denied', 403)),
                content_type='application/json',
                status=403,
            )
        except Exception as e:
            _logger.exception('Chat API error')
            return Response(
                json.dumps(self._error_response(f'Internal server error: {str(e)}', 500)),
                content_type='application/json',
                status=500,
            )

    # ============================================================
    # POST /api/ai/chat/stream (Server-Sent Events)
    # ============================================================

    @http.route('/api/ai/chat/stream', type='http', auth='user', methods=['POST'], csrf=False, cors='*')
    def chat_stream(self):
        """
        Streaming chat endpoint using Server-Sent Events (SSE).
        Same parameters as /api/ai/chat but returns streaming response.

        NOTE: For full streaming support, an async-compatible AI backend
        is required. This endpoint currently returns the full response
        wrapped in SSE format for compatibility.
        """
        data = self._get_json_data()
        message = data.get('message', '').strip()

        if not message:
            return Response(
                json.dumps(self._error_response('Message cannot be empty', 400)),
                content_type='application/json',
                status=400,
            )

        # For now, use the synchronous endpoint and wrap in SSE
        # In production, this would use an actual streaming implementation
        def generate():
            # Get or create conversation
            conversation_id = data.get('conversation_id')
            if conversation_id:
                conversation = request.env['ai.conversation'].sudo().browse(conversation_id)
                if not conversation.exists():
                    yield f'data: {json.dumps({"error": "Conversation not found"})}\n\n'
                    return
            else:
                conversation = request.env['ai.conversation'].sudo().create({
                    'name': f'Chat {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                    'user_id': request.env.user.id,
                })

            try:
                result = conversation.send_message(content=message)
                response_data = {
                    'conversation_id': conversation.id,
                    **result,
                }
                yield f'data: {json.dumps(response_data)}\n\n'
                yield 'data: [DONE]\n\n'
            except Exception as e:
                yield f'data: {json.dumps({"error": str(e)})}\n\n'

        return Response(
            generate(),
            content_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            },
        )

    # ============================================================
    # GET /api/ai/health
    # ============================================================

    @http.route('/api/ai/health', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def health_check(self):
        """
        AI service health check endpoint.

        Returns status of all AI subsystems.
        """
        try:
            chat_service = request.env['ai.chat.service'].sudo()
            vector_store = request.env['ai.vector.store.service'].sudo()
            embedding_service = request.env['ai.embedding.service'].sudo()

            health = {
                'status': 'healthy',
                'version': '1.0.0',
                'timestamp': datetime.now().isoformat(),
                'services': {
                    'chat': chat_service.health_check(),
                    'vector_store': vector_store.health_check(),
                    'embedding': {
                        'backend': embedding_service._get_backend(),
                        'model': embedding_service._get_model(),
                        'dimensions': embedding_service._get_dimensions(),
                    },
                },
                'system': {
                    'user': request.env.user.name,
                    'company': request.env.company.name,
                    'db': request.env.cr.dbname,
                },
            }

            return Response(
                json.dumps(health),
                content_type='application/json',
                status=200,
            )

        except Exception as e:
            return Response(
                json.dumps({
                    'status': 'unhealthy',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat(),
                }),
                content_type='application/json',
                status=503,
            )

    # ============================================================
    # GET /api/ai/conversations
    # ============================================================

    @http.route('/api/ai/conversations', type='http', auth='user', methods=['GET'], csrf=False, cors='*')
    def list_conversations(self):
        """
        List conversations for the current user.

        Query params:
        - limit: int (default: 20)
        - offset: int (default: 0)
        - state: str (active, archived, closed)
        """
        try:
            limit = int(request.params.get('limit', 20))
            offset = int(request.params.get('offset', 0))
            state = request.params.get('state', 'active')

            domain = [('user_id', '=', request.env.user.id)]
            if state:
                domain.append(('state', '=', state))

            conversations = request.env['ai.conversation'].sudo().search(
                domain,
                limit=min(limit, 100),
                offset=offset,
                order='write_date DESC',
            )

            result = []
            for conv in conversations:
                last_msg = conv.chat_message_ids.filtered(
                    lambda m: m.role == 'assistant'
                ).sorted(key=lambda m: m.id)[-1:] if conv.message_ids else []

                result.append({
                    'id': conv.id,
                    'name': conv.name,
                    'state': conv.state,
                    'message_count': conv.message_count,
                    'last_message': last_msg[0].content[:200] if last_msg else '',
                    'last_message_date': conv.last_message_date.isoformat() if conv.last_message_date else None,
                    'write_date': conv.write_date.isoformat() if conv.write_date else None,
                })

            return Response(
                json.dumps(self._success_response({
                    'conversations': result,
                    'total': len(result),
                    'limit': limit,
                    'offset': offset,
                })),
                content_type='application/json',
                status=200,
            )

        except Exception as e:
            return Response(
                json.dumps(self._error_response(str(e), 500)),
                content_type='application/json',
                status=500,
            )

    # ============================================================
    # GET /api/ai/conversations/<id>
    # ============================================================

    @http.route('/api/ai/conversations/<int:conversation_id>', type='http', auth='user',
                methods=['GET'], csrf=False, cors='*')
    def get_conversation(self, conversation_id):
        """Get conversation details including messages."""
        try:
            conversation = request.env['ai.conversation'].sudo().browse(conversation_id)
            if not conversation.exists():
                return Response(
                    json.dumps(self._error_response('Conversation not found', 404)),
                    content_type='application/json',
                    status=404,
                )

            messages = []
            for msg in conversation.chat_message_ids:
                messages.append({
                    'id': msg.id,
                    'role': msg.role,
                    'content': msg.content,
                    'model': msg.model_name,
                    'tokens_used': msg.tokens_used,
                    'rag_context_used': msg.rag_context_used,
                    'crm_context_used': msg.crm_context_used,
                    'create_date': msg.create_date.isoformat() if msg.create_date else None,
                })

            return Response(
                json.dumps(self._success_response({
                    'conversation': {
                        'id': conversation.id,
                        'name': conversation.name,
                        'state': conversation.state,
                        'model': conversation.model_name,
                        'temperature': conversation.temperature,
                        'system_prompt': conversation.system_prompt,
                        'use_rag': conversation.use_rag,
                        'use_crm_context': conversation.use_crm_context,
                        'partner_ids': conversation.partner_ids.ids,
                        'sale_order_ids': conversation.sale_order_ids.ids,
                        'document_ids': conversation.document_ids.ids,
                        'total_tokens_used': conversation.total_tokens_used,
                        'total_messages': conversation.total_messages,
                        'last_message_date': conversation.last_message_date.isoformat() if conversation.last_message_date else None,
                    },
                    'messages': messages,
                    'message_count': len(messages),
                })),
                content_type='application/json',
                status=200,
            )

        except Exception as e:
            return Response(
                json.dumps(self._error_response(str(e), 500)),
                content_type='application/json',
                status=500,
            )

    # ============================================================
    # POST /api/ai/search
    # ============================================================

    @http.route('/api/ai/search', type='http', auth='user', methods=['POST'], csrf=False, cors='*')
    def semantic_search(self):
        """
        Semantic search over indexed documents.

        Request body (JSON):
        {
            "query": "search query text",
            "document_ids": [int, ...] (optional, restrict to specific documents),
            "limit": int (default: 10),
            "threshold": float (default: 0.6)
        }
        """
        try:
            data = self._get_json_data()
            query = data.get('query', '').strip()
            if not query:
                return Response(
                    json.dumps(self._error_response('Query cannot be empty', 400)),
                    content_type='application/json',
                    status=400,
                )

            limit = min(int(data.get('limit', 10)), 50)
            threshold = float(data.get('threshold', 0.6))
            document_ids = data.get('document_ids')

            # Use RAG service for search
            RagService = request.env['ai.rag.service'].sudo()
            result = RagService.retrieve_context(
                query=query,
                document_ids=document_ids,
                top_k=limit,
                threshold=threshold,
            )

            search_results = []
            for chunk in result.get('chunks', []):
                search_results.append({
                    'chunk_id': chunk.get('chunk_id'),
                    'document_id': chunk.get('document_id'),
                    'document_name': chunk.get('document_name', ''),
                    'content': chunk.get('content', ''),
                    'score': round(chunk.get('score', 0), 4),
                })

            return Response(
                json.dumps(self._success_response({
                    'query': query,
                    'results': search_results,
                    'total': len(search_results),
                    'limit': limit,
                    'threshold': threshold,
                })),
                content_type='application/json',
                status=200,
            )

        except Exception as e:
            _logger.exception('Semantic search error')
            return Response(
                json.dumps(self._error_response(str(e), 500)),
                content_type='application/json',
                status=500,
            )
