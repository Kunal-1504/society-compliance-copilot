import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Menu, Moon, Sun, UserCircle } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

export const Layout: React.FC = () => {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="flex h-screen overflow-hidden bg-background-light dark:bg-background-dark">
      <Sidebar isMobileOpen={isMobileOpen} closeMobile={() => setIsMobileOpen(false)} />
      
      <main className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="h-16 px-4 glass flex items-center justify-between md:justify-end shrink-0 z-10">
          <div className="flex items-center md:hidden">
            <button 
              className="btn-icon mr-2"
              onClick={() => setIsMobileOpen(true)}
            >
              <Menu size={24} />
            </button>
            <span className="font-semibold text-brand-600 dark:text-brand-400">Copilot</span>
          </div>

          <div className="flex items-center gap-2">
            <button 
              onClick={toggleTheme}
              className="btn-icon"
              title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
            >
              {theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}
            </button>
            <button className="btn-icon">
              <UserCircle size={24} className="text-slate-500 dark:text-slate-400" />
            </button>
          </div>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-hidden relative">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
