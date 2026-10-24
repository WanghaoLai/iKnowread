import { createPointAnchor, loadReadingProgress, saveReadingProgress } from '../utils/sourceAnchor.js'

export const useReadingProgress = ({
  getSourceModel,
  getSourceFormat,
  getPage,
  getPageCount,
  getReadingMode,
  getScrollElement,
  saveRemote = null,
  delay = 250,
  remoteDelay = 1200,
}) => {
  let timer = null
  let remoteTimer = null

  const scrollProgression = () => {
    const element = getScrollElement()
    if (!element) return 0
    const maximum = element.scrollHeight - element.clientHeight
    return maximum > 0 ? element.scrollTop / maximum : 0
  }

  const currentAnchor = () => createPointAnchor(getSourceModel(), {
    page: getSourceFormat() === 'pdf' ? getPage() : null,
    progression: getReadingMode() === 'paged' && getSourceFormat() === 'pdf'
      ? (getPageCount() > 1 ? (getPage() - 1) / (getPageCount() - 1) : 0)
      : scrollProgression(),
  })

  const cancel = () => {
    clearTimeout(timer)
    clearTimeout(remoteTimer)
    timer = null
    remoteTimer = null
  }

  const syncRemote = anchor => {
    if (!saveRemote || !anchor) return
    Promise.resolve(saveRemote(anchor)).catch(() => {})
  }

  const scheduleRemote = anchor => {
    if (!saveRemote) return
    clearTimeout(remoteTimer)
    remoteTimer = setTimeout(() => {
      remoteTimer = null
      syncRemote(anchor)
    }, remoteDelay)
  }

  const persist = () => {
    cancel()
    timer = setTimeout(() => {
      timer = null
      const anchor = currentAnchor()
      if (anchor) {
        saveReadingProgress(anchor)
        scheduleRemote(anchor)
      }
    }, delay)
  }

  const flush = () => {
    cancel()
    const anchor = currentAnchor()
    if (anchor) {
      saveReadingProgress(anchor)
      syncRemote(anchor)
    }
    return anchor
  }

  const load = () => loadReadingProgress(getSourceModel())

  return { scrollProgression, currentAnchor, persist, flush, load, cancel }
}
