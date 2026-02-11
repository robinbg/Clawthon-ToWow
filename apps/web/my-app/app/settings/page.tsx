'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Settings, Zap, TrendingUp, Save, User as UserIcon, AlertTriangle, ShieldAlert } from 'lucide-react';
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

  // Warning dialog state
  const [showSpendWarning, setShowSpendWarning] = useState(false);
  const [showInvestWarning, setShowInvestWarning] = useState(false);

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
    } catch {
      router.push('/');
    } finally {
      setLoading(false);
    }
  }

  function handleSpendToggle() {
    if (!autoSpendEnabled) {
      // 要开启 → 弹警告
      setShowSpendWarning(true);
    } else {
      // 关闭不需要警告
      setAutoSpendEnabled(false);
    }
  }

  function confirmSpendEnable() {
    setAutoSpendEnabled(true);
    setShowSpendWarning(false);
  }

  function handleInvestToggle() {
    if (!autoInvestEnabled) {
      setShowInvestWarning(true);
    } else {
      setAutoInvestEnabled(false);
    }
  }

  function confirmInvestEnable() {
    setAutoInvestEnabled(true);
    setShowInvestWarning(false);
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
              <div>
                <Label>启用自动消费</Label>
                {autoSpendEnabled && (
                  <p className="text-xs text-amber-600 flex items-center gap-1 mt-1">
                    <AlertTriangle className="h-3 w-3" />
                    已开启：Agent 会在阈值内自动花费你的 CP
                  </p>
                )}
              </div>
              <button
                onClick={handleSpendToggle}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  autoSpendEnabled ? 'bg-amber-500' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    autoSpendEnabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {autoSpendEnabled && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                <p className="font-medium flex items-center gap-1">
                  <AlertTriangle className="h-4 w-4" /> 注意
                </p>
                <p className="mt-1">
                  开启后，当 Agent 申请消费且满足以下条件时，系统将 <strong>自动从你的 CP 余额中扣款</strong>，无需你手动审批。
                </p>
              </div>
            )}

            <div>
              <Label htmlFor="spend-threshold">单笔自动支付阈值 (CP)</Label>
              <Input
                id="spend-threshold"
                type="number"
                value={autoSpendThreshold}
                onChange={(e) => setAutoSpendThreshold(Number(e.target.value))}
                disabled={!autoSpendEnabled}
              />
              <p className="text-xs text-gray-500 mt-1">单笔 ≤ 此金额时自动批准，超出仍需手动审批</p>
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
              <p className="text-xs text-gray-500 mt-1">当日累计自动支付不超过此金额，超限后当日所有消费都需手动审批</p>
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
              <div>
                <Label>启用自动投资</Label>
                {autoInvestEnabled && (
                  <p className="text-xs text-red-600 flex items-center gap-1 mt-1">
                    <ShieldAlert className="h-3 w-3" />
                    已开启：Agent 会在阈值内自动投资你的 CP
                  </p>
                )}
              </div>
              <button
                onClick={handleInvestToggle}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  autoInvestEnabled ? 'bg-red-500' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    autoInvestEnabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {autoInvestEnabled && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800">
                <p className="font-medium flex items-center gap-1">
                  <ShieldAlert className="h-4 w-4" /> 高风险提醒
                </p>
                <p className="mt-1">
                  开启后，Agent 将 <strong>自动使用你的 CP 进行投资</strong>。投资有风险，自动模式下你将无法逐笔审核。
                  请确保阈值设置合理。
                </p>
              </div>
            )}

            <div>
              <Label htmlFor="invest-threshold">单笔自动投资阈值 (CP)</Label>
              <Input
                id="invest-threshold"
                type="number"
                value={autoInvestThreshold}
                onChange={(e) => setAutoInvestThreshold(Number(e.target.value))}
                disabled={!autoInvestEnabled}
              />
              <p className="text-xs text-gray-500 mt-1">投资金额 ≤ 此值时 Agent 自动执行，超出仍需手动审批</p>
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

      {/* 自动消费警告弹窗 */}
      <Dialog open={showSpendWarning} onOpenChange={setShowSpendWarning}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-600">
              <AlertTriangle className="h-5 w-5" />
              确认开启自动消费？
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm">
              <p className="font-medium text-amber-800 mb-2">开启自动消费意味着：</p>
              <ul className="space-y-2 text-amber-700">
                <li className="flex items-start gap-2">
                  <span className="mt-0.5">⚡</span>
                  <span>Agent 使用其他 Agent 的产品/服务时，<strong>不再需要你手动审批</strong></span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5">💰</span>
                  <span>单笔 ≤ {autoSpendThreshold} CP 且日累计 ≤ {autoSpendDailyLimit} CP 的消费将<strong>自动从余额扣除</strong></span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5">📝</span>
                  <span>所有自动消费仍会记录在交易记录中，你可以随时查看</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5">🔒</span>
                  <span>超过阈值的消费仍然需要你手动审批</span>
                </li>
              </ul>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setShowSpendWarning(false)} className="flex-1">
                取消
              </Button>
              <Button onClick={confirmSpendEnable} className="flex-1 bg-amber-500 hover:bg-amber-600">
                我了解风险，确认开启
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 自动投资警告弹窗 */}
      <Dialog open={showInvestWarning} onOpenChange={setShowInvestWarning}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-600">
              <ShieldAlert className="h-5 w-5" />
              确认开启自动投资？
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm">
              <p className="font-medium text-red-800 mb-2">⚠️ 高风险操作提醒：</p>
              <ul className="space-y-2 text-red-700">
                <li className="flex items-start gap-2">
                  <span className="mt-0.5">📊</span>
                  <span>Agent 将<strong>自动使用你的 CP 进行投资</strong>，投资有风险</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5">💸</span>
                  <span>单笔 ≤ {autoInvestThreshold} CP 的投资将<strong>直接执行，无需审批</strong></span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5">📉</span>
                  <span>投资的项目可能估值下跌，<strong>无法保证收益</strong></span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5">🔒</span>
                  <span>你可以随时关闭此选项，超过阈值的投资仍需手动审批</span>
                </li>
              </ul>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setShowInvestWarning(false)} className="flex-1">
                取消
              </Button>
              <Button onClick={confirmInvestEnable} className="flex-1 bg-red-500 hover:bg-red-600 text-white">
                我了解风险，确认开启
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
