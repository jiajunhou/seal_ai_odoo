# -*- coding: utf-8 -*-
"""
AI Chat Page Controller
=======================
Serves the AI Chat interface as a standalone HTML page.
"""

import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class AiChatPageController(http.Controller):

    @http.route('/ai/chat', type='http', auth='user', methods=['GET'], csrf=False)
    def chat_page(self):
        """Serve the AI Chat full-page interface."""
        return Response(
            self._render_chat_page(),
            content_type='text/html',
            status=200,
        )

    def _render_chat_page(self):
        """Render the chat page HTML."""
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="csrf-token" content="{request.csrf_token()}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 智能聊天</title>
    <style>
        {self._get_chat_styles()}
    </style>
</head>
<body>
    <div id="ai-chat-app">
        <div class="ai-chat-page">
            <!-- Sidebar -->
            <div class="ai-chat-sidebar">
                <div class="ai-chat-sidebar-header">
                    <h3>💬 对话列表</h3>
                    <button onclick="newConversation()" class="new-conv-btn">+ 新对话</button>
                </div>
                <div id="conversation-list" class="ai-chat-conv-list">
                    <div class="ai-chat-loading-text">加载中...</div>
                </div>
            </div>

            <!-- Main Chat Area -->
            <div class="ai-chat-main">
                <div class="ai-chat-header">
                    <h2 id="chat-title">AI 智能助手</h2>
                    <span class="model-badge" id="model-badge">模型加载中...</span>
                </div>

                <div id="chat-messages" class="ai-chat-messages">
                    <div class="ai-chat-empty">
                        <div class="icon">🤖</div>
                        <div class="title">AI 智能助手</div>
                        <div class="subtitle">
                            上传文档到知识库后，我可以基于文档内容回答你的问题。<br>
                            已上传的文档会自动解析为知识库。
                        </div>
                    </div>
                </div>

                <div class="ai-chat-input-area">
                    <div class="ai-chat-input-row">
                        <label class="ai-chat-upload-btn" id="upload-btn">
                            📎 上传文档
                            <input type="file" id="file-input" accept=".pdf,.docx,.doc,.txt" multiple onchange="uploadFiles(this.files)">
                        </label>
                        <input type="text" id="chat-input"
                               placeholder="输入消息，按 Enter 发送..."
                               onkeydown="handleKeyPress(event)"
                               autofocus>
                        <button id="send-btn" onclick="sendMessage()">发送</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        {self._get_chat_script()}
    </script>
</body>
</html>'''

    def _get_chat_styles(self):
        return '''
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f6fa; }

.ai-chat-page {
    display: flex;
    height: 100vh;
    background: #f5f6fa;
}

