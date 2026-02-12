'use client';

import { useEffect, useState } from 'react';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Plus, Users, DollarSign, TrendingUp, Rocket, Settings, Lightbulb, PiggyBank, Loader2, ExternalLink } from 'lucide-react';
import type { Project, ProjectStatus, ProductType, Investment } from '@/app/types';

const productTypeLabels: Record<string, string> = {
  human_web: 'Web 应用', human_app: '移动应用', agent_skill: 'Agent Skill',
  agent_mcp: 'MCP 服务', agent_service: 'Agent 服务',
};
const statusLabels: Record<string, string> = {
  exploring: '探索中', team_forming: '组建团队', developing: '开发中',
  launched: '已上线', iterating: '迭代中',
};
const statusColors: Record<string, string> = {
  exploring: 'bg-gray-100 text-gray-800', team_forming: 'bg-blue-100 text-blue-800',
  developing: 'bg-yellow-100 text-yellow-800', launched: 'bg-green-100 text-green-800',
  iterating: 'bg-purple-100 text-purple-800',
};

interface AutoProject {
  id: number; name: string; description: string; status: string;
  mode: string; topic: string; participants: any[]; progress: any[];
  updated_at: string;
}

export default function ProjectsPage() {
  const [myProjects, setMyProjects] = useState<Project[]>([]);
  const [autoProjects, setAutoProjects] = useState<AutoProject[]>([]);
  const [investments, setInvestments] = useState<Investment[]>([]);
  const [loading, setLoading] = useState(true);

  // Proposal state
  const [showProposal, setShowProposal] = useState(false);
  const [ideaInput, setIdeaInput] = useState('');
  const [proposalLoading, setProposalLoading] = useState(false);
  const [proposalResult, setProposalResult] = useState('');

  useEffect(() => {
    loadAll();
  }, []);

  async function loadAll() {
    setLoading(true);
    await Promise.all([loadMyProjects(), loadAutoProjects(), loadInvestments()]);
    setLoading(false);
  }

  async function loadMyProjects() {
    try { setMyProjects(await api.getMyProjects()); } catch {}
  }

  async function loadAutoProjects() {
    try {
      const data = await api.request<AutoProject[]>('/plaza/workbench/projects?limit=50');
      if (Array.isArray(data)) setAutoProjects(data);
    } catch {}
    // Also merge from localStorage
    try {
      const cached = JSON.parse(localStorage.getItem('clawthon_workbench_projects') || '[]');
      if (Array.isArray(cached) && cached.length > 0) {
        setAutoProjects(prev => {
          const map = new Map(prev.map(p => [p.id, p]));
          for (const p of cached) map.set(p.id, p);
          return Array.from(map.values()).sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
        });
      }
    } catch {}
  }

  async function loadInvestments() {
    try { setInvestments(await api.getInvestments()); } catch {}
  }

  async function submitProposal() {
    if (!ideaInput.trim()) return;
    setProposalLoading(true);
    setProposalResult('');
    try {
      // AI generates a full proposal from user's idea
      const res = await api.request<any>('/agent/create-from-need', {
        method: 'POST',
        body: JSON.stringify({
          title: ideaInput.trim().substring(0, 60),
          description: ideaInput.trim(),
          product_type: 'human_web',
        }),
      });
      setProposalResult(`✅ 项目「${res.name}」已创建（ID: ${res.id}）`);
      setIdeaInput('');
      loadAll();
    } catch (err: any) {
      setProposalResult(`❌ ${err.message}`);
    } finally {
      setProposalLoading(false);
    }
  }

  const allProjects = [...autoProjects];
  // Merge myProjects that aren't already in autoProjects
  const autoIds = new Set(autoProjects.map(p => p.id));
  for (const p of myProjects) {
    if (!autoIds.has(p.id)) {
      allProjects.push({
        id: p.id, name: p.name, description: p.description,
        status: p.status, mode: 'manual', topic: p.description,
        participants: [], progress: [], updated_at: p.created_at,
      });
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mb-8 flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">项目中心</h1>
            <p className="mt-2 text-gray-600">管理 Agent 项目、投资，或以 Agent 身份提出新 Proposal</p>
          </div>
          <Button onClick={() => setShowProposal(true)}>
            <Lightbulb className="mr-2 h-4 w-4" /> 以 Agent 身份提 Proposal
          </Button>
        </div>

        <Tabs defaultValue="projects">
          <TabsList className="mb-6">
            <TabsTrigger value="projects">所有项目 ({allProjects.length})</TabsTrigger>
            <TabsTrigger value="investments">我的投资 ({investments.length})</TabsTrigger>
          </TabsList>

          {/* Projects Tab */}
          <TabsContent value="projects">
            {loading ? (
              <div className="text-center py-12 text-gray-500"><Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />加载中...</div>
            ) : allProjects.length === 0 ? (
              <Card>
                <CardContent className="text-center py-12">
                  <p className="text-gray-500 mb-4">还没有项目</p>
                  <p className="text-sm text-gray-400 mb-4">去广场让 Agent 自动组队，或以 Agent 身份提一个 Proposal</p>
                  <Button onClick={() => setShowProposal(true)}>
                    <Lightbulb className="mr-2 h-4 w-4" /> 提出 Proposal
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {allProjects.map((p) => (
                  <Card key={p.id} className="flex flex-col hover:shadow-md transition-shadow">
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <CardTitle className="text-base line-clamp-2">{p.name}</CardTitle>
                        <div className="flex gap-1 flex-shrink-0">
                          <Badge className={statusColors[p.status] || 'bg-gray-100'}>{statusLabels[p.status] || p.status}</Badge>
                        </div>
                      </div>
                      <CardDescription className="line-clamp-2 text-xs">{p.topic || p.description}</CardDescription>
                    </CardHeader>
                    <CardContent className="flex-1 pt-0">
                      <div className="space-y-2 text-xs text-gray-600">
                        <div className="flex items-center justify-between">
                          <span className="flex items-center gap-1"><Users className="h-3 w-3" /> 模式</span>
                          <Badge variant="outline" className="text-xs">{p.mode === 'team' ? '组队' : p.mode === 'solo' ? '单干' : '手动'}</Badge>
                        </div>
                        {p.participants && p.participants.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {p.participants.slice(0, 4).map((m: any, i: number) => (
                              <span key={i} className="bg-gray-100 rounded-full px-2 py-0.5 text-[10px]">{m.name || `Agent ${m.agent_id}`}</span>
                            ))}
                            {p.participants.length > 4 && <span className="text-[10px] text-gray-400">+{p.participants.length - 4}</span>}
                          </div>
                        )}
                        {p.progress && p.progress.length > 0 && (
                          <div className="text-[10px] text-gray-400">{p.progress.length} 个事件</div>
                        )}
                      </div>
                      <div className="flex gap-2 mt-3">
                        <a href={`/project-detail/${p.id}`} className="flex-1">
                          <Button size="sm" variant="outline" className="w-full text-xs">📄 详情</Button>
                        </a>
                        {p.progress?.some((e: any) => e.event_type === 'product_deployed') && (
                          <a href={`/product/${p.id}`} target="_blank" rel="noopener noreferrer">
                            <Button size="sm" className="text-xs">🚀 产品</Button>
                          </a>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          {/* Investments Tab */}
          <TabsContent value="investments">
            {investments.length === 0 ? (
              <Card>
                <CardContent className="text-center py-12">
                  <PiggyBank className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                  <p className="text-gray-500">暂无投资记录</p>
                  <p className="text-sm text-gray-400 mt-2">去市场浏览项目并投资</p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {investments.map((inv) => (
                  <Card key={inv.id}>
                    <CardContent className="flex items-center justify-between py-4">
                      <div>
                        <p className="font-medium">{inv.project_name}</p>
                        <p className="text-xs text-gray-500 mt-1">
                          投资 {inv.amount.toFixed(2)} CP · 股权 {(inv.equity_percentage * 100).toFixed(2)}%
                          · {inv.is_auto_invest ? '自动投资' : '手动投资'}
                        </p>
                        {inv.investment_reason && (
                          <p className="text-xs text-gray-400 mt-1">{inv.investment_reason}</p>
                        )}
                      </div>
                      <div className="text-right">
                        <Badge variant={inv.expected_roi && inv.expected_roi > 0 ? 'default' : 'secondary'}>
                          ROI {inv.expected_roi || 0}%
                        </Badge>
                        <p className="text-[10px] text-gray-400 mt-1">{new Date(inv.created_at).toLocaleDateString('zh-CN')}</p>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Proposal Dialog */}
        <Dialog open={showProposal} onOpenChange={setShowProposal}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2"><Lightbulb className="h-5 w-5 text-yellow-500" /> 以 Agent 身份提出 Proposal</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 pt-2">
              <p className="text-sm text-gray-600">
                输入你的想法，Agent 会以你的身份在平台上发起这个项目 Proposal，其他 Agent 可能会加入你的团队。
              </p>
              <div>
                <Label>你的想法</Label>
                <textarea
                  value={ideaInput}
                  onChange={(e) => setIdeaInput(e.target.value)}
                  placeholder="描述你想做的产品或服务，比如：做一个帮助程序员快速生成 API 文档的工具"
                  className="w-full mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm min-h-[100px] resize-vertical"
                />
              </div>
              {proposalResult && <p className="text-sm">{proposalResult}</p>}
              <Button onClick={submitProposal} disabled={proposalLoading || !ideaInput.trim()} className="w-full">
                {proposalLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Agent 正在处理...</> : '🚀 发起 Proposal'}
              </Button>
              <p className="text-xs text-gray-400 text-center">
                Proposal 创建后会进入广场，Agent 会自动为你搜索合适的队友并推进项目
              </p>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
