let pdfEnginePromise
let docxRendererPromise

export const loadPdfEngine = () => {
  pdfEnginePromise ||= Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?worker'),
  ]).then(([pdfjs, workerModule]) => {
    pdfjs.GlobalWorkerOptions.workerPort ||= new workerModule.default()
    return pdfjs
  })
  return pdfEnginePromise
}

export const loadDocxRenderer = () => {
  docxRendererPromise ||= import('docx-preview').then(module => module.renderAsync)
  return docxRendererPromise
}
