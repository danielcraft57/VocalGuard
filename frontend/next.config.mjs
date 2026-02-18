/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    appDir: true
  },
  /**
   * On prépare un export statique:
   * - `next build` génère un dossier `out/`
   * - le contenu de `out/` sera copié dans `backend/web`
   */
  output: "export",
  images: {
    unoptimized: true
  }
};

export default nextConfig;

