# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ---- Chat Backend ----
    ai_chat_backend = fields.Selection(
        string='AI聊天后端',
        selection=[
            ('mock', 'Mock（开发/测试）'),
            ('openai', 'OpenAI API'),
            ('deepseek', 'DeepSeek API'),
            ('qwen', '通义千问 (Qwen) API'),
            ('openai_compatible', '自定义OpenAI兼容'),
        ],
        default='mock',
        config_parameter='ai_core.chat_backend',
    )
    ai_openai_api_key = fields.Char(
        string='API密钥',
        config_parameter='ai_core.openai_api_key',
    )
    ai_chat_model = fields.Char(
        string='聊天模型',
        default='deepseek-chat',
        config_parameter='ai_core.chat_model',
    )
    ai_custom_endpoint = fields.Char(
        string='自定义端点',
        config_parameter='ai_core.chat_endpoint',
    )

    # ---- Embedding Backend ----
    ai_embedding_backend = fields.Selection(
        string='嵌入后端',
        selection=[
            ('mock', 'Mock（开发/测试）'),
            ('openai', 'OpenAI API'),
            ('qwen', '通义千问 (Qwen) API'),
            ('openai_compatible', '自定义OpenAI兼容'),
        ],
        default='mock',
        config_parameter='ai_core.embedding_backend',
    )
    ai_embedding_model = fields.Char(
        string='嵌入模型',
        default='text-embedding-v2',
        config_parameter='ai_core.embedding_model',
    )
    ai_embedding_dimensions = fields.Integer(
        string='嵌入维度',
        default=1536,
        config_parameter='ai_core.embedding_dimensions',
    )

    # ---- Chunking Defaults ----
    ai_default_chunk_strategy = fields.Selection(
        string='默认分块策略',
        selection=[
            ('recursive', 'Recursive Split'),
            ('token', 'Token-based'),
            ('semantic', 'Semantic (by paragraph)'),
            ('fixed', 'Fixed Size'),
        ],
        default='recursive',
        config_parameter='ai_core.default_chunk_strategy',
    )
    ai_default_chunk_size = fields.Integer(
        string='默认分块大小',
        default=512,
        config_parameter='ai_core.default_chunk_size',
    )
    ai_default_chunk_overlap = fields.Integer(
        string='默认分块重叠',
        default=50,
        config_parameter='ai_core.default_chunk_overlap',
    )

    # ---- Backend Switching Helpers ----

    @api.onchange('ai_chat_backend')
    def _onchange_ai_chat_backend(self):
        """Auto-fill model and endpoint when backend changes."""
        presets = {
            'openai': {
                'ai_chat_model': 'gpt-4o-mini',
                'ai_custom_endpoint': 'https://api.openai.com/v1/chat/completions',
            },
            'deepseek': {
                'ai_chat_model': 'deepseek-chat',
                'ai_custom_endpoint': 'https://api.deepseek.com/v1/chat/completions',
            },
            'qwen': {
                'ai_chat_model': 'qwen-plus',
                'ai_custom_endpoint': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
            },
            'mock': {
                'ai_chat_model': 'gpt-4o-mini',
                'ai_custom_endpoint': False,
            },
            'openai_compatible': {
                'ai_chat_model': False,
                'ai_custom_endpoint': False,
            },
        }
        preset = presets.get(self.ai_chat_backend, {})
        if preset.get('ai_chat_model'):
            self.ai_chat_model = preset['ai_chat_model']
        if preset.get('ai_custom_endpoint'):
            self.ai_custom_endpoint = preset['ai_custom_endpoint']

    @api.onchange('ai_embedding_backend')
    def _onchange_ai_embedding_backend(self):
        """Auto-fill embedding model when backend changes."""
        presets = {
            'openai': {
                'ai_embedding_model': 'text-embedding-ada-002',
            },
            'qwen': {
                'ai_embedding_model': 'text-embedding-v2',
            },
            'mock': {
                'ai_embedding_model': 'text-embedding-ada-002',
            },
            'openai_compatible': {
                'ai_embedding_model': False,
            },
        }
        preset = presets.get(self.ai_embedding_backend, {})
        if preset.get('ai_embedding_model'):
            self.ai_embedding_model = preset['ai_embedding_model']
