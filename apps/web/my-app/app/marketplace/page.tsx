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
  const [investAmount, setInvestAmount] = useState('');
  const [investReason, setInvestReason] = useState('');
  const [expectedRoi, setExpectedRoi] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState('');

  async function handleSpend() {
    setSubmitting(true);
    setResult('');
    try {
      const res = await api.createSpendingRequest({
        target_project_id: product.id,
        amount: product.price_per_use || 0,
        reason: reason || '使用该服务',
        expected_return: expectedReturn || '提升效率',
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
        investment_reason: investReason || '看好该项目',
        expected_roi: Number(expectedRoi) || 20,
        risk_level: 'medium',
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
                <Button className="flex-1" onClick={() => setShowSpend(true)}
                  disabled={!product.price_per_use}>
                  申请使用
                </Button>
              ) : (
                <Button className="flex-1" variant="outline" onClick={() => setShowInvest(true)}>
                  查看详情
                </Button>
              )}
              <Button variant="outline" size="icon" onClick={() => setShowInvest(true)} title="投资">
                <TrendingUp className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 申请使用 Dialog */}
      <Dialog open={showSpend} onOpenChange={setShowSpend}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>申请使用 · {product.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="bg-gray-50 rounded p-3 text-sm">
              <p>价格：<strong>{product.price_per_use} CP</strong> / 次</p>
              <p className="text-gray-500 mt-1">消费将从你的 CP 余额中扣除</p>
            </div>
            <div>
              <Label>使用理由</Label>
              <Input value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="为什么需要这个服务？" />
            </div>
            <div>
              <Label>预期收益</Label>
              <Input value={expectedReturn} onChange={(e) => setExpectedReturn(e.target.value)}
                placeholder="预计带来什么价值？" />
            </div>
            {result && <p className="text-sm">{result}</p>}
            <Button onClick={handleSpend} disabled={submitting} className="w-full">
              {submitting ? '提交中...' : `确认支付 ${product.price_per_use} CP`}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* 投资 Dialog */}
      <Dialog open={showInvest} onOpenChange={setShowInvest}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>投资 · {product.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="bg-gray-50 rounded p-3 text-sm">
              <p>当前估值：<strong>{product.valuation?.toFixed(2)} CP</strong></p>
              <p className="text-gray-500 mt-1">投资金额将换算为对应股权</p>
            </div>
            <div>
              <Label>投资金额 (CP)</Label>
              <Input type="number" value={investAmount}
                onChange={(e) => setInvestAmount(e.target.value)}
                placeholder="输入投资金额" />
            </div>
            <div>
              <Label>投资理由</Label>
              <Input value={investReason} onChange={(e) => setInvestReason(e.target.value)}
                placeholder="为什么看好这个项目？" />
            </div>
            <div>
              <Label>预期回报率 (%)</Label>
              <Input type="number" value={expectedRoi}
                onChange={(e) => setExpectedRoi(e.target.value)}
                placeholder="20" />
            </div>
            {result && <p className="text-sm">{result}</p>}
            <Button onClick={handleInvest} disabled={submitting || !investAmount} className="w-full">
              {submitting ? '提交中...' : '确认投资'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
