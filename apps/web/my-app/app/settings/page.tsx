'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Settings, Zap, TrendingUp, Save, User as UserIcon } from 'lucide-react';
import type { User } from '@/app/types';

export default function SettingsPage() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const router = useRouter();

  // Settings form state
  const [autoSpendEnabled, setAutoSpendEnabled] = useState(false);
  const [autoSpendThreshold, setAutoSpendThreshold] = useState(50);
  const [autoSpendDailyLimit, setAutoSpendDailyLimit] = useState(200);
  const [autoInvestEnabled, setAutoInvestEnabled] = useState(false);
  const [autoInvestThreshold, setAutoInvestThreshold] = useState(100);

  // Profile form state
  const [name, setName] = useState('');
  const [bio, setBio] = useState('');

  useEffect(() => {
    const token = api.getToken();
    if (!token) {
      router.push('/');
      return;
    }
    loadUser();
  }, []);

  async function loadUser() {
    try {
      const userData = await api.getMe();
      setUser(userData);
      setAutoSpendEnabled(userData.settings.auto_spend_enabled);
      setAutoSpendThreshold(userData.settings.auto_spend_threshold);
      setAutoSpendDailyLimit(userData.settings.auto_spend_daily_limit);
      setAutoInvestEnabled(userData.settings.auto_invest_enabled);
      setAutoInvestThreshold(userData.settings.auto_invest_threshold);
      setName(userData.name || '');
      setBio(userData.bio || '');
    } catch {
      router.push('/');
    } finally {
      setLoading(false);
    }
  }

  async function saveSettings() {
    setSaving(true);
    setMessage('');
    try {
      await api.updateSettings({
        auto_spend_enabled: autoSpendEnabled,
        auto_spend_threshold: autoSpendThreshold,
        auto_spend_daily_limit: autoSpendDailyLimit,
        auto_invest_enabled: autoInvestEnabled,
        auto_invest_threshold: autoInvestThreshold,
      });
      setMessage('✅ 设置已保存');
    } catch {
      setMessage('❌ 保存失败');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-lg text-gray-600">加载中...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
            <Settings className="h-8 w-8" />
            设置
          </h1>
          <p className="mt-2 text-gray-600">管理你的 Agent 自动消费和投资规则</p>
        </div>

        {/* Profile */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserIcon className="h-5 w-5" />
              个人信息
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="h-16 w-16 rounded-full bg-blue-100 flex items-center justify-center text-2xl font-bold text-blue-600">
                {user?.name?.[0] || 'U'}
              </div>
              <div>
                <p className="font-semibold text-lg">{user?.name}</p>
                <p className="text-sm text-gray-500">{user?.email}</p>
                <div className="flex gap-2 mt-1">
                  <Badge>CP: {user?.budget.toFixed(2)}</Badge>
                  <Badge variant="outline">收益: {user?.total_earned.toFixed(2)}</Badge>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Auto-Spend */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-yellow-600" />
              自动消费设置
            </CardTitle>
            <CardDescription>
              当 Agent 需要使用其他 Agent 的产品/服务时，满足条件可自动支付
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <Label>启用自动消费</Label>
              <button
                onClick={() => setAutoSpendEnabled(!autoSpendEnabled)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  autoSpendEnabled ? 'bg-blue-600' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    autoSpendEnabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <div>
              <Label htmlFor="spend-threshold">单笔自动支付阈值 (CP)</Label>
              <Input
                id="spend-threshold"
                type="number"
                value={autoSpendThreshold}
                onChange={(e) => setAutoSpendThreshold(Number(e.target.value))}
                disabled={!autoSpendEnabled}
              />
              <p className="text-xs text-gray-500 mt-1">单笔 ≤ 此金额时自动批准</p>
            </div>

            <div>
              <Label htmlFor="spend-daily">每日自动支付上限 (CP)</Label>
              <Input
                id="spend-daily"
                type="number"
                value={autoSpendDailyLimit}
                onChange={(e) => setAutoSpendDailyLimit(Number(e.target.value))}
                disabled={!autoSpendEnabled}
              />
              <p className="text-xs text-gray-500 mt-1">当日累计自动支付不超过此金额</p>
            </div>
          </CardContent>
        </Card>

        {/* Auto-Invest */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-green-600" />
              自动投资设置
            </CardTitle>
            <CardDescription>
              Agent 可在满足条件时自动执行投资，无需每次审批
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <Label>启用自动投资</Label>
              <button
                onClick={() => setAutoInvestEnabled(!autoInvestEnabled)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  autoInvestEnabled ? 'bg-blue-600' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    autoInvestEnabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <div>
              <Label htmlFor="invest-threshold">单笔自动投资阈值 (CP)</Label>
              <Input
                id="invest-threshold"
                type="number"
                value={autoInvestThreshold}
                onChange={(e) => setAutoInvestThreshold(Number(e.target.value))}
                disabled={!autoInvestEnabled}
              />
              <p className="text-xs text-gray-500 mt-1">投资金额 ≤ 此值且开启自动投资时，Agent 自动执行</p>
            </div>
          </CardContent>
        </Card>

        {/* Save */}
        <div className="flex items-center gap-4">
          <Button onClick={saveSettings} disabled={saving} className="w-full">
            <Save className="mr-2 h-4 w-4" />
            {saving ? '保存中...' : '保存设置'}
          </Button>
        </div>
        {message && (
          <p className="mt-3 text-center text-sm">{message}</p>
        )}
      </div>
    </div>
  );
}
