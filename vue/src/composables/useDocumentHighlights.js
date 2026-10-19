import { reactive, ref } from 'vue'

const emptyDetail = () => ({
  visible: false,
  item: null,
  editing: false,
  remark: '',
  saving: false,
  left: 12,
  top: 12,
  anchorRect: null,
})

const emptySelection = () => ({
  open: false,
  remark: '',
  remarkTouched: false,
  saving: false,
  saved: false,
  id: null,
})

/**
 * Owns every client-side reference to a saved highlight.
 *
 * Keeping these transitions here prevents the list, detail card, selection
 * composer and resolved DOM ranges from drifting apart after a mutation.
 */
export const useDocumentHighlights = () => {
  const highlights = ref([])
  const highlightManager = reactive({ open: false, loading: false })
  const highlightDetail = reactive(emptyDetail())
  const selectionHighlight = reactive(emptySelection())
  let resolvedRanges = []

  const closeDetail = () => Object.assign(highlightDetail, emptyDetail())
  const resetSelection = () => Object.assign(selectionHighlight, emptySelection())

  const replaceAll = items => {
    highlights.value = Array.isArray(items) ? items : []
    resolvedRanges = []
    if (
      highlightDetail.item
      && !highlights.value.some(item => item.id === highlightDetail.item.id)
    ) closeDetail()
    if (
      selectionHighlight.id
      && !highlights.value.some(item => item.id === selectionHighlight.id)
    ) resetSelection()
  }

  const clear = () => {
    highlights.value = []
    highlightManager.open = false
    highlightManager.loading = false
    resolvedRanges = []
    closeDetail()
    resetSelection()
  }

  const openDetail = (item, anchorRect, { edit = false } = {}) => {
    if (!item) return
    Object.assign(highlightDetail, {
      visible: true,
      item,
      editing: edit,
      remark: item.remark || '',
      saving: false,
      anchorRect,
    })
  }

  const beginDetailEdit = () => {
    if (!highlightDetail.item) return
    highlightDetail.remark = highlightDetail.item.remark || ''
    highlightDetail.editing = true
  }

  const upsert = (item, { selected = false } = {}) => {
    if (!item) return
    highlights.value = [item, ...highlights.value.filter(entry => entry.id !== item.id)]
    if (highlightDetail.item?.id === item.id) {
      highlightDetail.item = item
      highlightDetail.remark = item.remark || ''
    }
    if (selected) {
      Object.assign(selectionHighlight, {
        open: false,
        remark: item.remark || '',
        saving: false,
        saved: true,
        id: item.id,
      })
    }
  }

  const removeLocal = id => {
    highlights.value = highlights.value.filter(item => item.id !== id)
    resolvedRanges = resolvedRanges.filter(entry => entry.item.id !== id)
    if (highlightDetail.item?.id === id) closeDetail()
    if (selectionHighlight.id === id) resetSelection()
  }

  const setResolvedRanges = entries => {
    resolvedRanges = Array.isArray(entries) ? entries : []
  }

  const clearResolvedRanges = () => { resolvedRanges = [] }
  const rangeFor = item => resolvedRanges.find(entry => entry.item.id === item?.id)?.range
  const findResolved = predicate => [...resolvedRanges].reverse().find(predicate)

  return {
    highlights,
    highlightManager,
    highlightDetail,
    selectionHighlight,
    replaceAll,
    clear,
    openDetail,
    closeDetail,
    beginDetailEdit,
    resetSelection,
    upsert,
    removeLocal,
    setResolvedRanges,
    clearResolvedRanges,
    rangeFor,
    findResolved,
  }
}
