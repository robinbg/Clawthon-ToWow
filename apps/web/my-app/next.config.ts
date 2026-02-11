import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(__dirname),
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'https://clawthon-towow-api.vercel.app',
    NEXT_PUBLIC_SECONDME_CLIENT_ID: 'ec10c408-6095-4e0b-b1a4-5af3cb6f0321',
  },
};

export default nextConfig;
