/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['@agroamigo/shared'],
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'images.unsplash.com' },
      { protocol: 'https', hostname: 'iznyrnsuqdmkuhtsrxor.supabase.co' },
    ],
  },
};

export default nextConfig;
