export const API_BASE = "http://localhost:8000";

export interface QueryResponse {
  answer: string;
  sources: Array<{
    title?: string;
    url?: string;
    source_page?: string;
    filename?: string;
    category?: string;
    department?: string;
    domain?: string;
    page?: string | number;
    similarity?: number;
  }>;
  confidence: number;
  language?: string;
  debug?: any;
}

export async function askQuestion(query: string): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, top_k: 8 }),
  });
  if (!response.ok) {
    throw new Error(`API returned ${response.status}`);
  }
  return response.json();
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchDocuments() {
  const res = await fetch(`${API_BASE}/documents`);
  return res.json();
}

// MOCK DATA FOR FEATURES WITHOUT BACKEND YET
export const mockCalendarEvents = [
  // May (Month - 2)
  { id: 101, date: new Date(new Date().getFullYear(), new Date().getMonth() - 2, 12).toISOString(), title: 'Special General Body Meeting', type: 'meeting', status: 'completed' },
  { id: 102, date: new Date(new Date().getFullYear(), new Date().getMonth() - 2, 22).toISOString(), title: 'Quarterly Accounts Audit', type: 'compliance', status: 'completed' },
  
  // June (Month - 1)
  { id: 3, date: new Date(new Date().getFullYear(), new Date().getMonth() - 1, 10).toISOString(), title: 'Fire Safety Drill', type: 'event', status: 'completed' },
  { id: 103, date: new Date(new Date().getFullYear(), new Date().getMonth() - 1, 25).toISOString(), title: 'Maintenance Dues Deadline', type: 'deadline', status: 'completed' },
  
  // July (Month)
  { id: 4, date: new Date(new Date().getFullYear(), new Date().getMonth(), 5).toISOString(), title: 'Monthly MC Meeting', type: 'meeting', status: 'completed' },
  { id: 1, date: new Date(new Date().getFullYear(), new Date().getMonth(), 15).toISOString(), title: 'AGM Notice Deadline', type: 'deadline', status: 'pending' },
  { id: 2, date: new Date(new Date().getFullYear(), new Date().getMonth(), 28).toISOString(), title: 'Audit Report Submission', type: 'compliance', status: 'pending' },
  
  // August (Month + 1)
  { id: 104, date: new Date(new Date().getFullYear(), new Date().getMonth() + 1, 8).toISOString(), title: 'Independence Day Prep', type: 'event', status: 'pending' },
  { id: 105, date: new Date(new Date().getFullYear(), new Date().getMonth() + 1, 20).toISOString(), title: 'Conveyance Deed Review', type: 'compliance', status: 'pending' },
  
  // September (Month + 2)
  { id: 106, date: new Date(new Date().getFullYear(), new Date().getMonth() + 2, 10).toISOString(), title: 'Monthly MC Meeting', type: 'meeting', status: 'pending' },
  { id: 107, date: new Date(new Date().getFullYear(), new Date().getMonth() + 2, 18).toISOString(), title: 'Structural Audit Submission', type: 'compliance', status: 'pending' },
  { id: 108, date: new Date(new Date().getFullYear(), new Date().getMonth() + 2, 30).toISOString(), title: 'Deemed Conveyance Filing', type: 'deadline', status: 'pending' },

  // October (Month + 3)
  { id: 109, date: new Date(new Date().getFullYear(), new Date().getMonth() + 3, 15).toISOString(), title: 'Half Yearly SGM Meeting', type: 'meeting', status: 'pending' }
];

export const mockDashboardStats = {
  totalDocuments: 145,
  totalQueries: 4892,
  dailyUsers: 342,
  ocrSuccessRate: 98.4,
  recentFailed: 2,
  topQueries: [
    "AGM Notice Period",
    "Car parking rules",
    "Transfer fee limit",
    "Leakage repair responsibility"
  ]
};
