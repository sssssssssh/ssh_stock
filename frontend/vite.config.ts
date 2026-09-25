import vue from "@vitejs/plugin-vue";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:9034";

  return {
    plugins: [vue()],
    test: {
      environment: "happy-dom",
      coverage: {
        provider: "v8",
        include: [
          "src/services/**/*.ts",
          "src/utils/**/*.ts",
          "src/components/{ResearchLab,LoginView,JobCenter}.vue"
        ],
        thresholds: {
          statements: 20,
          lines: 20,
          functions: 20,
          branches: 10
        }
      }
    },
    build: {
      chunkSizeWarningLimit: 700
    },
    server: {
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true
        }
      }
    }
  };
});
