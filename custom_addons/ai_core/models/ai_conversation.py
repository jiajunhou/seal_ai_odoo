# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
from datetime import datetime

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AiConversation(models.Model):
    """Represents an AI chat conversation with context from CRM and documents."""

    _name = 'ai.conversation'
    _description = 'AI Conversation'
    _order = 'write_date DESC'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ---- Core Fields ----
    name = fields.Char(string='Subject', required=True, default='New Conversation')
    state = fields.Selection(
        string='Status',
        selection=[
            ('active', 'Active'),
            ('archived', 'Archived'),
            ('closed', 'Closed'),
        ],
        default='active',
        required=True,
        tracking=True,
    )

    # ---- AI Configuration ----
    model_name = fields.Char(
        string='AI Model',
        default='gpt-4o-mini',
        help='The AI model used for chat completion',
    )
    temperature = fields.Float(string='Temperature', default=0.7, help='Response creativity (0-1)')
    max_tokens = fields.Integer(string='Max Tokens', default=2048, help='Maximum response length')
    system_prompt = fields.Text(
        string='System Prompt',
        default="""You are an AI assistant integrated with Odoo ERP. You have access to CRM data including customers (res.partner) and sales orders (sale.order). 
Use the provided context to answer questions accurately. When referencing specific data, mention the source.
Always be professional, helpful, and concise.""",
        translate=True,
    )

    # ---- Context Configuration ----
    use_rag = fields.Boolean(string='Use RAG Context', default=True, help='Retrieve relevant document chunks')
    use_crm_context = fields.Boolean(string='Use CRM Context', default=True, help='Include CRM data in context')
    top_k_chunks = fields.Integer(string='Top K Chunks', default=5, help='Number of relevant chunks to retrieve')
    similarity_threshold = fields.Float(string='Similarity Threshold', default=0.6, help='Minimum similarity score')

    # ---- Relations ----
    message_ids = fields.One2many('ai.conversation.message', 'conversation_id', string='Messages')
    message_count = fields.Integer(string='Message Count', compute='_compute_message_count', store=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user, required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # ---- CRM Context: Linked Records ----
    partner_ids = fields.Many2many(
        'res.partner',
        string='Related Partners',
        help='Customers/contacts to include in AI context',
    )
    sale_order_ids = fields.Many2many(
        'sale.order',
        string='Related Sales Orders',
        help='Sales orders to include in AI context',
    )
    document_ids = fields.Many2many(
        'ai.document',
        string='Knowledge Base Documents',
        help='Documents to search for RAG',
    )

    # ---- Statistics ----
    total_tokens_used = fields.Integer(string='Total Tokens Used', default=0)
    total_messages = fields.Integer(string='Total Messages', default=0)
    last_message_date = fields.Datetime(string='Last Message Date', readonly=True)

    # ---- Computed ----

    @api.depends('message_ids')
    def _compute_message_count(self):
        for record in self:
            record.message_count = len(record.message_ids)

    # ---- Actions ----

    def action_archive(self):
        self.write({'state': 'archived'})

    def action_unarchive(self):
        self.write({'state': 'active'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_clear_messages(self):
        """Clear all messages but keep the conversation."""
        self.message_ids.unlink()
        self.write({
            'total_tokens_used': 0,
            'total_messages': 0,
            'last_message_date': False,
        })

    def action_view_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Messages'),
            'res_model': 'ai.conversation.message',
            'view_mode': 'tree,form',
            'domain': [('conversation_id', '=', self.id)],
            'context': {'default_conversation_id': self.id},
        }

    # ---- Chat Methods ----

    def send_message(self, content, use_rag=None, use_crm_context=None):
        """
        Send a user message and get AI response.
        
        :param content: The user's message text
        :param use_rag: Override RAG setting
        :param use_crm_context: Override CRM context setting
        :return: dict with 'user_message' and 'ai_message' data
        """
        self.ensure_one()

        use_rag = use_rag if use_rag is not None else self.use_rag
        use_crm_context = use_crm_context if use_crm_context is not None else self.use_crm_context

        # 1. Create user message
        user_msg = self.env['ai.conversation.message'].create({
            'conversation_id': self.id,
            'role': 'user',
            'content': content,
            'model_name': self.model_name,
        })

        # 2. Build context
        rag_context = self._get_rag_context(content) if use_rag else []
        crm_context = self._get_crm_context() if use_crm_context else {}

        # 3. Get AI response
        AiChatService = self.env['ai.chat.service']
        response = AiChatService.chat(
            conversation=self,
            user_message=content,
            rag_context=rag_context,
            crm_context=crm_context,
        )

        # 4. Create AI response message
        ai_msg = self.env['ai.conversation.message'].create({
            'conversation_id': self.id,
            'role': 'assistant',
            'content': response.get('content', ''),
            'model_name': response.get('model', self.model_name),
            'tokens_used': response.get('tokens_used', 0),
            'rag_context_used': bool(rag_context),
            'crm_context_used': use_crm_context,
            'response_time_ms': response.get('response_time_ms', 0),
            'metadata_json': json.dumps(response.get('metadata', {})),
        })

        # 5. Update conversation stats
        self.write({
            'total_messages': self.total_messages + 2,
            'total_tokens_used': self.total_tokens_used + (response.get('tokens_used', 0) or 0),
            'last_message_date': fields.Datetime.now(),
        })

        return {
            'user_message': {
                'id': user_msg.id,
                'content': user_msg.content,
                'create_date': user_msg.create_date,
            },
            'ai_message': {
                'id': ai_msg.id,
                'content': ai_msg.content,
                'model': ai_msg.model_name,
                'tokens_used': ai_msg.tokens_used,
                'rag_context_used': ai_msg.rag_context_used,
                'crm_context_used': ai_msg.crm_context_used,
                'response_time_ms': ai_msg.response_time_ms,
            },
        }

    def _get_rag_context(self, query):
        """Retrieve relevant document chunks for context."""
        if not self.document_ids and not self.env['ai.document'].search_count([]):
            return []

        EmbeddingService = self.env['ai.embedding.service']
        chunks = EmbeddingService.search_similar(
            query=query,
            document_ids=self.document_ids.ids if self.document_ids else None,
            limit=self.top_k_chunks or 5,
            threshold=self.similarity_threshold or 0.6,
        )
        return chunks

    def _get_crm_context(self):
        """Build CRM context from linked partners and sales orders."""
        context = {
            'partners': [],
            'sales_orders': [],
        }

        # Get partners
        partners = self.partner_ids
        if not partners:
            # If no specific partners linked, get recent ones
            partners = self.env['res.partner'].search([
                ('active', '=', True),
            ], limit=10)

        for partner in partners:
            partner_data = {
                'id': partner.id,
                'name': partner.name,
                'email': partner.email or '',
                'phone': partner.phone or '',
                'city': partner.city or '',
                'country': partner.country_id.name or '',
                'is_company': partner.is_company,
            }
            context['partners'].append(partner_data)

        # Get sales orders
        sale_orders = self.sale_order_ids
        if not sale_orders:
            # If no specific orders linked, get recent ones
            sale_orders = self.env['sale.order'].search([
                ('company_id', '=', self.env.company.id),
            ], limit=10, order='date_order DESC')

        for order in sale_orders:
            order_data = {
                'id': order.id,
                'name': order.name,
                'partner': order.partner_id.name,
                'date_order': str(order.date_order) if order.date_order else '',
                'amount_total': order.amount_total,
                'state': order.state,
                'line_count': len(order.order_line),
            }
            context['sales_orders'].append(order_data)

        return context


class AiConversationMessage(models.Model):
    """Individual message in an AI conversation."""

    _name = 'ai.conversation.message'
    _description = 'AI Conversation Message'
    _order = 'id ASC'

    # ---- Core Fields ----
    conversation_id = fields.Many2one(
        'ai.conversation',
        string='Conversation',
        required=True,
        ondelete='cascade',
        index=True,
    )
    role = fields.Selection(
        string='Role',
        selection=[
            ('system', 'System'),
            ('user', 'User'),
            ('assistant', 'Assistant'),
        ],
        required=True,
        default='user',
    )
    content = fields.Text(string='Content', required=True)

    # ---- AI Metadata ----
    model_name = fields.Char(string='Model Used')
    tokens_used = fields.Integer(string='Tokens Used', default=0)
    temperature = fields.Float(string='Temperature')
    response_time_ms = fields.Integer(string='Response Time (ms)')

    # ---- Context Information ----
    rag_context_used = fields.Boolean(string='RAG Context Used', default=False)
    crm_context_used = fields.Boolean(string='CRM Context Used', default=False)
    rag_chunks_retrieved = fields.Integer(string='RAG Chunks Retrieved', default=0)
    metadata_json = fields.Text(string='Response Metadata (JSON)')

    # ---- Feedback ----
    feedback_rating = fields.Selection(
        string='Rating',
        selection=[
            ('thumbs_up', 'Thumbs Up'),
            ('thumbs_down', 'Thumbs Down'),
        ],
    )
    feedback_comment = fields.Text(string='Feedback Comment')

    # ---- Computed ----
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('role', 'content')
    def _compute_display_name(self):
        for record in self:
            prefix = {'user': '👤', 'assistant': '🤖', 'system': '⚙️'}.get(record.role, '❓')
            preview = record.content[:80] + '...' if record.content and len(record.content) > 80 else (record.content or '')
            record.display_name = f'{prefix} {preview}'
