/** @odoo-module **/

/**
 * AI Chat Widget
 * Provides an interactive chat interface for Odoo.
 * Communicates with the /api/ai/chat backend endpoint.
 */

import { registry } from '@web/core/registry';
import { Component, useState, onMounted, useRef } from '@odoo/owl';
import { useService } from '@web/core/utils/hooks';

export class AiChatWidget extends Component {
    static template = 'ai_core.AiChatWidget';

    setup() {
        this.rpc = useService('rpc');
        this.state = useState({
            messages: [],
            inputText: '',
            loading: false,
            conversationId: null,
            error: null,
        });
        this.messagesContainer = useRef('messagesContainer');
        this.inputRef = useRef('chatInput');

        onMounted(() => {
            this.loadConversation();
        });
    }

    async loadConversation() {
        try {
            const result = await this.rpc('/api/ai/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: 'Hello',
                    use_rag: true,
                    use_crm_context: true,
                }),
                headers: { 'Content-Type': 'application/json' },
            });
            // Handle response
        } catch (err) {
            console.error('Failed to load conversation:', err);
        }
    }

    async sendMessage() {
        const message = this.state.inputText.trim();
        if (!message || this.state.loading) return;

        this.state.inputText = '';
        this.state.loading = true;
        this.state.error = null;

        // Add user message
        this.state.messages.push({
            role: 'user',
            content: message,
            timestamp: new Date().toISOString(),
        });
        this.scrollToBottom();

        try {
            const response = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken(),
                },
                body: JSON.stringify({
                    message: message,
                    conversation_id: this.state.conversationId,
                }),
            });

            const data = await response.json();

            if (data.error) {
                throw new Error(data.error.message || 'Unknown error');
            }

            const result = data.result;
            this.state.conversationId = result.conversation_id;

            // Add AI response
            this.state.messages.push({
                role: 'assistant',
                content: result.ai_message.content,
                model: result.ai_message.model,
                tokens: result.ai_message.tokens_used,
                ragContext: result.rag_sources || [],
                timestamp: new Date().toISOString(),
            });

        } catch (err) {
            this.state.error = err.message || 'Failed to get AI response';
            this.state.messages.push({
                role: 'assistant',
                content: `Error: ${this.state.error}. Please check your configuration and try again.`,
                isError: true,
                timestamp: new Date().toISOString(),
            });
        } finally {
            this.state.loading = false;
            this.scrollToBottom();
            if (this.inputRef.el) {
                this.inputRef.el.focus();
            }
        }
    }

    scrollToBottom() {
        setTimeout(() => {
            if (this.messagesContainer.el) {
                this.messagesContainer.el.scrollTop = this.messagesContainer.el.scrollHeight;
            }
        }, 50);
    }

    getCsrfToken() {
        const tokenElement = document.querySelector('meta[name="csrf-token"]');
        return tokenElement ? tokenElement.getAttribute('content') : '';
    }

    handleKeyPress(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendMessage();
        }
    }

    formatTimestamp(isoString) {
        const date = new Date(isoString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
}

// Register the widget
registry.category('widgets').add('ai_chat_widget', AiChatWidget);
