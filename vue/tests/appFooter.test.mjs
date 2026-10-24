import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const footerSource = await readFile(
  new URL('../src/components/AppFooter.vue', import.meta.url),
  'utf8',
)
const appSource = await readFile(new URL('../src/App.vue', import.meta.url), 'utf8')

test('renders the copyright, ICP and public security records in the global footer', () => {
  assert.match(footerSource, /© 2026 iKnowread开发团队/)
  assert.match(footerSource, /赣ICP备2026027332号-1/)
  assert.match(footerSource, /href="https:\/\/beian\.miit\.gov\.cn\/"/)
  assert.match(footerSource, /赣公网安备36073202361022号/)
  assert.match(footerSource, /href="https:\/\/beian\.mps\.gov\.cn\/#\/query\/webSearch\?code=36073202361022"/)
  assert.match(footerSource, /public-security-record\.png/)
  assert.match(footerSource, /target="_blank"/)
  assert.match(footerSource, /rel="noopener noreferrer"/)
  assert.match(appSource, /<AppFooter\s*\/>/)
})
