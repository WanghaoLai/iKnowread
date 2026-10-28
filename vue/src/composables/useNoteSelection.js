import { computed, ref } from 'vue'

export function useNoteSelection(notes) {
  const selectionMode = ref(false)
  const selectedNoteIds = ref(new Set())
  const selectedCount = computed(() => selectedNoteIds.value.size)
  const currentPageAllSelected = computed(() => (
    notes.value.length > 0 && notes.value.every(note => selectedNoteIds.value.has(note.id))
  ))

  const toggleNoteSelection = (id, checked = !selectedNoteIds.value.has(id)) => {
    const next = new Set(selectedNoteIds.value)
    if (checked) next.add(id)
    else next.delete(id)
    selectedNoteIds.value = next
  }

  const startBatchSelection = () => {
    if (selectionMode.value) return
    selectionMode.value = true
    selectedNoteIds.value = new Set()
  }

  const cancelBatchSelection = () => {
    selectionMode.value = false
    selectedNoteIds.value = new Set()
  }

  const toggleCurrentPageSelection = () => {
    const next = new Set(selectedNoteIds.value)
    if (currentPageAllSelected.value) notes.value.forEach(note => next.delete(note.id))
    else notes.value.forEach(note => next.add(note.id))
    selectedNoteIds.value = next
  }

  return {
    selectionMode,
    selectedNoteIds,
    selectedCount,
    currentPageAllSelected,
    toggleNoteSelection,
    startBatchSelection,
    cancelBatchSelection,
    toggleCurrentPageSelection,
  }
}
