'use client';

import { useEffect, useState } from 'react';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Package, Zap, Server, ShoppingCart, TrendingUp } from 'lucide-react';
import type { Project } from '@/app/types';

export default function MarketplacePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMarketplace();
  }, []);

  async function loadMarketplace() {
    try {
      const data = await api.getMarketplace();
      setProjects(data);
    } catch (err) {
      console.error('加载市场失败:', err);
    } finally {
      setLoading(false);
    }
  }

  const skills = projects.filter((p) => p.product_type === 'agent_skill');
  const mcps = projects.filter((p) => p.product_type === 'agent_mcp');
  const services = projects.filter((p) => p.product_type === 'agent_service');
  const humanProducts = projects.filter(
    (p) => ['human_web', 'human_app'].includes(p.product_type)
  );

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">市场</h1>
          <p className="mt-2 text-gray-600">浏览和购买 Agent 产品与服务</p>
        </div>

        <Tabs defaultValue="skills">
          <TabsList className="mb-6">
            <TabsTrigger value="skills">
              <Zap className="mr-2 h-4 w-4" />
              Skills
            </TabsTrigger>
            <TabsTrigger value="mcp">
              <Server className="mr-2 h-4 w-4" />
              MCP 服务
            </TabsTrigger>
            <TabsTrigger value="services">
              <Package className="mr-2 h-4 w-4" />
              Agent 服务
            </TabsTrigger>
            <TabsTrigger value="human">
              <ShoppingCart className="mr-2 h-4 w-4" />
              人类产品
            </TabsTrigger>
          </TabsList>

          <TabsContent value="skills">
            <ProductGrid
              products={skills}
              loading={loading}
              emptyText="暂无 Skills 上架"
              type="skill"
            />
          </TabsContent>

          <TabsContent value="mcp">
            <ProductGrid
              products={mcps}
              loading={loading}
              emptyText="暂无 MCP 服务上架"
              type="mcp"
            />
          </TabsContent>

          <TabsContent value="services">
            <ProductGrid
              products={services}
              loading={loading}
              emptyText="暂无 Agent 服务"
              type="service"
            />
          </TabsContent>

          <TabsContent value="human">
            <ProductGrid
              products={humanProducts}
              loading={loading}
              emptyText="暂无人类产品"
              type="human"
            />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

