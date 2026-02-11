'use client';

import { useEffect, useState } from 'react';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Package, Zap, Server, ShoppingCart } from 'lucide-react';
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

  return (
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
              <img
                src={product.owner.avatar || '/default-avatar.png'}
                alt={product.owner.name}
                className="h-6 w-6 rounded-full"
              />
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

          <div className="pt-3">
            <Button
              className="w-full"
              variant={isAgentProduct ? 'default' : 'outline'}
              disabled={isAgentProduct && !product.price_per_use}
            >
              {isAgentProduct ? '申请使用' : '查看详情'}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
