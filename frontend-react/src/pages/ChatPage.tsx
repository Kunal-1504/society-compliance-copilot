import React, { useEffect, useRef, useState } from 'react';
import { useChat } from '../context/ChatContext';
import { MessageBubble } from '../components/MessageBubble';
import { ChatInput } from '../components/ChatInput';
import { askQuestion } from '../lib/api';
import { Download, Share2 } from 'lucide-react';
// We use a dynamic import or require for html2pdf if needed, but since we npm installed it:
import html2pdf from 'html2pdf.js';

export const ChatPage: React.FC = () => {
  const { chats, activeChatId, addMessage } = useChat();
  const [isStreaming, setIsStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  
  const activeChat = activeChatId ? chats[activeChatId] : null;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activeChat?.messages, isStreaming]);

  // Removed unused handleSendMessage

  // Improved handleSendMessage
  const handleSend = async (content: string) => {
    if (!activeChatId) return;
    addMessage(activeChatId, { role: 'user', content });
    setIsStreaming(true);

    try {
      const response = await askQuestion(content);
      addMessage(activeChatId, {
        role: 'assistant',
        content: response.answer,
        sources: response.sources,
        language: response.language || detectLang(content),
        debug: response.debug
      });
    } catch (error) {
      addMessage(activeChatId, {
        role: 'assistant',
        content: 'Failed to reach the server. Please try again.',
        error: true
      });
    } finally {
      setIsStreaming(false);
    }
  };

  const detectLang = (text: string) => {
    if (/[\u0900-\u097F]/.test(text)) return 'मराठी';
    return 'English';
  };

  const exportChat = () => {
    const element = document.getElementById('chat-export-container');
    if (element) {
      const opt = {
        margin:       10,
        filename:     `Society_Copilot_Chat_${new Date().toISOString().split('T')[0]}.pdf`,
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  { scale: 2 },
        jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' }
      };
      (html2pdf() as any).set(opt).from(element).save();
    }
  };

  const handleShare = async () => {
    if (!activeChat) return;
    
    const chatText = activeChat.messages.map(m => `${m.role === 'user' ? 'You' : 'Copilot'}:\n${m.content}`).join('\n\n');
    
    try {
      if (navigator.share) {
        await navigator.share({
          title: activeChat.title || 'Society Copilot Chat',
          text: chatText
        });
      } else {
        await navigator.clipboard.writeText(chatText);
        alert('Chat content copied to clipboard!');
      }
    } catch (err) {
      console.error('Error sharing:', err);
    }
  };

  if (!activeChat) return <div className="flex-1 flex items-center justify-center">No active chat</div>;

  return (
    <div className="flex flex-col h-full bg-slate-50/50 dark:bg-background-dark relative">
      {/* Header Actions */}
      <div className="absolute top-4 right-4 z-10 flex gap-2">
        <button onClick={exportChat} className="btn-secondary px-3 py-2 text-sm" title="Export as PDF">
          <Download size={16} /> <span className="hidden sm:inline">Export</span>
        </button>
        <button onClick={handleShare} className="btn-secondary px-3 py-2 text-sm" title="Share Chat">
          <Share2 size={16} /> <span className="hidden sm:inline">Share</span>
        </button>
      </div>

      <div 
        ref={scrollRef}
        id="chat-export-container"
        className="flex-1 overflow-y-auto custom-scrollbar px-4 sm:px-6 md:px-8 py-8"
      >
        <div className="max-w-4xl mx-auto space-y-6 pb-32">
          {activeChat.messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center mt-20 opacity-0 animate-fade-in">
              <div className="w-16 h-16 bg-brand-100 dark:bg-brand-900/30 rounded-2xl flex items-center justify-center text-brand-500 mb-6 shadow-sm">
                <span className="text-3xl font-bold">S</span>
              </div>
              <h2 className="text-2xl font-semibold text-slate-800 dark:text-slate-100 mb-2">
                How can I help you today?
              </h2>
              <p className="text-slate-500 dark:text-slate-400 max-w-md">
                Ask me anything about Maharashtra Cooperative Housing Society laws, bye-laws, or compliance deadlines.
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-8 w-full max-w-2xl text-left">
                {[
                  "What is the procedure for an AGM?",
                  "Society cha audit kadhi karaycha?",
                  "Can the managing committee charge extra parking fees?",
                  "Deemed conveyance process mhanje kay?"
                ].map(q => (
                  <button 
                    key={q}
                    onClick={() => handleSend(q)}
                    className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800 hover:border-brand-300 dark:hover:border-brand-700 hover:shadow-md transition-all text-sm text-slate-600 dark:text-slate-300"
                  >
                    "{q}"
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {activeChat.messages.map((msg, i) => (
                <MessageBubble key={msg.id || i} message={msg} />
              ))}
              {isStreaming && (
                <MessageBubble 
                  message={{ id: 'streaming', role: 'assistant', content: '', timestamp: Date.now() }} 
                  isStreaming={true} 
                />
              )}
            </>
          )}
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white dark:from-background-dark dark:via-background-dark to-transparent pt-10 pb-6 px-4">
        <ChatInput onSendMessage={handleSend} disabled={isStreaming} />
      </div>
    </div>
  );
};
