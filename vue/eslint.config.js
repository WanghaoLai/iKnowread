import globals from 'globals'
import pluginVue from 'eslint-plugin-vue'

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  ...pluginVue.configs['flat/essential'],
  {
    files: ['src/**/*.{js,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: globals.browser,
    },
    rules: {
      'vue/multi-word-component-names': 'off',
      'no-constant-binary-expression': 'error',
      'no-dupe-else-if': 'error',
      'no-dupe-keys': 'error',
      'no-func-assign': 'error',
      'no-import-assign': 'error',
      'no-obj-calls': 'error',
      'no-redeclare': 'error',
      'no-unreachable': 'error',
      'no-unsafe-finally': 'error',
      'no-undef': 'error',
    },
  },
  {
    files: ['tests/**/*.mjs'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: globals.node,
    },
    rules: {
      'no-dupe-keys': 'error',
      'no-redeclare': 'error',
      'no-unreachable': 'error',
      'no-undef': 'error',
    },
  },
]
