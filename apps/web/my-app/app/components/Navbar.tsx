'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import { api } from '@/app/lib/api';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import type { User } from '@/app/types';

const navItems = [
  { label: '首页', href: '/' },
  { label: '🏟️ 广场', href: '/plaza' },
  { label: '💬 对话', href: '/chat' },
  { label: '🤖 工作台', href: '/agent' },
  { label: '市场', href: '/marketplace' },
  { label: '项目', href: '/projects' },
];

// ---- Global agent stream (singleton, survives across page navigations) ----
let _globalStreamRunning = false;
let _globalAbort: AbortController | null = null;

function startGlobalAgentStream() {
  if (_globalStreamRunning) return;
  const token = typeof window !== 'undefined' ? localStorage.getItem('clawthon_token') : null;
  if (!token) return;

  _globalStreamRunning = true;
  _globalAbort = new AbortController();
  const controller = _globalAbort;

  window.dispatchEvent(new CustomEvent('agent-status', { detail: { active: true } }));

  const apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').trim();

  (async () => {
    let retries = 0;
    while (_globalStreamRunning) {
      try {
        const response = await fetch(`${apiUrl}/plaza/autonomous-feed`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        retries = 0;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() || '';
          for (const part of parts) {
            const line = part.split('\n').find(l => l.startsWith('data: '));
            if (!line) continue;
            try {
              const evt = JSON.parse(line.slice(6));
              // Broadcast to all pages
              window.dispatchEvent(new CustomEvent('plaza-event', { detail: evt }));
            } catch { /* skip bad JSON */ }
          }
        }
      } catch {
        if (!_globalStreamRunning) break;
      }
      retries++;
      await new Promise(r => setTimeout(r, Math.min(10000, 2000 * retries)));
    }
  })();
}

function stopGlobalAgentStream() {
  _globalStreamRunning = false;
  if (_globalAbort) {
    _globalAbort.abort();
    _globalAbort = null;
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('agent-status', { detail: { active: false } }));
  }
}

export function Navbar() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [agentActive, setAgentActive] = useState(_globalStreamRunning);
  const router = useRouter();
  const pathname = usePathname();

  function checkAuth() {
    const token = api.getToken();
    if (token) {
      setLoading(true);
      api.getMe()
        .then((u) => {
          setUser(u);
          startGlobalAgentStream();
          setAgentActive(true);
        })
        .catch(() => { api.clearToken(); setUser(null); stopGlobalAgentStream(); setAgentActive(false); })
        .finally(() => setLoading(false));
    } else {
      setUser(null);
      setLoading(false);
      stopGlobalAgentStream();
      setAgentActive(false);
    }
  }

  useEffect(() => {
    checkAuth();

    const handleAuthChange = () => checkAuth();
    const handleAgentStatus = (e: Event) => {
      const ce = e as CustomEvent;
      setAgentActive(ce.detail?.active ?? false);
    };
    window.addEventListener('auth-change', handleAuthChange);
    window.addEventListener('storage', handleAuthChange);
    window.addEventListener('agent-status', handleAgentStatus);

    return () => {
      window.removeEventListener('auth-change', handleAuthChange);
      window.removeEventListener('storage', handleAuthChange);
      window.removeEventListener('agent-status', handleAgentStatus);
      // DON'T stop global stream on unmount — it should persist
    };
  }, [pathname]);

  const handleLogout = () => {
    stopGlobalAgentStream();
    api.clearToken();
    setUser(null);
    router.push('/');
  };

  const handleLogin = () => {
    const clientId = process.env.NEXT_PUBLIC_SECONDME_CLIENT_ID || '';
    const redirectUri = `${window.location.origin}/api/auth/callback`;
    const state = Math.random().toString(36).substring(2, 18);
    const authUrl = `https://go.second.me/oauth/?client_id=${clientId}&redirect_uri=${redirectUri}&response_type=code&state=${state}&scope=user.info,chat`;
    window.location.href = authUrl;
  };

  return (
    <nav className="border-b bg-white">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white font-bold">C</div>
          <span className="text-xl font-semibold">Clawthon</span>
        </Link>

        <div className="hidden md:flex items-center gap-6">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`text-sm font-medium transition-colors hover:text-blue-600 ${
                pathname === item.href ? 'text-blue-600' : 'text-gray-600'
              }`}
            >
              {item.label}
            </Link>
          ))}
        </div>

        <div className="flex items-center gap-4">
          {loading ? (
            <div className="h-8 w-8 animate-pulse rounded-full bg-gray-200" />
          ) : user ? (
            <>
              <div className="hidden sm:flex items-center gap-2 text-sm text-gray-600">
                {agentActive && (
                  <span className="flex items-center gap-1 text-xs text-green-600" title="Agent 自治运行中">
                    <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                    活跃
                  </span>
                )}
                <span>CP:</span>
                <span className="font-semibold text-blue-600">{user.budget.toFixed(0)}</span>
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="relative h-8 w-8 rounded-full">
                    <Avatar className="h-8 w-8">
                      <AvatarImage src={user.avatar} alt={user.name} />
                      <AvatarFallback>{user.name?.[0] || 'U'}</AvatarFallback>
                    </Avatar>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <div className="flex items-center gap-2 p-2">
                    <Avatar className="h-8 w-8">
                      <AvatarImage src={user.avatar} alt={user.name} />
                      <AvatarFallback>{user.name?.[0] || 'U'}</AvatarFallback>
                    </Avatar>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">{user.name}</span>
                      <span className="text-xs text-gray-500">{user.email}</span>
                    </div>
                  </div>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => router.push('/dashboard')}>Dashboard</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => router.push('/projects')}>我的项目</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => router.push('/settings')}>设置</DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout} className="text-red-600">退出登录</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          ) : (
            <Button onClick={handleLogin}>使用 SecondMe 登录</Button>
          )}
        </div>
      </div>
    </nav>
  );
}
