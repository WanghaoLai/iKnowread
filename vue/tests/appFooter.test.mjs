import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const footerSource = await readFile(
  new URL('../src/components/AppFooter.vue', import.meta.url),
  'utf8',
)
const appSource = await readFile(new URL('../src/App.vue', import.meta.url), 'utf8')

test('renders the required ICP record as a safe MIIT link in the global footer', () => {
  assert.match(footerSource, /© 2026 iKnowread开发团队/)
  assert.match(footerSource, /赣ICP备2026027332号-1/)
  assert.match(footerSource, /href="https:\/\/beian\.miit\.gov\.cn\/"/)
  assert.match(footerSource, /target="_blank"/)
  assert.match(footerSource, /rel="noopener noreferrer"/)
  assert.match(appSource, /<AppFooter\s*\/>/)
})
