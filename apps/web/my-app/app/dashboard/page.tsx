'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Wallet, TrendingUp, TrendingDown, PiggyBank, Briefcase } from 'lucide-react';
import type { DashboardData, Transaction, SpendingAnalytics } from '@/app/types';

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center"><div className="text-lg text-gray-600">加载中...</div></div>}>
      <DashboardContent />
    </Suspense>
  );
}

function DashboardContent() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const searchParams = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    // OAuth 回调后，从 URL 提取 token 并存到 localStorage
    const token = searchParams.get('token');
    if (token) {
      api.setToken(token);
      // 清除 URL 中的 token 参数
      router.replace('/dashboard');
    }
    loadDashboard();
  }, []);

  async function loadDashboard() {
    try {
      const dashboardData = await api.getDashboard();
      setData(dashboardData);
    } catch (err) {
      setError('加载 Dashboard 失败，请检查登录状态');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-lg text-gray-600">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-lg text-red-600">{error}</div>
      </div>
    );
  }

  if (!data) return null;

  const { stats, recent_transactions, spending_analytics, auto_settings } = data;

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-8">Dashboard</h1>

        {/* Stats Cards */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-5 mb-8">
          <StatCard
            icon={<Wallet className="h-5 w-5 text-blue-600" />}
            title="CP 余额"
            value={stats.total_budget.toFixed(2)}
            suffix="CP"
          />
          <StatCard
            icon={<TrendingUp className="h-5 w-5 text-green-600" />}
            title="累计收益"
            value={stats.total_earned.toFixed(2)}
            suffix="CP"
          />
          <StatCard
            icon={<TrendingDown className="h-5 w-5 text-red-600" />}
            title="累计支出"
            value={stats.total_spent.toFixed(2)}
            suffix="CP"
          />
          <StatCard
            icon={<Briefcase className="h-5 w-5 text-purple-600" />}
            title="活跃投资"
            value={stats.active_investments}
            suffix="个"
          />
          <StatCard
            icon={<PiggyBank className="h-5 w-5 text-yellow-600" />}
            title="拥有项目"
            value={stats.owned_projects}
            suffix="个"
          />
        </div>

        {/* Tabs */}
        <Tabs defaultValue="transactions" className="space-y-6">
          <TabsList>
            <TabsTrigger value="transactions">交易记录</TabsTrigger>
            <TabsTrigger value="spending">消费分析</TabsTrigger>
            <TabsTrigger value="settings">自动设置</TabsTrigger>
          </TabsList>

          <TabsContent value="transactions">
            <Card>
              <CardHeader>
                <CardTitle>最近交易</CardTitle>
              </CardHeader>
              <CardContent>
                <TransactionTable transactions={recent_transactions} />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="spending">
            <Card>
              <CardHeader>
                <CardTitle>Agent 消费分析</CardTitle>
              </CardHeader>
              <CardContent>
                <SpendingTable data={spending_analytics} />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="settings">
            <Card>
              <CardHeader>
                <CardTitle>自动设置</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="grid gap-6 md:grid-cols-2">
                  <div className="space-y-4">
                    <h3 className="font-semibold">自动消费</h3>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600">是否启用</span>
                      <Badge variant={auto_settings.auto_spend_enabled ? 'default' : 'secondary'}>
                        {auto_settings.auto_spend_enabled ? '已开启' : '已关闭'}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600">单笔阈值</span>
                      <span className="font-medium">{auto_settings.auto_spend_threshold} CP</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600">每日上限</span>
                      <span className="font-medium">{auto_settings.auto_spend_daily_limit} CP</span>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <h3 className="font-semibold">自动投资</h3>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600">是否启用</span>
                      <Badge variant={auto_settings.auto_invest_enabled ? 'default' : 'secondary'}>
                        {auto_settings.auto_invest_enabled ? '已开启' : '已关闭'}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600">单笔阈值</span>
                      <span className="font-medium">{auto_settings.auto_invest_threshold} CP</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

function StatCard({
  icon,
  title,
  value,
  suffix,
}: {
  icon: React.ReactNode;
  title: string;
  value: string | number;
  suffix: string;
}) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center gap-4">
          <div className="p-2 bg-gray-100 rounded-lg">{icon}</div>
          <div>
            <p className="text-sm text-gray-600">{title}</p>
            <p className="text-2xl font-bold">
              {value} <span className="text-sm font-normal text-gray-500">{suffix}</span>
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function TransactionTable({ transactions }: { transactions: Transaction[] }) {
  if (transactions.length === 0) {
    return <div className="text-center py-8 text-gray-500">暂无交易记录</div>;
  }

  const getStatusBadge = (status: string) => {
    const variants: Record<string, string> = {
      pending: 'bg-yellow-100 text-yellow-800',
      approved: 'bg-green-100 text-green-800',
      rejected: 'bg-red-100 text-red-800',
      auto_approved: 'bg-blue-100 text-blue-800',
    };
    const labels: Record<string, string> = {
      pending: '待审批',
      approved: '已批准',
      rejected: '已拒绝',
      auto_approved: '自动批准',
    };
    return (
      <Badge className={variants[status] || 'bg-gray-100'}>{labels[status] || status}</Badge>
    );
  };

  const getTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      spend: '消费',
      income: '收入',
      invest: '投资',
      dividend: '分红',
      cost: '成本',
    };
    return labels[type] || type;
  };

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>类型</TableHead>
          <TableHead>金额</TableHead>
          <TableHead>目标</TableHead>
          <TableHead>状态</TableHead>
          <TableHead>时间</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {transactions.map((tx) => (
          <TableRow key={tx.id}>
            <TableCell>{getTypeLabel(tx.transaction_type)}</TableCell>
            <TableCell className="font-medium">{tx.amount.toFixed(2)} CP</TableCell>
            <TableCell>{tx.to_project_name || tx.to_user_name || '-'}</TableCell>
            <TableCell>{getStatusBadge(tx.status)}</TableCell>
            <TableCell className="text-gray-500">
              {new Date(tx.created_at).toLocaleDateString('zh-CN')}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function SpendingTable({ data }: { data: SpendingAnalytics[] }) {
  if (data.length === 0) {
    return <div className="text-center py-8 text-gray-500">暂无消费数据</div>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>消费来源</TableHead>
          <TableHead>消费对象</TableHead>
          <TableHead>支付 CP</TableHead>
          <TableHead>状态</TableHead>
          <TableHead>预期收益</TableHead>
          <TableHead>实际收益</TableHead>
          <TableHead>日期</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.map((item, index) => (
          <TableRow key={index}>
            <TableCell>{item.source_agent}</TableCell>
            <TableCell>{item.target_product}</TableCell>
            <TableCell className="font-medium">{item.amount.toFixed(2)}</TableCell>
            <TableCell>
              <Badge
                variant={item.status === 'approved' ? 'default' : 'secondary'}
              >
                {item.status === 'auto_approved' ? '自动批准' : item.status}
              </Badge>
            </TableCell>
            <TableCell className="max-w-xs truncate">{item.expected_return}</TableCell>
            <TableCell>{item.actual_return?.toFixed(2) || '-'}</TableCell>
            <TableCell className="text-gray-500">
              {new Date(item.date).toLocaleDateString('zh-CN')}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
