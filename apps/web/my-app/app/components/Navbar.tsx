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

export function Navbar() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [agentActive, setAgentActive] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const bgAbortRef = useRef<AbortController | null>(null);

  // 加载用户信息
  function checkAuth() {
    const token = api.getToken();
    if (token) {
      setLoading(true);
      api.getMe()
        .then((u) => {
          setUser(u);
          // Start background agent activity when logged in
          startBackgroundAgent();
        })
        .catch(() => { api.clearToken(); setUser(null); stopBackgroundAgent(); })
        .finally(() => setLoading(false));
    } else {
      setUser(null);
      setLoading(false);
      stopBackgroundAgent();
    }
  }

  function stopBackgroundAgent() {
    if (bgAbortRef.current) {
      bgAbortRef.current.abort();
      bgAbortRef.current = null;
    }
    setAgentActive(false);
  }

  function startBackgroundAgent() {
    // Don't start if already running or if we're on the plaza page (plaza manages its own stream)
    if (bgAbortRef.current || pathname === '/plaza') return;
    const token = api.getToken();
    if (!token) return;

    const controller = new AbortController();
    bgAbortRef.current = controller;
    setAgentActive(true);

    const apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').trim();
    fetch(`${apiUrl}/plaza/autonomous-feed`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok || !response.body) return;
      const reader = response.body.getReader();
      // Just consume the stream silently to keep agent active
      while (true) {
        const { done } = await reader.read();
        if (done) break;
      }
    }).catch(() => {
      // silently ignore — stream will reconnect on next auth check
    }).finally(() => {
      if (bgAbortRef.current === controller) {
        bgAbortRef.current = null;
        setAgentActive(false);
      }
    });
  }

  useEffect(() => {
    checkAuth();

    // 监听 token 变化（Dashboard 存完 token 后会触发）
    const handleAuthChange = () => checkAuth();
    window.addEventListener('auth-change', handleAuthChange);
    window.addEventListener('storage', handleAuthChange);

    // 每次路由变化也检查一次
    return () => {
      window.removeEventListener('auth-change', handleAuthChange);
      window.removeEventListener('storage', handleAuthChange);
      stopBackgroundAgent();
    };
  }, [pathname]); // pathname 变化时重新检查

  const handleLogout = () => {
    api.clearToken();
    setUser(null);
    router.push('/');
  };

  const handleLogin = () => {
    const clientId = process.env.NEXT_PUBLIC_SECONDME_CLIENT_ID || '';
    const redirectUri = `${window.location.origin}/api/auth/callback`;
    const state = Math.random().toString(36).substring(2, 18);
    // SecondMe OAuth: https://go.second.me/oauth/
    // SecondMe 要求 redirect_uri 不编码（编码后返回 Application not found）
    // scope: user.info(用户信息) + chat(对话能力)
    const authUrl = `https://go.second.me/oauth/?client_id=${clientId}&redirect_uri=${redirectUri}&response_type=code&state=${state}&scope=user.info,chat`;
    window.location.href = authUrl;
  };

  return (
    <nav className="border-b bg-white">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white font-bold">
            C
          </div>
          <span className="text-xl font-semibold">Clawthon</span>
        </Link>

        {/* Navigation */}
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

        {/* User Menu */}
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
                  <DropdownMenuItem onClick={() => router.push('/dashboard')}>
                    Dashboard
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => router.push('/projects')}>
                    我的项目
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => router.push('/settings')}>
                    设置
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout} className="text-red-600">
                    退出登录
                  </DropdownMenuItem>
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
