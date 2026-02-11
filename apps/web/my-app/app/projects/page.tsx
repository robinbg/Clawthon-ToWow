'use client';

import { useEffect, useState } from 'react';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus, Users, DollarSign, TrendingUp } from 'lucide-react';
import type { Project, ProjectStatus, ProductType } from '@/app/types';

const productTypeLabels: Record<string, string> = {
  human_web: 'Web 应用',
  human_app: '移动应用',
  agent_skill: 'Agent Skill',
  agent_mcp: 'MCP 服务',
  agent_service: 'Agent 服务',
};

const statusLabels: Record<string, string> = {
  exploring: '探索中',
  team_forming: '组建团队',
  developing: '开发中',
  launched: '已上线',
  iterating: '迭代中',
};

const statusColors: Record<string, string> = {
  exploring: 'bg-gray-100 text-gray-800',
  team_forming: 'bg-blue-100 text-blue-800',
  developing: 'bg-yellow-100 text-yellow-800',
  launched: 'bg-green-100 text-green-800',
  iterating: 'bg-purple-100 text-purple-800',
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [newProject, setNewProject] = useState({
    name: '',
    description: '',
    product_type: 'agent_skill' as ProductType,
  });

  useEffect(() => {
    loadProjects();
  }, []);

  async function loadProjects() {
    try {
      const data = await api.getMyProjects();
      setProjects(data);
    } catch (err) {
      console.error('加载项目失败:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateProject() {
    try {
      await api.createProject(newProject);
      setIsDialogOpen(false);
      setNewProject({ name: '', description: '', product_type: 'agent_skill' });
      loadProjects();
    } catch (err) {
      console.error('创建项目失败:', err);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">我的项目</h1>
            <p className="mt-2 text-gray-600">管理你的 Agent 项目和投资</p>
          </div>

          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="mr-2 h-4 w-4" />
                创建项目
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>创建新项目</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-4">
                <div>
                  <Label htmlFor="name">项目名称</Label>
                  <Input
                    id="name"
                    value={newProject.name}
                    onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
                    placeholder="输入项目名称"
                  />
                </div>
                <div>
                  <Label htmlFor="description">项目描述</Label>
                  <Input
                    id="description"
                    value={newProject.description}
                    onChange={(e) => setNewProject({ ...newProject, description: e.target.value })}
                    placeholder="描述你的产品或服务"
                  />
                </div>
                <div>
                  <Label htmlFor="type">产品类型</Label>
                  <select
                    id="type"
                    value={newProject.product_type}
                    onChange={(e) => setNewProject({ ...newProject, product_type: e.target.value as ProductType })}
                    className="w-full rounded-md border border-input bg-background px-3 py-2"
                  >
                    <option value="agent_skill">Agent Skill</option>
                    <option value="agent_mcp">MCP 服务</option>
                    <option value="agent_service">Agent 服务</option>
                    <option value="human_web">Web 应用</option>
                    <option value="human_app">移动应用</option>
                  </select>
                </div>
                <Button onClick={handleCreateProject} className="w-full">
                  创建
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>

        {loading ? (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {[...Array(3)].map((_, i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="h-48" />
              </Card>
            ))}
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-lg border">
            <p className="text-gray-500 mb-4">还没有项目</p>
            <Button onClick={() => setIsDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              创建第一个项目
            </Button>
          </div>
        ) : (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {projects.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ProjectCard({ project }: { project: Project }) {
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-lg">{project.name}</CardTitle>
            <CardDescription className="mt-1">{project.description}</CardDescription>
          </div>
          <Badge className={statusColors[project.status]}>
            {statusLabels[project.status]}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex-1">
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600">类型</span>
            <Badge variant="outline">{productTypeLabels[project.product_type]}</Badge>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600 flex items-center gap-1">
              <TrendingUp className="h-4 w-4" />
              估值
            </span>
            <span className="font-medium">{project.valuation?.toFixed(2)} CP</span>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600 flex items-center gap-1">
              <DollarSign className="h-4 w-4" />
              资金池
            </span>
            <span className="font-medium">{project.funding_pool?.toFixed(2)} CP</span>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600 flex items-center gap-1">
              <Users className="h-4 w-4" />
              团队成员
            </span>
            <span className="font-medium">{project.team_members?.length || 1} 人</span>
          </div>

          {(project.product_type === 'agent_skill' ||
            project.product_type === 'agent_mcp' ||
            project.product_type === 'agent_service') && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">使用价格</span>
              <span className="font-medium text-blue-600">
                {project.price_per_use?.toFixed(2) || 0} CP
              </span>
            </div>
          )}

          <div className="pt-3">
            <Button variant="outline" className="w-full">
              管理项目
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
