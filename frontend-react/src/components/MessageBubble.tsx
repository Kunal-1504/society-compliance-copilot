import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Copy, ThumbsUp, ThumbsDown, RotateCcw, Terminal } from 'lucide-react';
import { motion } from 'framer-motion';
import type { Message } from '../context/ChatContext';

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message, isStreaming }) => {
  const isUser = message.role === 'user';
  const [showDebug, setShowDebug] = useState(false);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(message.content);
  };

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex gap-4 w-full ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {/* Avatar */}
      <div className={`
        shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold
        ${isUser ? 'bg-brand-500 text-white' : 'bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900'}
      `}>
        {isUser ? 'U' : 'AI'}
      </div>

      {/* Bubble Content */}
      <div className={`flex flex-col gap-1 max-w-[85%] md:max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div className={`
          px-5 py-3.5 rounded-2xl shadow-sm
          ${isUser 
            ? 'bg-brand-600 text-white rounded-tr-sm' 
            : 'bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded-tl-sm border border-slate-100 dark:border-slate-700'
          }
          ${message.error ? 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800' : ''}
        `}>
          {message.language && !isUser && (
            <div className="text-[10px] font-semibold uppercase tracking-wider text-brand-500 dark:text-brand-400 mb-2">
              {message.language}
            </div>
          )}

          {isStreaming ? (
            <div className="flex gap-1 py-1">
              <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          ) : (
            <div className="prose dark:prose-invert max-w-none text-[15px] leading-relaxed">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Action Row */}
        {!isUser && !isStreaming && !message.error && (
          <div className="flex flex-col gap-2 w-full mt-1">
            <div className="flex items-center gap-2 text-slate-400">
              <button onClick={copyToClipboard} className="p-1 hover:text-slate-600 dark:hover:text-slate-200 transition-colors" title="Copy">
                <Copy size={14} />
              </button>
              <button className="p-1 hover:text-slate-600 dark:hover:text-slate-200 transition-colors" title="Helpful">
                <ThumbsUp size={14} />
              </button>
              <button className="p-1 hover:text-slate-600 dark:hover:text-slate-200 transition-colors" title="Not helpful">
                <ThumbsDown size={14} />
              </button>
              <button className="p-1 hover:text-slate-600 dark:hover:text-slate-200 transition-colors" title="Regenerate">
                <RotateCcw size={14} />
              </button>
              
              {message.debug && (
                <button 
                  onClick={() => setShowDebug(!showDebug)} 
                  className={`p-1 hover:text-slate-600 dark:hover:text-slate-200 transition-colors ${showDebug ? 'text-brand-500 dark:text-brand-400' : ''}`} 
                  title="Developer Debug Info"
                >
                  <Terminal size={14} />
                </button>
              )}
              
              {message.sources && message.sources.length > 0 && !message.content.toLowerCase().includes('i can only help you with society compliance') && (
                <div className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400 select-none ml-2">
                  <div className="flex items-center -space-x-1.5 hover:space-x-1 transition-all duration-200">
                    {message.sources.map((source, idx) => {
                      let d = source.domain || '';
                      if (!d && (source.url || source.source_page)) {
                        try { d = new URL(source.url || source.source_page || '').hostname; } catch {}
                      }
                      const url = source.url || source.source_page;
                      if (!url) return null;
                      
                      return (
                        <a 
                          key={idx}
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="w-[18px] h-[18px] rounded-full bg-white ring-[1.5px] ring-white dark:ring-slate-900 overflow-hidden flex items-center justify-center relative shadow-sm hover:scale-125 transition-all"
                          style={{ zIndex: 10 - idx }}
                          title={d || 'Document'}
                        >
                          <img 
                            src={`https://www.google.com/s2/favicons?domain=${d}&sz=16`} 
                            alt="favicon"
                            className="w-[12px] h-[12px] object-contain"
                            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                          />
                        </a>
                      );
                    })}
                  </div>
                  <span className="select-none pointer-events-none">Sources</span>
                </div>
              )}
            </div>

            {/* Developer Debug Panel */}
            {showDebug && message.debug && (
              <div className="w-full mt-2 p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-900 text-slate-100 font-mono text-xs overflow-x-auto space-y-3 shadow-md">
                <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider border-b border-slate-800 pb-1.5 flex justify-between items-center">
                  <span>Developer Debug Panel</span>
                  <span className="text-brand-400 font-semibold">{message.debug.language || 'Unknown Lang'}</span>
                </div>
                
                {message.debug.marathi_query && (
                  <div>
                    <span className="text-brand-400 font-bold">Normalized Query (Devanagari):</span>
                    <p className="mt-1 text-slate-300">{message.debug.marathi_query}</p>
                  </div>
                )}
                
                {message.debug.acronyms && message.debug.acronyms.length > 0 && (
                  <div>
                    <span className="text-brand-400 font-bold">Acronyms Detected:</span>
                    <ul className="list-disc list-inside mt-1 text-slate-300">
                      {message.debug.acronyms.map((acr: string, idx: number) => (
                        <li key={idx}>{acr}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                <div>
                  <span className="text-brand-400 font-bold">Embedding Model:</span>
                  <p className="mt-1 text-slate-300">BAAI/bge-m3 (Dense 1024-dim, Cosine)</p>
                </div>
                
                {message.debug.chunks && message.debug.chunks.length > 0 && (
                  <div>
                    <span className="text-brand-400 font-bold">Top Retrieved Chunks (RRF + FTS + Vector):</span>
                    <div className="mt-2 space-y-2">
                      {message.debug.chunks.map((chunk: any, idx: number) => (
                        <div key={idx} className="p-2.5 rounded bg-slate-950 border border-slate-800 space-y-1">
                          <div className="flex justify-between text-[10px] text-slate-400">
                            <span className="font-semibold text-slate-300 truncate max-w-[60%]">{chunk.filename}</span>
                            <span>Page {chunk.page} | Category: {chunk.category}</span>
                          </div>
                          <div className="flex gap-4 text-[10px] text-brand-400">
                            <span>Vector Cos: {chunk.similarity}</span>
                            <span>RRF Score: {chunk.rrf_score}</span>
                            <span>FTS Rank: {chunk.fts_score}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {message.debug.final_prompt && (
                  <div className="space-y-1">
                    <span className="text-brand-400 font-bold">Final LLM Prompt:</span>
                    <pre className="mt-1 p-2 bg-slate-950 border border-slate-800 rounded whitespace-pre-wrap max-h-48 overflow-y-auto text-[11px] text-slate-300 custom-scrollbar">
                      {message.debug.final_prompt}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
};
