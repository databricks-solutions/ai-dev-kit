import path from "path";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'out',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;

          if (
            id.includes("react-syntax-highlighter") ||
            id.includes("highlight.js") ||
            id.includes("lowlight") ||
            id.includes("refractor") ||
            id.includes("prismjs")
          ) {
            return "vendor-syntax";
          }
          if (
            id.includes("react-markdown") ||
            id.includes("remark-gfm") ||
            id.includes("/remark-") ||
            id.includes("/rehype-") ||
            id.includes("/micromark") ||
            id.includes("/mdast") ||
            id.includes("/hast") ||
            id.includes("/unist") ||
            id.includes("/unified") ||
            id.includes("/vfile")
          ) {
            return "vendor-markdown";
          }
          if (
            id.includes("/react-router-dom/") ||
            id.includes("/react-router/") ||
            id.includes("/history/")
          ) {
            return "vendor-router";
          }
          if (
            id.includes("/react-dom/") ||
            id.includes("/react/") ||
            id.includes("/scheduler/")
          ) {
            return "vendor-react";
          }
          if (id.includes("lucide-react") || id.includes("sonner")) return "vendor-ui";

          return "vendor-misc";
        },
      },
    },
  },
});