function ProductGrid({
  products,
  loading,
  emptyText,
  type,
}: {
  products: Project[];
  loading: boolean;
  emptyText: string;
  type: string;
}) {
  if (loading) {
    return (
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {[...Array(6)].map((_, i) => (
          <Card key={i} className="animate-pulse">
            <CardContent className="h-48">
              <div className="h-4 bg-gray-200 rounded w-3/4 mb-4"></div>
              <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (products.length === 0) {
    return (
      <div className="text-center py-16 bg-white rounded-lg border">
        <p className="text-gray-500">{emptyText}</p>
      </div>
    );
  }

  return (
    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} type={type} />
      ))}
    </div>
  );
}

function ProductCard({ product, type }: { product: Project; type: string }) {
  const isAgentProduct = ['skill', 'mcp', 'service'].includes(type);
  const [showSpend, setShowSpend] = useState(false);
  const [showInvest, setShowInvest] = useState(false);
  const [reason, setReason] = useState('');
  const [expectedReturn, setExpectedReturn] = useState('');
  const [risk, setRisk] = useState('');
  const [recommendedAction, setRecommendedAction] = useState('');
  const [investAmount, setInvestAmount] = useState('');
  const [investReason, setInvestReason] = useState('');
  const [expectedRoi, setExpectedRoi] = useState('');
  const [investRisk, setInvestRisk] = useState('');
  const [investAction, setInvestAction] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [result, setResult] = useState('');

  // 打开消费弹窗时，AI 自动生成理由
  async function openSpendDialog() {
    setShowSpend(true);
    setAiLoading(true);
    setReason('');
    setExpectedReturn('');
    setRisk('');
    setResult('');
    try {
      const ai = await api.generateSpendReason(product.id);
      setReason(ai.reason);
      setExpectedReturn(ai.expected_return);
      setRisk(ai.risk);
      setRecommendedAction(ai.recommended_action);
    } catch {
      // AI 失败时用默认值
      setReason(`使用「${product.name}」提升效率`);
      setExpectedReturn(`预计节省约 ${((product.price_per_use || 0) * 1.5).toFixed(1)} CP`);
      setRisk('低风险');
      setRecommendedAction('approve');
    } finally {
      setAiLoading(false);
    }
  }

  // 打开投资弹窗时，预填金额后 AI 自动生成建议
  async function openInvestDialog() {
    setShowInvest(true);
    setInvestAmount('');
    setInvestReason('');
    setExpectedRoi('');
    setInvestRisk('');
    setResult('');
  }

  async function generateInvestAI() {
    if (!investAmount || Number(investAmount) <= 0) return;
    setAiLoading(true);
    try {
      const ai = await api.generateInvestReason(product.id, Number(investAmount));
      setInvestReason(ai.reason);
      setExpectedRoi(String(ai.expected_roi));
      setInvestRisk(ai.risk_level);
      setInvestAction(ai.recommended_action);
    } catch {
      setInvestReason(`投资「${product.name}」获取股权`);
      setExpectedRoi('20');
      setInvestRisk('medium');
      setInvestAction('cautious');
    } finally {
      setAiLoading(false);
    }
  }

  async function handleSpend() {
    setSubmitting(true);
    setResult('');
    try {
      const res = await api.createSpendingRequest({
        target_project_id: product.id,
        amount: product.price_per_use || 0,
        reason: reason,
        expected_return: expectedReturn,
        risk: risk,
      });
      setResult(`✅ ${res.message}`);
      setTimeout(() => { setShowSpend(false); setResult(''); }, 2000);
    } catch (err: any) {
      setResult(`❌ ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleInvest() {
    setSubmitting(true);
    setResult('');
    try {
      const res: any = await api.createInvestment({
        project_id: product.id,
        amount: Number(investAmount),
        investment_reason: investReason,
        expected_roi: Number(expectedRoi) || 20,
        risk_level: investRisk || 'medium',
      });
      setResult(`✅ ${res.message || '投资成功'}`);
      setTimeout(() => { setShowInvest(false); setResult(''); }, 2000);
    } catch (err: any) {
      setResult(`❌ ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Card className="flex flex-col">
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle className="text-lg">{product.name}</CardTitle>
              <CardDescription className="mt-1">{product.description}</CardDescription>
            </div>
            <Badge variant="outline">{product.product_type}</Badge>
          </div>
        </CardHeader>
        <CardContent className="flex-1">
          <div className="space-y-3">
            {product.owner && (
              <div className="flex items-center gap-2">
                <div className="h-6 w-6 rounded-full bg-blue-100 flex items-center justify-center text-xs font-bold text-blue-600">
                  {product.owner.name?.[0] || '?'}
                </div>
                <span className="text-sm text-gray-600">{product.owner.name}</span>
              </div>
            )}

            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">估值</span>
              <span className="font-medium">{product.valuation?.toFixed(2) || 0} CP</span>
            </div>

            {isAgentProduct && (
              <>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">每次使用</span>
                  <span className="font-medium text-blue-600">
                    {product.price_per_use?.toFixed(2) || 0} CP
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">使用次数</span>
                  <span className="font-medium">{product.usage_count || 0}</span>
                </div>
              </>
            )}

            <div className="pt-3 flex gap-2">
              {isAgentProduct ? (
                <Button className="flex-1" onClick={openSpendDialog}
                  disabled={!product.price_per_use}>
                  申请使用
                </Button>
              ) : (
                <Button className="flex-1" variant="outline" onClick={openInvestDialog}>
                  查看详情
                </Button>
              )}
              <Button variant="outline" size="icon" onClick={openInvestDialog} title="投资">
                <TrendingUp className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 申请使用 Dialog — AI 自动生成理由 */}
      <Dialog open={showSpend} onOpenChange={setShowSpend}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>🤖 AI 消费决策 · {product.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="bg-blue-50 rounded p-3 text-sm border border-blue-200">
              <p className="font-medium text-blue-800">价格：{product.price_per_use} CP / 次</p>
            </div>

            {aiLoading ? (
              <div className="text-center py-6">
                <div className="animate-spin h-6 w-6 border-2 border-blue-600 border-t-transparent rounded-full mx-auto mb-2" />
                <p className="text-sm text-gray-500">AI 正在分析...</p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="bg-gray-50 rounded p-3 space-y-2 text-sm">
                  <p><strong>📋 理由：</strong>{reason}</p>
                  <p><strong>📈 预期收益：</strong>{expectedReturn}</p>
                  <p><strong>⚠️ 风险：</strong>{risk}</p>
                  <p><strong>🎯 AI 建议：</strong>
                    <span className={recommendedAction === 'approve' ? 'text-green-600 font-medium' : recommendedAction === 'reject' ? 'text-red-600 font-medium' : 'text-yellow-600 font-medium'}>
                      {recommendedAction === 'approve' ? '✅ 建议批准' : recommendedAction === 'reject' ? '❌ 建议拒绝' : '⚡ 建议谨慎'}
                    </span>
                  </p>
                </div>
              </div>
            )}

            {result && <p className="text-sm">{result}</p>}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setShowSpend(false)} className="flex-1">
                取消
              </Button>
              <Button onClick={handleSpend} disabled={submitting || aiLoading} className="flex-1">
                {submitting ? '提交中...' : `确认支付 ${product.price_per_use} CP`}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 投资 Dialog — AI 自动生成建议 */}
      <Dialog open={showInvest} onOpenChange={setShowInvest}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>🤖 AI 投资决策 · {product.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="bg-green-50 rounded p-3 text-sm border border-green-200">
              <p className="font-medium text-green-800">当前估值：{product.valuation?.toFixed(2)} CP</p>
            </div>

            <div>
              <Label>投资金额 (CP)</Label>
              <div className="flex gap-2 mt-1">
                <Input type="number" value={investAmount}
                  onChange={(e) => setInvestAmount(e.target.value)}
                  placeholder="输入投资金额" />
                <Button variant="outline" onClick={generateInvestAI}
                  disabled={aiLoading || !investAmount}>
                  {aiLoading ? '分析中...' : '🤖 AI 分析'}
                </Button>
              </div>
            </div>

            {investReason && (
              <div className="bg-gray-50 rounded p-3 space-y-2 text-sm">
                <p><strong>📋 投资理由：</strong>{investReason}</p>
                <p><strong>📈 预期 ROI：</strong>{expectedRoi}%</p>
                <p><strong>⚠️ 风险等级：</strong>
                  <span className={investRisk === 'low' ? 'text-green-600' : investRisk === 'high' ? 'text-red-600' : 'text-yellow-600'}>
                    {investRisk === 'low' ? '🟢 低风险' : investRisk === 'high' ? '🔴 高风险' : '🟡 中等风险'}
                  </span>
                </p>
                <p><strong>🎯 AI 建议：</strong>
                  <span className={investAction === 'approve' ? 'text-green-600 font-medium' : investAction === 'reject' ? 'text-red-600 font-medium' : 'text-yellow-600 font-medium'}>
                    {investAction === 'approve' ? '✅ 建议投资' : investAction === 'reject' ? '❌ 不建议投资' : '⚡ 建议谨慎'}
                  </span>
                </p>
              </div>
            )}

            {result && <p className="text-sm">{result}</p>}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setShowInvest(false)} className="flex-1">
                取消
              </Button>
              <Button onClick={handleInvest} disabled={submitting || !investAmount || !investReason} className="flex-1">
                {submitting ? '提交中...' : '确认投资'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
