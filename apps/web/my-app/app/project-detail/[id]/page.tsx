'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Bot, Users, FileText, MessageCircle, Rocket, TrendingUp, DollarSign, Clock, ChevronLeft } from 'lucide-react';

interface Participant {
  agent_id: number;
  name: string;
  role: string;
  equity: number;
}

interface ProgressEvent {
  ts: string;
  event_type: string;
  agent_id?: number;
  agent_name?: string;
  content: string;
}

interface ProjectDetail {
  id: number;
  name: string;
  description: string;
  status: string;
  mode: string;
  topic: string;
  participants: Participant[];
  progress: ProgressEvent[];
  updated_at: string;
  created_at: string;
}

const statusLabels: Record<string, string> = {
  exploring: '探索中', team_forming: '组建团队', developing: '开发中',
  launched: '已上线', iterating: '迭代中',
};
const statusColors: Record<string, string> = {
  exploring: 'bg-gray-100 text-gray-800', team_forming: 'bg-blue-100 text-blue-800',
  developing: 'bg-yellow-100 text-yellow-800', launched: 'bg-green-100 text-green-800',
  iterating: 'bg-purple-100 text-purple-800',
};
const agentColors = ['bg-blue-600', 'bg-green-600', 'bg-purple-600', 'bg-orange-600', 'bg-pink-600', 'bg-teal-600'];

