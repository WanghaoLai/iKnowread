import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
// 导入对应包

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
  ],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          minSize: 30 * 1024,
          maxSize: 450 * 1024,
          groups: [
            { name: 'pdfjs', test: /node_modules[\\/]pdfjs-dist/, priority: 5 },
            { name: 'element-plus', test: /node_modules[\\/](?:element-plus|@element-plus)/, priority: 4 },
            { name: 'docx', test: /node_modules[\\/](?:docx-preview|jszip)/, priority: 3 },
            { name: 'vue', test: /node_modules[\\/](?:vue|@vue|vue-router)/, priority: 2 },
          ],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:9090',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  }
})
