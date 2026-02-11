import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get('code');

  if (!code) {
    return NextResponse.redirect(new URL('/?error=no_code', request.url));
  }

  try {
    // 将 code 发送到后端进行验证（trim 防止环境变量有换行）
    const apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').trim();
    console.log('[OAuth] Calling backend:', `${apiUrl}/auth/callback`);

    const response = await fetch(
      `${apiUrl}/auth/callback`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      }
    );

    const responseText = await response.text();
    console.log('[OAuth] Backend response status:', response.status);
    console.log('[OAuth] Backend response body:', responseText.substring(0, 500));

    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}: ${responseText.substring(0, 200)}`);
    }

    const data = JSON.parse(responseText);

    if (!data.access_token) {
      throw new Error('No access_token in response');
    }

    // 通过 query param 传递 token 给客户端，客户端会存到 localStorage
    const redirectUrl = new URL('/dashboard', request.url);
    redirectUrl.searchParams.set('token', data.access_token);

    return NextResponse.redirect(redirectUrl);
  } catch (error) {
    console.error('[OAuth] Callback error:', error);
    return NextResponse.redirect(new URL('/?error=auth_failed', request.url));
  }
}
