/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['@agroamigo/shared'],
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'images.unsplash.com' },
      { protocol: 'https', hostname: 'pnpxowiqulmuumldtmfg.supabase.co' },
    ],
  },
};

export default nextConfig;
