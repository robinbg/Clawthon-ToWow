// 用户类型
export interface User {
  id: number;
  name: string;
  email: string;
  avatar?: string;
  bio?: string;
  budget: number;
  total_earned: number;
  total_spent: number;
  skills: string[];
  specialties: string[];
  settings: UserSettings;
  created_at: string;
}

export interface UserSettings {
  auto_spend_enabled: boolean;
  auto_spend_threshold: number;
  auto_spend_daily_limit: number;
  auto_invest_enabled: boolean;
  auto_invest_threshold: number;
}

// 项目类型
export interface Project {
  id: number;
  name: string;
  description: string;
  product_type: ProductType;
  status: ProjectStatus;
  valuation: number;
  funding_pool: number;
  total_revenue: number;
  owner_id: number;
  team_members: TeamMember[];
  price_per_use: number;
  usage_count: number;
  prd_content?: string;
  created_at: string;
  owner?: User;
}

export type ProductType = 'human_web' | 'human_app' | 'agent_skill' | 'agent_mcp' | 'agent_service';
export type ProjectStatus = 'exploring' | 'team_forming' | 'developing' | 'launched' | 'iterating';

export interface TeamMember {
  agent_id: number;
  role: string;
  equity: number;
}

// 交易类型
export interface Transaction {
  id: number;
  from_user_id: number;
  from_user_name: string;
  to_user_id?: number;
  to_user_name?: string;
  to_project_id?: number;
  to_project_name?: string;
  amount: number;
  transaction_type: TransactionType;
  status: TransactionStatus;
  description?: string;
  expected_return?: string;
  created_at: string;
}

export type TransactionType = 'spend' | 'income' | 'invest' | 'dividend' | 'cost';
export type TransactionStatus = 'pending' | 'approved' | 'rejected' | 'auto_approved';

// 投资类型
export interface Investment {
  id: number;
  investor_id: number;
  investor_name: string;
  project_id: number;
  project_name: string;
  amount: number;
  equity_percentage: number;
  investment_reason?: string;
  expected_roi?: number;
  is_auto_invest: boolean;
  created_at: string;
}

// Dashboard类型
export interface DashboardStats {
  total_budget: number;
  total_earned: number;
  total_spent: number;
  active_investments: number;
  owned_projects: number;
}

export interface SpendingAnalytics {
  source_agent: string;
  target_product: string;
  amount: number;
  status: string;
  expected_return: string;
  actual_return?: number;
  date: string;
}

export interface DashboardData {
  stats: DashboardStats;
  recent_transactions: Transaction[];
  spending_analytics: SpendingAnalytics[];
  auto_settings: UserSettings;
}

// API响应类型
export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data?: T;
}
