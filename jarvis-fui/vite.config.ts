import { defineConfig } from 'vite'

export default defineConfig({
  base: './',
  build: {
    target: 'es2020',
    cssCodeSplit: false,
    chunkSizeWarningLimit: 900,
  },
  server: { port: 5173, host: true },
})
