import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/metadata': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      // /chat API is POST-only; browser navigation (GET /chat) must
      // fall through to the SPA.  Keeping the proxy is safe because
      // browsers never POST on direct URL navigation, but we can also
      // leave it — Vite proxies all methods.  Keeping it for fetch().
      '/chat': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // Only proxy if the request is NOT a browser navigation (HTML)
        bypass(req) {
          if (req.headers.accept?.includes('text/html')) {
            return req.url;          // serve index.html (SPA)
          }
        }
      },
      '/sessions': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/diagnostics': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      // Only proxy the actual API sub-routes; GET /network itself is
      // a frontend SPA route and must not be forwarded to FastAPI.
      '/network/map': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/network/agent': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true
      }
    }
  }
})
