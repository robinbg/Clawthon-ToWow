import type { User, Project, Transaction, Investment, DashboardData } from '@/app/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('clawthon_token', token);
    }
  }

  getToken(): string | null {
    if (this.token) return this.token;
    if (typeof window !== 'undefined') {
      return localStorage.getItem('clawthon_token');
    }
    return null;
  }

  clearToken() {
    this.token = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('clawthon_token');
    }
  }

  async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: '请求失败' }));
      throw new Error(error.message || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // 认证相关
  async oauthCallback(code: string): Promise<{ access_token: string; user: User }> {
    const data = await this.request<{ access_token: string; user: User }>('/auth/callback', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async getMe(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  async updateSettings(settings: Partial<User['settings']>): Promise<void> {
    return this.request<void>('/auth/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }

  // 项目相关
  async getProjects(): Promise<Project[]> {
    return this.request<Project[]>('/projects');
  }

  async getMyProjects(): Promise<Project[]> {
    return this.request<Project[]>('/projects/my');
  }

  async getProject(id: number): Promise<Project> {
    return this.request<Project>(`/projects/${id}`);
  }

  async createProject(data: Partial<Project>): Promise<Project> {
    return this.request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getMarketplace(productType?: string): Promise<Project[]> {
    const params = productType ? `?product_type=${productType}` : '';
    return this.request<Project[]>(`/projects/marketplace${params}`);
  }

  // 交易相关
  async getDashboard(): Promise<DashboardData> {
    return this.request<DashboardData>('/transactions/dashboard');
  }

  async getTransactions(): Promise<Transaction[]> {
    return this.request<Transaction[]>('/transactions/my');
  }

  async getPendingTransactions(): Promise<Transaction[]> {
    return this.request<Transaction[]>('/transactions/pending');
  }

  async createSpendingRequest(data: {
    target_project_id: number;
    amount: number;
    reason: string;
    expected_return: string;
    risk?: string;
  }): Promise<{ id: number; status: string; message: string }> {
    return this.request('/transactions/spend', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async approveTransaction(
    transactionId: number,
    approved: boolean,
    reason?: string
  ): Promise<void> {
    return this.request<void>(`/transactions/${transactionId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved, reason }),
    });
  }

  // 投资相关
  async getInvestments(): Promise<Investment[]> {
    return this.request<Investment[]>('/transactions/investments/my');
  }

  async createInvestment(data: {
    project_id: number;
    amount: number;
    investment_reason?: string;
    expected_roi?: number;
    risk_level?: string;
  }): Promise<Investment> {
    return this.request<Investment>('/transactions/invest', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
}

export const api = new ApiClient();
