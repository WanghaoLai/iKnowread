import assert from 'node:assert/strict'
import test from 'node:test'

import { usePdfRenderer } from '../src/composables/usePdfRenderer.js'

const ref = value => ({ value })

const deferred = () => {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

const renderTask = () => ({
  promise: Promise.resolve(),
  cancel() {},
})

test('a delayed old PDF page cannot overwrite the latest paged render', async () => {
  const previousWindow = globalThis.window
  globalThis.window = { devicePixelRatio: 1 }
  try {
    const first = deferred()
    const second = deferred()
    const requestedPages = []
    const renderedPages = []
    const documentProxy = {
      async getPage(pageNumber) {
        requestedPages.push(pageNumber)
        return pageNumber === 1 ? first.promise : second.promise
      },
    }
    const page = pageNumber => ({
      getViewport: ({ scale }) => ({ width: 600 * scale, height: 800 * scale }),
      render() {
        renderedPages.push(pageNumber)
        return renderTask()
      },
      streamTextContent: () => ({ pageNumber }),
    })
    const canvas = {
      style: {},
      getContext: () => ({}),
    }
    const surface = { style: {} }
    const layer = {
      replacements: 0,
      replaceChildren() { this.replacements += 1 },
    }
    const pageNum = ref(1)
    const selectableTextCount = ref(0)
    let textRendered = 0
    const renderer = usePdfRenderer({
      pdfDoc: ref(documentProxy),
      pageNum,
      numPages: ref(2),
      zoom: ref(1),
      readingMode: ref('paged'),
      loading: ref(false),
      loadingText: ref(''),
      selectableTextCount,
      continuousRenderedCount: ref(0),
      bodyRef: ref(null),
      canvasRef: ref(canvas),
      pageSurfaceRef: ref(surface),
      textLayerRef: ref(layer),
      continuousRef: ref(null),
      onTextRendered: () => { textRendered += 1 },
      createTextLayer: ({ textContentSource }) => ({
        textContentItemsStr: [`page-${textContentSource.pageNumber}`],
        render: async () => {},
        cancel() {},
      }),
    })

    const oldRender = renderer.renderPage()
    await Promise.resolve()
    assert.deepEqual(requestedPages, [1])

    pageNum.value = 2
    const latestRender = renderer.renderPage()
    await Promise.resolve()
    assert.deepEqual(requestedPages, [1, 2])

    second.resolve(page(2))
    await latestRender
    first.resolve(page(1))
    await oldRender

    assert.deepEqual(renderedPages, [2])
    assert.equal(layer.replacements, 1)
    assert.equal(selectableTextCount.value, 'page-2'.length)
    assert.equal(textRendered, 1)
    assert.equal(canvas.style.width, '600px')
  } finally {
    if (previousWindow === undefined) delete globalThis.window
    else globalThis.window = previousWindow
  }
})
