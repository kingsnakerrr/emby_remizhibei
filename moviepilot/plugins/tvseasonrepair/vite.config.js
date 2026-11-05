import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'TVSeasonRepair',
      filename: 'remoteEntry.js',
      exposes: { './Page': './src/components/Page.vue' },
      shared: { vue: { requiredVersion: false, generate: false } },
      format: 'esm',
    }),
  ],
  build: { target: 'esnext', minify: false, cssCodeSplit: true },
  css: {
    postcss: {
      plugins: [{
        postcssPlugin: 'vuetify-filter',
        Root(root) {
          root.walkRules(rule => {
            if (rule.selector && (rule.selector.includes('.v-') || rule.selector.includes('.mdi-'))) rule.remove()
          })
        },
      }],
    },
  },
})
