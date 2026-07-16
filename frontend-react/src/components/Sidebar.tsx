import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { 
  MessageSquare, 
  Calendar, 
  Plus, 
  Search, 
  Pin,
  Trash2,
  X
} from 'lucide-react';
import { useChat } from '../context/ChatContext';

export const Sidebar: React.FC<{ isMobileOpen: boolean; closeMobile: () => void }> = ({ isMobileOpen, closeMobile }) => {
  const { chats, activeChatId, setActiveChatId, createNewChat, deleteChat, togglePinChat } = useChat();
  const [searchTerm, setSearchTerm] = useState('');

  const chatList = Object.values(chats)
    .filter(c => c.title?.toLowerCase().includes(searchTerm.toLowerCase()) || searchTerm === '')
    .sort((a, b) => {
      if (a.isPinned && !b.isPinned) return -1;
      if (!a.isPinned && b.isPinned) return 1;
      return b.updatedAt - a.updatedAt;
    });

  const navLinks = [
    { to: '/', icon: <MessageSquare size={20} />, label: 'Chat' },
    { to: '/calendar', icon: <Calendar size={20} />, label: 'Calendar' },
  ];

  return (
    <>
      {/* Mobile scrim */}
      {isMobileOpen && (
        <div 
          className="fixed inset-0 bg-slate-900/50 z-40 md:hidden"
          onClick={closeMobile}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed md:static inset-y-0 left-0 z-50 w-72 h-screen
        glass-panel flex flex-col transition-transform duration-300
        ${isMobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
      `}>
        {/* Header */}
        <div className="p-4 flex items-center justify-between border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2 font-semibold text-lg text-brand-600 dark:text-brand-400">
            <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white">
              S
            </span>
            Copilot
          </div>
          <button className="md:hidden btn-icon" onClick={closeMobile}>
            <X size={20} />
          </button>
        </div>

        {/* New Chat Button */}
        <div className="p-4">
          <button 
            onClick={() => { createNewChat(); closeMobile(); }}
            className="w-full btn-primary py-2.5 rounded-lg shadow-none"
          >
            <Plus size={20} />
            New Chat
          </button>
        </div>

        {/* Main Navigation */}
        <nav className="px-3 space-y-1 mb-4">
          {navLinks.map(link => (
            <NavLink
              key={link.to}
              to={link.to}
              onClick={closeMobile}
              className={({ isActive }) => `
                flex items-center gap-3 px-3 py-2 rounded-lg transition-colors
                ${isActive 
                  ? 'bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-400 font-medium' 
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-200'
                }
              `}
            >
              {link.icon}
              {link.label}
            </NavLink>
          ))}
        </nav>

        {/* Chat History Section */}
        <div className="flex-1 overflow-hidden flex flex-col">
          <div className="px-4 pb-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Recent Chats
          </div>
          
          <div className="px-4 pb-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 text-slate-400" size={14} />
              <input 
                type="text" 
                placeholder="Search chats..." 
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 bg-slate-100 dark:bg-slate-800/50 border border-transparent rounded-lg text-sm focus:outline-none focus:border-brand-500 dark:text-slate-200 transition-colors"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto custom-scrollbar px-3 pb-4 space-y-1">
            {chatList.map(chat => (
              <div 
                key={chat.id}
                className={`group relative flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors
                  ${activeChatId === chat.id 
                    ? 'bg-slate-200/50 dark:bg-slate-800 text-slate-900 dark:text-slate-100' 
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-200'
                  }
                `}
                onClick={() => { setActiveChatId(chat.id); closeMobile(); }}
              >
                <div className="flex-1 truncate text-sm">
                  {chat.isPinned && <Pin size={12} className="inline mr-1 text-brand-500" />}
                  {chat.title || 'New Chat'}
                </div>
                
                {/* Actions that appear on hover */}
                <div className="hidden group-hover:flex items-center gap-1 absolute right-2 bg-gradient-to-l from-slate-100 dark:from-slate-800 pl-2">
                  <button 
                    onClick={(e) => { e.stopPropagation(); togglePinChat(chat.id); }}
                    className="p-1 text-slate-400 hover:text-brand-500 transition-colors"
                    title={chat.isPinned ? "Unpin" : "Pin"}
                  >
                    <Pin size={14} />
                  </button>
                  <button 
                    onClick={(e) => { e.stopPropagation(); deleteChat(chat.id); }}
                    className="p-1 text-slate-400 hover:text-red-500 transition-colors"
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
            {chatList.length === 0 && (
              <div className="px-3 py-4 text-sm text-center text-slate-500">
                No chats found
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  );
};
