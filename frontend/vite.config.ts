import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite 配置
// - server.proxy 让 /api/* 转发到后端 uvicorn (127.0.0.1:8765)
//   开发期前端在 5173 端口，请求 /api/auth/login 会被 proxy 改写为 /auth/login 转给后端
//   生产期 Nginx 做同样的事情，前端代码不用改
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
