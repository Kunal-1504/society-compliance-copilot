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
  { id: 1, date: new Date(new Date().getFullYear(), new Date().getMonth(), 15).toISOString(), title: 'AGM Notice Deadline', type: 'deadline', status: 'pending' },
  { id: 2, date: new Date(new Date().getFullYear(), new Date().getMonth(), 28).toISOString(), title: 'Audit Report Submission', type: 'compliance', status: 'pending' },
  { id: 3, date: new Date(new Date().getFullYear(), new Date().getMonth() - 1, 10).toISOString(), title: 'Fire Safety Drill', type: 'event', status: 'completed' },
  { id: 4, date: new Date(new Date().getFullYear(), new Date().getMonth(), 5).toISOString(), title: 'Monthly MC Meeting', type: 'meeting', status: 'completed' },
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
