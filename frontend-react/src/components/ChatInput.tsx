import React, { useState, useRef, useEffect } from 'react';
import { Send, Mic, StopCircle } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (msg: string) => void;
  disabled?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage, disabled }) => {
  const [text, setText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  // Web Speech API
  const [recognition, setRecognition] = useState<any>(null);

  useEffect(() => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      const rec = new SpeechRecognition();
      rec.continuous = true;
      rec.interimResults = true;
      // We don't set a hardcoded lang here because the user might speak Marathi or English.
      // Ideally, it automatically detects, or we might need a UI toggle. We'll set 'mr-IN' as default for Marathi support, 
      // but it can often pick up English too.
      rec.lang = 'mr-IN'; 

      rec.onresult = (event: any) => {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalTranscript += event.results[i][0].transcript;
          } else {
            interimTranscript += event.results[i][0].transcript;
          }
        }
        
        if (finalTranscript) {
          setText(prev => prev + (prev ? ' ' : '') + finalTranscript);
        }
      };

      rec.onerror = (event: any) => {
        console.error('Speech recognition error', event.error);
        setIsRecording(false);
      };

      rec.onend = () => {
        setIsRecording(false);
      };

      setRecognition(rec);
    }
  }, []);

  const toggleRecording = () => {
    if (!recognition) {
      alert("Speech recognition is not supported in this browser.");
      return;
    }

    if (isRecording) {
      recognition.stop();
      setIsRecording(false);
    } else {
      recognition.start();
      setIsRecording(true);
    }
  };

  const handleSend = () => {
    if (text.trim() && !disabled) {
      if (isRecording) {
        recognition?.stop();
        setIsRecording(false);
      }
      onSendMessage(text.trim());
      setText('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  };

  return (
    <div className="relative glass-panel rounded-2xl p-2 mx-auto w-full max-w-4xl shadow-lg border-brand-100 dark:border-brand-900/30">
      <div className="flex items-end gap-2">
        <button
          onClick={toggleRecording}
          type="button"
          className={`shrink-0 p-3 rounded-xl transition-colors ${
            isRecording 
              ? 'bg-red-100 text-red-600 dark:bg-red-900/50 dark:text-red-400 animate-pulse' 
              : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
          }`}
          title={isRecording ? 'Stop recording' : 'Use voice input (Marathi/English)'}
        >
          {isRecording ? <StopCircle size={24} /> : <Mic size={24} />}
        </button>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={isRecording ? "Listening..." : "Ask about society rules (e.g. AGM kadhi ghyavi?)"}
          className="flex-1 max-h-[150px] min-h-[50px] bg-transparent border-0 resize-none py-3 px-2 focus:ring-0 text-slate-800 dark:text-slate-100 placeholder-slate-400 custom-scrollbar outline-none"
          rows={1}
          disabled={disabled}
        />

        <button
          onClick={handleSend}
          disabled={!text.trim() || disabled}
          className={`shrink-0 p-3 rounded-xl transition-all ${
            text.trim() && !disabled
              ? 'bg-brand-600 text-white hover:bg-brand-700 shadow-md'
              : 'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500'
          }`}
        >
          <Send size={20} className={text.trim() && !disabled ? 'translate-x-0.5 -translate-y-0.5' : ''} />
        </button>
      </div>
    </div>
  );
};