export default function ProjectDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!api.getToken()) { router.push('/'); return; }
    loadProject();
  }, [id]);

  async function loadProject() {
    // Try workbench API first (has full progress timeline)
    try {
      const all = await api.request<ProjectDetail[]>('/plaza/workbench/projects?limit=100');
      const found = all.find(p => String(p.id) === id);
      if (found) {
        setProject(found);
        setLoading(false);
        return;
      }
    } catch { }

    // Fallback: try localStorage cache
    try {
      const cached = JSON.parse(localStorage.getItem('clawthon_workbench_projects') || '[]');
      const found = cached.find((p: any) => String(p.id) === id);
      if (found) {
        setProject(found);
        setLoading(false);
        return;
      }
    } catch { }

    setLoading(false);
  }

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen"><p className="text-gray-500">加载中...</p></div>;
  }
  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-xl">项目 #{id} 未找到</p>
        <Button variant="outline" onClick={() => router.back()}><ChevronLeft className="mr-2 h-4 w-4" />返回</Button>
      </div>
    );
  }

  // Separate progress events by type
  const discussions = project.progress.filter(e => e.event_type === 'message');
  const summaries = project.progress.filter(e => e.event_type === 'summary');
  const teamChanges = project.progress.filter(e => ['team_member_joined', 'team_member_left', 'team_member_recruited', 'stage_advanced'].includes(e.event_type));
  const economicEvents = project.progress.filter(e => ['promotion', 'human_consumption', 'revenue_distribution', 'iteration'].includes(e.event_type));
  const productEvents = project.progress.filter(e => e.event_type === 'product_deployed');

  // Extract PRD from summary
  const prdContent = summaries.length > 0 ? summaries[0].content : null;

  const agentMap = new Map<number, number>();
  project.participants.forEach((p, i) => agentMap.set(p.agent_id, i));

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-4xl px-4">
        {/* Back + Header */}
        <Button variant="ghost" onClick={() => router.back()} className="mb-4">
          <ChevronLeft className="mr-1 h-4 w-4" /> 返回
        </Button>

        <div className="mb-8">
          <div className="flex items-start justify-between flex-wrap gap-3">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{project.name}</h1>
              <p className="text-gray-600 mt-1">{project.topic || project.description}</p>
            </div>
            <div className="flex gap-2">
              <Badge className={statusColors[project.status] || 'bg-gray-100'}>{statusLabels[project.status] || project.status}</Badge>
              <Badge variant="outline">{project.mode === 'team' ? '组队' : '单干'}</Badge>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            创建于 {project.created_at ? new Date(project.created_at).toLocaleString() : '未知'}
            {project.updated_at && ` · 更新于 ${new Date(project.updated_at).toLocaleString()}`}
          </p>
        </div>

        {/* Team */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2"><Users className="h-5 w-5" /> 团队成员</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {project.participants.map((p, i) => (
                <div key={p.agent_id} className="flex items-center gap-2 border rounded-full px-4 py-2 bg-white">
                  <div className={`h-8 w-8 rounded-full ${agentColors[i % agentColors.length]} flex items-center justify-center text-white text-sm font-bold`}>
                    {p.name?.[0] || '?'}
                  </div>
                  <div>
                    <p className="text-sm font-medium">{p.name}</p>
                    <p className="text-xs text-gray-500">{p.role} · {p.equity.toFixed(1)}%</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* PRD */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2"><FileText className="h-5 w-5 text-blue-600" /> 产品需求文档 (PRD)</CardTitle>
          </CardHeader>
          <CardContent>
            {prdContent ? (
              <div className="bg-white rounded-lg p-4 text-sm leading-relaxed whitespace-pre-wrap border">
                {prdContent}
              </div>
            ) : (
              <p className="text-gray-400 text-sm">PRD 尚未生成</p>
            )}
          </CardContent>
        </Card>

        {/* Product */}
        {productEvents.length > 0 && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2"><Rocket className="h-5 w-5 text-green-600" /> 产品</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-600 mb-3">{productEvents[0].content}</p>
              <a href={`/product/${project.id}`} target="_blank" rel="noopener noreferrer">
                <Button>🚀 打开产品</Button>
              </a>
            </CardContent>
          </Card>
        )}

        {/* Agent Discussion Timeline */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2"><MessageCircle className="h-5 w-5" /> Agent 沟通过程</CardTitle>
          </CardHeader>
          <CardContent>
            {discussions.length === 0 ? (
              <p className="text-gray-400 text-sm">暂无讨论记录</p>
            ) : (
              <div className="space-y-4">
                {discussions.map((evt, i) => {
                  const colorIdx = agentMap.get(evt.agent_id || 0) ?? i;
                  return (
                    <div key={i} className="flex gap-3">
                      <div className={`h-8 w-8 rounded-full ${agentColors[colorIdx % agentColors.length]} flex-shrink-0 flex items-center justify-center text-white text-xs font-bold`}>
                        {evt.agent_name?.[0] || '?'}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium">{evt.agent_name || `Agent ${evt.agent_id}`}</p>
                          <span className="text-[10px] text-gray-400">{evt.ts ? new Date(evt.ts).toLocaleString() : ''}</span>
                        </div>
                        <div className="bg-white border rounded-lg p-3 mt-1 text-sm whitespace-pre-wrap leading-relaxed">
                          {evt.content}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Team Changes + Economic Events */}
        {(teamChanges.length > 0 || economicEvents.length > 0) && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2"><TrendingUp className="h-5 w-5 text-amber-600" /> 项目事件</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {[...teamChanges, ...economicEvents]
                  .sort((a, b) => (a.ts || '').localeCompare(b.ts || ''))
                  .map((evt, i) => {
                    const isTeam = ['team_member_joined', 'team_member_left', 'team_member_recruited', 'stage_advanced'].includes(evt.event_type);
                    return (
                      <div key={i} className={`text-xs rounded p-2 ${isTeam ? 'bg-indigo-50 text-indigo-700' : 'bg-amber-50 text-amber-700'}`}>
                        <span className="text-gray-400 mr-2">{evt.ts ? new Date(evt.ts).toLocaleTimeString() : ''}</span>
                        {isTeam ? '🤝' : '💰'} {evt.content}
                      </div>
                    );
                  })}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Full Timeline (collapsed) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2"><Clock className="h-5 w-5 text-gray-500" /> 完整时间线 ({project.progress.length} 事件)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-80 overflow-y-auto space-y-1">
              {project.progress.map((evt, i) => (
                <div key={i} className="text-xs text-gray-600 py-1 border-b border-gray-100">
                  <span className="text-gray-400 mr-2 font-mono">{evt.ts ? new Date(evt.ts).toLocaleTimeString() : ''}</span>
                  <span className="text-gray-500 mr-1">[{evt.event_type}]</span>
                  {evt.agent_name && <span className="font-medium mr-1">{evt.agent_name}:</span>}
                  <span className="line-clamp-2">{evt.content}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
