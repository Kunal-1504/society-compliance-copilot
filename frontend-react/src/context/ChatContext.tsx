import React, { createContext, useContext, useEffect, useState } from 'react';

export interface Source {
  title?: string;
  filename?: string;
  category?: string;
  source?: string;
  url?: string;
  source_page?: string;
  department?: string;
  snippet?: string;
  snippet_keywords?: string[];
  document_type?: string;
  section?: string;
  page_number?: string | number;
  publication_date?: string;
  updated_date?: string;
  confidence?: number;
  domain?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  error?: boolean;
  language?: string;
  timestamp: number;
}

export interface Chat {
  id: string;
  title: string | null;
  messages: Message[];
  updatedAt: number;
  isPinned?: boolean;
}

interface ChatContextType {
  chats: Record<string, Chat>;
  activeChatId: string | null;
  setActiveChatId: (id: string) => void;
  createNewChat: () => string;
  deleteChat: (id: string) => void;
  updateChatTitle: (id: string, title: string) => void;
  togglePinChat: (id: string) => void;
  addMessage: (chatId: string, message: Omit<Message, 'id' | 'timestamp'>) => void;
  updateMessage: (chatId: string, messageId: string, content: string) => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

const STORAGE_KEY = 'societyCopilot.react.chats.v1';
const ACTIVE_KEY = 'societyCopilot.react.activeId.v1';

export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [chats, setChats] = useState<Record<string, Chat>>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  const [activeChatId, setActiveChatIdState] = useState<string | null>(() => {
    return localStorage.getItem(ACTIVE_KEY) || null;
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
  }, [chats]);

  const setActiveChatId = (id: string) => {
    setActiveChatIdState(id);
    localStorage.setItem(ACTIVE_KEY, id);
  };

  const createNewChat = () => {
    const id = `chat_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    const newChat: Chat = {
      id,
      title: null,
      messages: [],
      updatedAt: Date.now()
    };
    setChats(prev => ({ ...prev, [id]: newChat }));
    setActiveChatId(id);
    return id;
  };

  // Ensure there's always an active chat
  useEffect(() => {
    if (!activeChatId || !chats[activeChatId]) {
      const ids = Object.keys(chats);
      if (ids.length > 0) {
        setActiveChatId(ids[0]);
      } else {
        createNewChat();
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const deleteChat = (id: string) => {
    setChats(prev => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    if (activeChatId === id) {
      const remaining = Object.keys(chats).filter(k => k !== id);
      if (remaining.length > 0) {
        setActiveChatId(remaining[0]);
      } else {
        createNewChat();
      }
    }
  };

  const updateChatTitle = (id: string, title: string) => {
    setChats(prev => ({
      ...prev,
      [id]: { ...prev[id], title, updatedAt: Date.now() }
    }));
  };

  const togglePinChat = (id: string) => {
    setChats(prev => ({
      ...prev,
      [id]: { ...prev[id], isPinned: !prev[id].isPinned, updatedAt: Date.now() }
    }));
  };

  const addMessage = (chatId: string, msg: Omit<Message, 'id' | 'timestamp'>) => {
    const id = `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    const message: Message = { ...msg, id, timestamp: Date.now() };
    
    setChats(prev => {
      const chat = prev[chatId];
      if (!chat) return prev;
      
      let title = chat.title;
      // Auto-generate title from first user message
      if (!title && msg.role === 'user') {
        title = msg.content.substring(0, 40) + (msg.content.length > 40 ? '...' : '');
      }

      return {
        ...prev,
        [chatId]: {
          ...chat,
          title,
          messages: [...chat.messages, message],
          updatedAt: Date.now()
        }
      };
    });
  };

  const updateMessage = (chatId: string, messageId: string, content: string) => {
    setChats(prev => {
      const chat = prev[chatId];
      if (!chat) return prev;
      
      return {
        ...prev,
        [chatId]: {
          ...chat,
          messages: chat.messages.map(m => m.id === messageId ? { ...m, content } : m),
          updatedAt: Date.now()
        }
      };
    });
  }

  return (
    <ChatContext.Provider value={{
      chats,
      activeChatId,
      setActiveChatId,
      createNewChat,
      deleteChat,
      updateChatTitle,
      togglePinChat,
      addMessage,
      updateMessage
    }}>
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) throw new Error('useChat must be used within ChatProvider');
  return context;
};
