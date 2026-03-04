/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow images from any backend origin
  images: { unoptimized: true },
};

module.exports = nextConfig;
