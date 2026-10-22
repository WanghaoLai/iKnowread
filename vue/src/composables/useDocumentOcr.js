import { computed, ref } from 'vue'

export const buildVersionedDocumentUrl = (url, version, derivedRevision = '') => {
  const parameters = []
  if (version) parameters.push(`version=${encodeURIComponent(version)}`)
  if (derivedRevision) parameters.push(`revision=${encodeURIComponent(derivedRevision)}`)
  if (!parameters.length) return url
  return `${url}${url.includes('?') ? '&' : '?'}${parameters.join('&')}`
}

export const useDocumentOcr = ({
  getModel,
  reload,
  notifyReady = () => {},
  pollDelay = 2500,
  fetchStatus,
  requestRetry,
  notifyRetryError = (_error) => {},
}) => {
  if (typeof fetchStatus !== 'function' || typeof requestRetry !== 'function') {
    throw new TypeError('OCR status and retry transports are required')
  }
  const initial = getModel()
  const activeUrl = ref(buildVersionedDocumentUrl(
    initial.url,
    initial.contentVersion || '',
    initial.ocrUpdatedAt || '',
  ))
  const contentVersion = ref(initial.contentVersion || '')
  const ocrStatus = ref(initial.ocrStatus || 'not_applicable')
  const ocrError = ref(initial.ocrError || '')
  const ocrUpdatedAt = ref(initial.ocrUpdatedAt || '')
  const ocrRetrying = ref(false)
  const ocrBusy = computed(() => ['pending', 'processing'].includes(ocrStatus.value))
  const ocrDisabled = computed(() => ocrError.value === 'OCR 服务未启用')
  let timer = null
  let generation = 0

  const stop = () => {
    generation += 1
    clearTimeout(timer)
    timer = null
  }

  const schedule = () => {
    clearTimeout(timer)
    timer = null
    if (ocrBusy.value) timer = setTimeout(refresh, pollDelay)
  }

  const refresh = async () => {
    const expectedGeneration = generation
    try {
      const response = await fetchStatus(getModel().id)
      if (expectedGeneration !== generation) return
      const doc = response.data || {}
      const previousStatus = ocrStatus.value
      const previousVersion = contentVersion.value
      const previousRevision = ocrUpdatedAt.value
      ocrStatus.value = doc.ocr_status || previousStatus
      ocrError.value = doc.ocr_error || ''
      ocrUpdatedAt.value = doc.ocr_updated_at || previousRevision
      const contentChanged = doc.content_version && doc.content_version !== previousVersion
      const derivativeChanged = ocrStatus.value === 'ready' && (
        previousStatus !== 'ready' || ocrUpdatedAt.value !== previousRevision
      )
      if (contentChanged || derivativeChanged) {
        contentVersion.value = doc.content_version || previousVersion
        activeUrl.value = buildVersionedDocumentUrl(
          getModel().url,
          contentVersion.value,
          ocrUpdatedAt.value,
        )
        await reload()
        notifyReady()
      }
    } catch (_) {
      // A failed status request must not create an endless stream of errors.
      stop()
      return
    }
    schedule()
  }

  const retry = async () => {
    if (ocrRetrying.value) return
    ocrRetrying.value = true
    try {
      const response = await requestRetry(getModel().id)
      ocrStatus.value = response.data?.ocr_status || 'pending'
      ocrError.value = ''
      schedule()
    } catch (error) {
      await notifyRetryError(error)
    } finally {
      ocrRetrying.value = false
    }
  }

  const sync = model => {
    stop()
    contentVersion.value = model.contentVersion || ''
    ocrStatus.value = model.ocrStatus || 'not_applicable'
    ocrError.value = model.ocrError || ''
    ocrUpdatedAt.value = model.ocrUpdatedAt || ''
    activeUrl.value = buildVersionedDocumentUrl(
      model.url,
      contentVersion.value,
      ocrUpdatedAt.value,
    )
    schedule()
  }

  return {
    activeUrl,
    contentVersion,
    ocrStatus,
    ocrError,
    ocrUpdatedAt,
    ocrRetrying,
    ocrBusy,
    ocrDisabled,
    refresh,
    retry,
    sync,
    stop,
  }
}
