# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
AI Chat Service
===============
Core service for AI chat completion. Handles:

1. Building conversation context (history, CRM data, RAG results)
2. Calling the AI model API (OpenAI, or mock for testing)
3. Processing and returning responses

Supports:
- OpenAI API (GPT-4, GPT-3.5, etc.)
- Mock mode for testing/development
- Pluggable architecture for custom AI backends
"""

import json
import logging
import time
from datetime import datetime
from typing import List, Optional

from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError

_logger = logging.getLogger(__name__)

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
    _logger.warning('requests not available. OpenAI chat will not work.')


class AiChatService(models.AbstractModel):
    """Service for AI chat completion with RAG and CRM context."""

    _name = 'ai.chat.service'
    _description = 'AI Chat Service'
    _inherit = 'ai.base.service'

    # ---- Configuration Keys ----
    CONFIG_OPENAI_API_KEY = 'ai_core.openai_api_key'
    CONFIG_OPENAI_CHAT_MODEL = 'ai_core.chat_model'
    CONFIG_CHAT_BACKEND = 'ai_core.chat_backend'
    CONFIG_CHAT_ENDPOINT = 'ai_core.chat_endpoint'  # Custom endpoint for local models

    # ---- Main Chat API ----

    @api.model
    def chat(self, conversation, user_message, rag_context=None, crm_context=None):
        """
        Process a chat message and return AI response.

        :param conversation: ai.conversation record
        :param user_message: the user's message string
        :param rag_context: list of RAG chunk dicts (optional)
        :param crm_context: dict with CRM data (optional)
        :return: dict with response data
        """
        start_time = time.time()

        # 1. Build messages for the LLM
        messages = self._build_messages(conversation, user_message, rag_context, crm_context)

        # 2. Get model config
        model = conversation.model_name or self._get_chat_model()
        temperature = conversation.temperature or 0.7
        max_tokens = conversation.max_tokens or 2048

        # 3. Call the AI backend
        try:
            response = self._call_ai_backend(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            self.log_error(f'AI backend call failed: {e}', exc_info=True)
            # Provide a fallback response
            response = {
                'content': self._get_fallback_response(str(e)),
                'model': model,
                'tokens_used': 0,
                'metadata': {'error': str(e), 'fallback': True},
            }

        response_time_ms = int((time.time() - start_time) * 1000)
        response['response_time_ms'] = response_time_ms

        # 4. Log the interaction
        self.log_info(
            f'Chat response: model={model}, '
            f'tokens={response.get("tokens_used", 0)}, '
            f'time={response_time_ms}ms'
        )

        return response

    # ---- Message Builder ----

    @api.model
    def _build_messages(self, conversation, user_message, rag_context=None, crm_context=None):
        """
        Build the messages array for the LLM API call.

        Structure:
        - System prompt (with CRM data context if enabled)
        - Conversation history (last N messages)
        - RAG context (as a system message or user message prefix)
        - Current user message
        """
        messages = []

        # 1. System prompt
        system_content = conversation.system_prompt or self._get_default_system_prompt()

        # 2. Add CRM context to system prompt
        if crm_context:
            crm_block = self._format_crm_context(crm_context)
            if crm_block:
                system_content += f'\n\n### Current CRM Context:\n{crm_block}'

        messages.append({'role': 'system', 'content': system_content})

        # 3. Add RAG context
        if rag_context:
            rag_text = self._format_rag_context(rag_context)
            messages.append({
                'role': 'system',
                'content': f'### Retrieved Knowledge Base Context:\n{rag_text}',
            })

        # 4. Conversation history (last 20 messages to stay within token limits)
        history = conversation.message_ids.filtered(
            lambda m: m.role in ('user', 'assistant')
        ).sorted(key=lambda m: m.id)
        for msg in history[-20:]:  # Last 20 messages
            messages.append({
                'role': msg.role,
                'content': msg.content,
            })

        # 5. Current user message
        messages.append({'role': 'user', 'content': user_message})

        return messages

    # ---- AI Backend Call ----

    @api.model
    def _call_ai_backend(self, messages, model, temperature, max_tokens):
        """Route the call to the configured AI backend."""
        backend = self._get_backend()
        self.log_info(f'Calling AI backend: {backend}, model: {model}')

        backends = {
            'openai': self._call_openai,
            'openai_compatible': self._call_openai_compatible,
            'mock': self._call_mock,
        }

        caller = backends.get(backend, self._call_mock)
        return caller(messages, model, temperature, max_tokens)

    @api.model
    def _call_openai(self, messages, model, temperature, max_tokens):
        """Call OpenAI Chat Completions API."""
        if not _HAS_REQUESTS:
            return self._call_mock(messages, model, temperature, max_tokens)

        api_key = self._get_openai_api_key()
        if not api_key:
            self.log_warning('OpenAI API key not configured. Using mock response.')
            return self._call_mock(messages, model, temperature, max_tokens)

        url = 'https://api.openai.com/v1/chat/completions'
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        data = {
            'model': model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            result = response.json()

            choice = result.get('choices', [{}])[0]
            usage = result.get('usage', {})

            return {
                'content': choice.get('message', {}).get('content', ''),
                'model': result.get('model', model),
                'tokens_used': usage.get('total_tokens', 0),
                'metadata': {
                    'prompt_tokens': usage.get('prompt_tokens', 0),
                    'completion_tokens': usage.get('completion_tokens', 0),
                    'finish_reason': choice.get('finish_reason', ''),
                },
            }

        except requests.exceptions.Timeout:
            self.log_error('OpenAI API request timed out')
            raise UserError(_('AI service timed out. Please try again.'))
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if hasattr(e, 'response') else 0
            if status == 401:
                raise UserError(_('Invalid OpenAI API key. Please check your configuration.'))
            elif status == 429:
                raise UserError(_('Rate limit exceeded. Please wait and try again.'))
            raise UserError(_('AI service error: %s') % str(e))
        except Exception as e:
            self.log_error(f'OpenAI API error: {e}', exc_info=True)
            raise UserError(_('Failed to get AI response: %s') % str(e))

    @api.model
    def _call_openai_compatible(self, messages, model, temperature, max_tokens):
        """
        Call any OpenAI-compatible API (e.g., local Ollama, vLLM, etc.)
        Uses the configured custom endpoint.
        """
        if not _HAS_REQUESTS:
            return self._call_mock(messages, model, temperature, max_tokens)

        endpoint = self._get_custom_endpoint()
        if not endpoint:
            self.log_warning('Custom endpoint not configured. Using mock.')
            return self._call_mock(messages, model, temperature, max_tokens)

        api_key = self._get_openai_api_key()

        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        data = {
            'model': model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }

        try:
            response = requests.post(endpoint, headers=headers, json=data, timeout=180)
            response.raise_for_status()
            result = response.json()

            choice = result.get('choices', [{}])[0]

            return {
                'content': choice.get('message', {}).get('content', ''),
                'model': result.get('model', model),
                'tokens_used': result.get('usage', {}).get('total_tokens', 0),
                'metadata': {
                    'finish_reason': choice.get('finish_reason', ''),
                },
            }

        except Exception as e:
            self.log_error(f'Custom API error: {e}', exc_info=True)
            return self._call_mock(messages, model, temperature, max_tokens)

    @api.model
    def _call_mock(self, messages, model, temperature, max_tokens):
        """
        Mock AI response for development/testing.
        Provides sensible responses based on the conversation context.
        """
        # Extract the last user message
        user_msg = ''
        for msg in reversed(messages):
            if msg['role'] == 'user':
                user_msg = msg['content']
                break

        # Get CRM context if available
        has_crm = any('CRM Context' in msg.get('content', '') for msg in messages)
        has_rag = any('Knowledge Base' in msg.get('content', '') for msg in messages)

        # Generate mock response
        response_text = self._generate_mock_response(user_msg, has_crm, has_rag)

        return {
            'content': response_text,
            'model': f'mock-{model}',
            'tokens_used': len(user_msg.split()) + len(response_text.split()),
            'metadata': {
                'mock': True,
                'has_crm_context': has_crm,
                'has_rag_context': has_rag,
            },
        }

    # ---- Context Formatting ----

    @api.model
    def _format_crm_context(self, crm_context):
        """Format CRM data into a structured text block."""
        if not crm_context:
            return ''

        parts = []

        partners = crm_context.get('partners', [])
        if partners:
            parts.append('--- Customers/Contacts ---')
            for p in partners:
                parts.append(
                    f"- {p.get('name', 'N/A')} "
                    f"(Email: {p.get('email', 'N/A')}, "
                    f"Phone: {p.get('phone', 'N/A')}, "
                    f"Location: {p.get('city', '')}, {p.get('country', '')})"
                )

        orders = crm_context.get('sales_orders', [])
        if orders:
            parts.append('\n--- Sales Orders ---')
            for o in orders:
                parts.append(
                    f"- {o.get('name', 'N/A')}: "
                    f"Customer: {o.get('partner', 'N/A')}, "
                    f"Total: ${o.get('amount_total', 0):.2f}, "
                    f"Status: {o.get('state', 'N/A')}, "
                    f"Lines: {o.get('line_count', 0)}"
                )

        return '\n'.join(parts)

    @api.model
    def _format_rag_context(self, rag_context):
        """Format RAG results into context block."""
        if not rag_context:
            return ''

        parts = []
        for i, chunk in enumerate(rag_context, start=1):
            content = chunk.get('content', '')
            doc_name = chunk.get('document_name', 'Unknown')
            score = chunk.get('score', 0)
            parts.append(f'[{i}] From "{doc_name}" (relevance: {score:.2f}):\n{content}')

        return '\n\n'.join(parts)

    # ---- Mock Response Generator ----

    @api.model
    def _generate_mock_response(self, user_message, has_crm=False, has_rag=False):
        """Generate a realistic mock response for testing."""
        user_lower = user_message.lower()

        # CRM-related queries
        if has_crm:
            if any(word in user_lower for word in ['customer', 'partner', 'contact', 'client']):
                return (
                    "Based on the CRM data, I can see the following customers:\n\n"
                    "1. **John Smith** - john.smith@email.com - New York, USA\n"
                    "2. **ABC Corporation** - info@abccorp.com - San Francisco, USA\n"
                    "3. **Maria Garcia** - maria@email.com - Madrid, Spain\n\n"
                    "I can provide more details about any specific customer if needed. "
                    "You can also ask about their sales orders or interaction history."
                )
            if any(word in user_lower for word in ['order', 'sale', 'revenue', 'amount']):
                return (
                    "Here's a summary of recent sales orders:\n\n"
                    "1. **SO001** - ABC Corporation - $15,000.00 - Confirmed\n"
                    "2. **SO002** - John Smith - $3,200.00 - Draft\n"
                    "3. **SO003** - Maria Garcia - €8,500.00 - Done\n\n"
                    "Total order value across all orders: $26,700.00\n"
                    "Would you like to drill down into any specific order?"
                )

        # RAG-related queries
        if has_rag:
            if any(word in user_lower for word in ['document', 'knowledge', 'rag', 'context']):
                return (
                    "I've retrieved relevant information from the knowledge base. "
                    "The documents I found contain information that can help answer your question. "
                    "Based on the context provided:\n\n"
                    "1. The system processes documents through a pipeline: upload → parse → chunk → embed\n"
                    "2. Multiple chunking strategies are available: recursive, token, semantic, fixed\n"
                    "3. Embeddings are stored using pgvector for efficient similarity search\n\n"
                    "What specific aspect would you like to explore further?"
                )

        # General responses
        return (
            "I'm your AI assistant integrated with Odoo ERP. "
            "I can help you with:\n\n"
            "📊 **CRM Data** - Ask about customers, contacts, and sales orders\n"
            "📄 **Knowledge Base** - Search uploaded documents and retrieve relevant information\n"
            "🔍 **Analysis** - Get insights from your business data\n\n"
            f"Your query was: *\"{user_message[:100]}\"*\n\n"
            "How would you like me to help you today? Please provide more details or ask a specific question."
        )

    # ---- Helper Methods ----

    @api.model
    def _get_default_system_prompt(self):
        """Get the default system prompt."""
        return (
            "You are an AI assistant integrated with Odoo ERP. You have access to CRM data "
            "including customers (res.partner) and sales orders (sale.order). "
            "Use the provided context to answer questions accurately. "
            "When referencing specific data, mention the source. "
            "Always be professional, helpful, and concise."
        )

    @api.model
    def _get_backend(self):
        """Get configured chat backend."""
        param = self.env['ir.config_parameter'].sudo()
        return param.get_param(self.CONFIG_CHAT_BACKEND, 'mock')

    @api.model
    def _get_chat_model(self):
        """Get configured chat model."""
        param = self.env['ir.config_parameter'].sudo()
        return param.get_param(self.CONFIG_OPENAI_CHAT_MODEL, 'gpt-4o-mini')

    @api.model
    def _get_openai_api_key(self):
        """Get OpenAI API key."""
        param = self.env['ir.config_parameter'].sudo()
        return param.get_param(self.CONFIG_OPENAI_API_KEY, '')

    @api.model
    def _get_custom_endpoint(self):
        """Get custom API endpoint."""
        param = self.env['ir.config_parameter'].sudo()
        return param.get_param(self.CONFIG_CHAT_ENDPOINT, '')

    @api.model
    def _get_fallback_response(self, error_msg):
        """Get a fallback response when the AI service fails."""
        return (
            "I apologize, but I'm currently experiencing a connectivity issue. "
            f"Error: {error_msg}\n\n"
            "Please check your AI service configuration and try again. "
            "You can verify your settings in the AI Configuration menu."
        )

    # ---- Configuration ----

    @api.model
    def configure(self, backend='mock', api_key='', model='gpt-4o-mini', endpoint=''):
        """Configure the AI chat service."""
        param = self.env['ir.config_parameter'].sudo()
        param.set_param(self.CONFIG_CHAT_BACKEND, backend)
        param.set_param(self.CONFIG_OPENAI_CHAT_MODEL, model)

        if api_key:
            param.set_param(self.CONFIG_OPENAI_API_KEY, api_key)
        if endpoint:
            param.set_param(self.CONFIG_CHAT_ENDPOINT, endpoint)

        self.log_info(f'Configured chat backend: {backend}, model: {model}')
        return True

    @api.model
    def health_check(self):
        """Check if the AI chat service is properly configured."""
        backend = self._get_backend()
        config_status = {
            'backend': backend,
            'model': self._get_chat_model(),
            'api_key_configured': bool(self._get_openai_api_key()),
            'custom_endpoint': self._get_custom_endpoint() or 'N/A',
            'status': 'ready' if backend == 'mock' else 'needs_configuration',
        }

        if backend == 'openai':
            if config_status['api_key_configured']:
                config_status['status'] = 'configured'
            else:
                config_status['status'] = 'missing_api_key'

        return config_status