/* Sidebar */
.ai-chat-sidebar {
    width: 280px;
    background: white;
    border-right: 1px solid #e0e0e0;
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
}
.ai-chat-sidebar-header {
    padding: 16px;
    border-bottom: 1px solid #e0e0e0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.ai-chat-sidebar-header h3 { margin: 0; font-size: 16px; color: #333; }
.new-conv-btn {
    padding: 6px 12px;
    background: #4a6cf7;
    color: white;
    border: none;
    border-radius: 16px;
    font-size: 13px;
    cursor: pointer;
}
.new-conv-btn:hover { background: #3a5ce5; }
.ai-chat-conv-list { flex: 1; overflow-y: auto; padding: 8px; }
.ai-chat-loading-text { padding: 16px; color: #999; text-align: center; }
.ai-chat-conv-item {
    padding: 12px;
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 4px;
    transition: background 0.2s;
}
.ai-chat-conv-item:hover { background: #f0f2ff; }
.ai-chat-conv-item.active { background: #e8eaff; border-left: 3px solid #4a6cf7; }
.ai-chat-conv-item .conv-name { font-size: 14px; color: #333; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ai-chat-conv-item .conv-preview { font-size: 12px; color: #888; margin-top: 4px; }

/* Main */
.ai-chat-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.ai-chat-header {
    padding: 16px 24px;
    background: white;
    border-bottom: 1px solid #e0e0e0;
    display: flex;
    align-items: center;
    gap: 12px;
}
.ai-chat-header h2 { margin: 0; font-size: 18px; color: #333; flex: 1; }
.model-badge {
    font-size: 12px;
    color: #4a6cf7;
    background: #e8eaff;
    padding: 4px 10px;
    border-radius: 12px;
}

/* Messages */
.ai-chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
}
.ai-chat-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #999;
}
.ai-chat-empty .icon { font-size: 64px; margin-bottom: 16px; }
.ai-chat-empty .title { font-size: 20px; color: #333; margin-bottom: 8px; }
.ai-chat-empty .subtitle { font-size: 14px; color: #888; max-width: 400px; text-align: center; }

.ai-chat-message { max-width: 75%; padding: 12px 16px; border-radius: 12px; line-height: 1.5; font-size: 14px; word-wrap: break-word; }
.ai-chat-message.user { align-self: flex-end; background: #4a6cf7; color: white; border-bottom-right-radius: 4px; }
.ai-chat-message.assistant { align-self: flex-start; background: white; color: #333; border: 1px solid #e0e0e0; border-bottom-left-radius: 4px; }
.ai-chat-message .message-meta { font-size: 11px; color: #999; margin-top: 6px; display: flex; gap: 8px; }
.ai-chat-message.user .message-meta { color: rgba(255,255,255,0.7); }

.ai-chat-loading {
    align-self: flex-start;
    display: flex;
    align-items: center;
    padding: 12px 16px;
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    border-bottom-left-radius: 4px;
    color: #888;
    font-size: 14px;
    gap: 12px;
}
.spinner { width: 20px; height: 20px; border: 2px solid #e0e0e0; border-top: 2px solid #4a6cf7; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Input */
.ai-chat-input-area { padding: 16px 24px; background: white; border-top: 1px solid #e0e0e0; }
.ai-chat-input-row { display: flex; gap: 12px; align-items: center; }
.ai-chat-input-row input {
    flex: 1;
    padding: 12px 16px;
    border: 1px solid #e0e0e0;
    border-radius: 24px;
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s;
}
.ai-chat-input-row input:focus { border-color: #4a6cf7; }
.ai-chat-input-row input:disabled { background: #f5f5f5; }
.ai-chat-input-row button {
    padding: 10px 24px;
    background: #4a6cf7;
    color: white;
    border: none;
    border-radius: 24px;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.2s;
}
.ai-chat-input-row button:hover:not(:disabled) { background: #3a5ce5; }
.ai-chat-input-row button:disabled { background: #ccc; cursor: not-allowed; }

.ai-chat-upload-btn {
    padding: 10px 16px;
    background: #f0f2ff;
    color: #4a6cf7;
    border: 1px solid #d0d5ff;
    border-radius: 24px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
}
.ai-chat-upload-btn:hover { background: #e0e4ff; }
.ai-chat-upload-btn input[type="file"] { display: none; }

.ai-chat-error { background: #fff0f0 !important; color: #d32f2f !important; border: 1px solid #ffcdd2 !important; }

/* Toast */
.toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    padding: 12px 24px;
    border-radius: 8px;
    color: white;
    font-size: 14px;
    z-index: 9999;
    animation: fadeIn 0.3s;
}
.toast.success { background: #4caf50; }
.toast.error { background: #f44336; }
.toast.info { background: #2196f3; }
@keyframes fadeIn { from { opacity: 0; transform: translateX(-50%) translateY(20px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }

/* Upload progress */
.upload-progress {
    padding: 8px 16px;
    background: #e8f5e9;
    border-radius: 8px;
    font-size: 13px;
    color: #2e7d32;
    margin-bottom: 8px;
}
'''

    def _get_chat_script(self):
        return '''
const API_CHAT = '/api/ai/chat';
const API_DOCS = '/api/ai/documents';
const API_CONV = '/api/ai/conversations';

let state = {
    messages: [],
    loading: false,
    conversationId: null,
    conversations: [],
};

// ======== Initialization ========
document.addEventListener('DOMContentLoaded', async () => {
    await loadConversations();
    document.getElementById('chat-input').focus();
});

// ======== Conversations ========
async function loadConversations() {
    try {
        const resp = await fetch(API_CONV + '?state=active', {
            headers: { 'X-CSRF-Token': getCSRF() }
        });
        const data = await resp.json();
        if (data.result) {
            state.conversations = data.result.conversations || [];
            renderConversationList();
            if (state.conversations.length > 0) {
                selectConversation(state.conversations[0].id);
            }
        }
    } catch(e) {
        console.error('Failed to load conversations', e);
    }
}

function renderConversationList() {
    const list = document.getElementById('conversation-list');
    if (state.conversations.length === 0) {
        list.innerHTML = '<div class="ai-chat-loading-text">暂无对话，开始新对话吧</div>';
        return;
    }
    list.innerHTML = state.conversations.map(c => `
        <div class="ai-chat-conv-item ${c.id === state.conversationId ? 'active' : ''}"
             onclick="selectConversation(${c.id})">
            <div class="conv-name">${escHtml(c.name)}</div>
            <div class="conv-preview">${escHtml((c.last_message || '').substring(0, 60))}</div>
        </div>
    `).join('');
}

async function selectConversation(id) {
    state.conversationId = id;
    renderConversationList();

    try {
        const resp = await fetch(API_CONV + '/' + id, {
            headers: { 'X-CSRF-Token': getCSRF() }
        });
        const data = await resp.json();
        if (data.result) {
            const conv = data.result.conversation;
            const msgs = data.result.messages || [];
            document.getElementById('chat-title').textContent = conv.name || 'AI 智能助手';
            document.getElementById('model-badge').textContent = conv.model || '模型加载中';
            renderMessages(msgs);
        }
    } catch(e) {
        console.error('Failed to load conversation', e);
    }
}

async function newConversation() {
    state.conversationId = null;
    state.messages = [];
    renderMessages([]);
    document.getElementById('chat-title').textContent = '新对话';
    document.getElementById('chat-input').value = '';
    document.getElementById('chat-input').focus();
}

// ======== Messages ========
function renderMessages(msgs) {
    const container = document.getElementById('chat-messages');
    if (!msgs || msgs.length === 0) {
        container.innerHTML = `
            <div class="ai-chat-empty">
                <div class="icon">🤖</div>
                <div class="title">AI 智能助手</div>
                <div class="subtitle">
                    上传文档到知识库后，我可以基于文档内容回答你的问题。<br>
                    已上传的文档会自动解析为知识库。
                </div>
            </div>
        `;
        return;
    }
    container.innerHTML = msgs.map(m => `
        <div class="ai-chat-message ${m.role}">
            <div class="message-content">${escHtml(m.content)}</div>
            <div class="message-meta">
                ${m.model ? '<span>' + escHtml(m.model) + '</span>' : ''}
                ${m.tokens_used ? '<span>' + m.tokens_used + ' tokens</span>' : ''}
                ${m.create_date ? '<span>' + formatTime(m.create_date) + '</span>' : ''}
            </div>
        </div>
    `).join('');
    setTimeout(() => container.scrollTop = container.scrollHeight, 50);
}

function addMessage(role, content, extra = {}) {
    const container = document.getElementById('chat-messages');
    const empty = container.querySelector('.ai-chat-empty');
    if (empty) container.innerHTML = '';

    const div = document.createElement('div');
    div.className = 'ai-chat-message ' + role;
    div.innerHTML = `
        <div class="message-content">${escHtml(content)}</div>
        <div class="message-meta">
            ${extra.model ? '<span>' + escHtml(extra.model) + '</span>' : ''}
            ${extra.tokens ? '<span>' + extra.tokens + ' tokens</span>' : ''}
        </div>
    `;
    container.appendChild(div);
    setTimeout(() => container.scrollTop = container.scrollHeight, 50);
}

function showLoading() {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = 'ai-chat-loading';
    div.id = 'chat-loading';
    div.innerHTML = '<div class="spinner"></div><span>AI 思考中...</span>';
    container.appendChild(div);
    setTimeout(() => container.scrollTop = container.scrollHeight, 50);
}

function hideLoading() {
    const el = document.getElementById('chat-loading');
    if (el) el.remove();
}

// ======== Send Message ========
async function sendMessage() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const message = input.value.trim();
    if (!message || state.loading) return;

    state.loading = true;
    input.disabled = true;
    sendBtn.disabled = true;
    input.value = '';

    addMessage('user', message);

    showLoading();

    try {
        const resp = await fetch(API_CHAT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRF(),
            },
            body: JSON.stringify({
                message: message,
                conversation_id: state.conversationId,
                use_rag: true,
                use_crm_context: false,
            }),
        });

        const data = await resp.json();

        hideLoading();

        if (data.error) {
            throw new Error(data.error.message || 'Unknown error');
        }

        const result = data.result;
        state.conversationId = result.conversation_id;

        addMessage('assistant', result.ai_message.content || '(empty response)', {
            model: result.ai_message.model,
            tokens: result.ai_message.tokens_used,
        });

        // Refresh conversation list
        await loadConversations();

    } catch (err) {
        hideLoading();
        addMessage('assistant', '⚠️ ' + (err.message || '获取AI响应失败，请检查配置'), { isError: true });
    } finally {
        state.loading = false;
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
    }
}

function handleKeyPress(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

// ======== File Upload ========
async function uploadFiles(files) {
    if (!files || files.length === 0) return;

    showToast('正在上传 ' + files.length + ' 个文档到知识库...', 'info');

    let success = 0;
    let failed = 0;

    for (const file of files) {
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('name', file.name.replace(/\.[^/.]+$/,  ''));

            const resp = await fetch(API_DOCS + '/upload', {
                method: 'POST',
                headers: {
                    'X-CSRF-Token': getCSRF(),
                },
                body: formData,
            });

            const data = await resp.json();

            if (data.error) {
                failed++;
                console.error('Upload failed:', data.error);
            } else {
                success++;
                // Auto-trigger processing via the document create hook
                console.log('Uploaded:', data.result);
            }
        } catch (e) {
            failed++;
            console.error('Upload error:', e);
        }
    }

    if (success > 0) {
        showToast('✅ ' + success + ' 个文档已上传并加入知识库。现在可以提问了！', 'success');
    }
    if (failed > 0) {
        showToast('❌ ' + failed + ' 个文档上传失败', 'error');
    }

    // Clear file input
    document.getElementById('file-input').value = '';
}

// ======== Utilities ========
function getCSRF() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatTime(iso) {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function showToast(message, type = 'info') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}
'''
