import React, { useEffect, useState } from 'react';
import { Search, FileText, Download, ExternalLink, Filter } from 'lucide-react';
import { fetchDocuments } from '../lib/api';

interface Document {
  category: string;
  filename: string;
  path: string;
  url?: string;
}

export const DocumentsPage: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('All');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDocuments().then(data => {
      setDocuments(data.documents || []);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, []);

  const categories = ['All', ...Array.from(new Set(documents.map(d => d.category)))];

  const filteredDocs = documents.filter(doc => {
    const matchesSearch = doc.filename.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = categoryFilter === 'All' || doc.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="flex flex-col h-full overflow-y-auto custom-scrollbar p-4 sm:p-8 bg-slate-50/50 dark:bg-background-dark">
      <div className="max-w-6xl mx-auto w-full">
        <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Document Library</h1>
            <p className="text-slate-500 dark:text-slate-400 mt-1">Browse, search, and download official compliance documents.</p>
          </div>
          
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 text-slate-400" size={18} />
              <input 
                type="text" 
                placeholder="Search documents..." 
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="pl-10 pr-4 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:border-brand-500 dark:text-slate-200 w-full sm:w-64"
              />
            </div>
            
            <div className="relative">
              <Filter className="absolute left-3 top-2.5 text-slate-400" size={18} />
              <select
                value={categoryFilter}
                onChange={e => setCategoryFilter(e.target.value)}
                className="pl-10 pr-8 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:border-brand-500 dark:text-slate-200 appearance-none w-full sm:w-48"
              >
                {categories.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center p-12">
            <div className="w-8 h-8 border-4 border-brand-200 border-t-brand-600 rounded-full animate-spin"></div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredDocs.map((doc, i) => (
              <div key={i} className="glass-panel p-5 rounded-2xl flex flex-col gap-3 group hover:border-brand-300 dark:hover:border-brand-700 transition-colors">
                <div className="flex items-start gap-3">
                  <div className="p-3 bg-brand-50 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400 rounded-xl shrink-0">
                    <FileText size={24} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-slate-800 dark:text-slate-200 truncate" title={doc.filename}>
                      {doc.filename}
                    </h3>
                    <span className="inline-block px-2 py-1 mt-1 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-[10px] uppercase tracking-wider rounded-md font-medium">
                      {doc.category}
                    </span>
                  </div>
                </div>
                
                <div className="flex items-center gap-2 mt-auto pt-3 border-t border-slate-100 dark:border-slate-800">
                  <button className="flex-1 btn-secondary py-2 text-sm">
                    <Download size={14} /> Download
                  </button>
                  {doc.url && (
                    <a href={doc.url} target="_blank" rel="noopener noreferrer" className="p-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors">
                      <ExternalLink size={16} />
                    </a>
                  )}
                </div>
              </div>
            ))}
            {filteredDocs.length === 0 && (
              <div className="col-span-full py-12 text-center text-slate-500">
                No documents found matching your criteria.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
