<template>
  <section class="notes-page">
    <header class="notes-heading">
      <div>
        <h1>我的笔记</h1>
        <p>收纳阅读时的重要解释和思考，随时整理、检索与导出。</p>
      </div>
      <div class="heading-actions">
        <div class="note-total"><strong>{{ summary.total }}</strong><span>条笔记</span></div>
        <el-dropdown :disabled="exporting || !summary.total" @command="handleExportCommand">
          <el-button :icon="Download" :loading="exporting" :disabled="!summary.total">
            导出笔记<el-icon class="export-arrow"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="document">按文档导出</el-dropdown-item>
              <el-dropdown-item command="selected">批量导出</el-dropdown-item>
              <el-dropdown-item command="all" divided>全量导出</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建笔记</el-button>
      </div>
    </header>

    <div class="notes-filter card">
      <el-input
          v-model="keyword"
          class="keyword-input"
          clearable
          :prefix-icon="Search"
          placeholder="搜索标题、选文、解释或备注"
          aria-label="搜索笔记"
          @input="scheduleLoad"
          @clear="resetPageAndLoad"
          @keyup.enter="resetPageAndLoad"
      />
      <el-select v-model="documentId" clearable class="document-filter" placeholder="全部文档" aria-label="按来源文档筛选" @change="resetPageAndLoad">
        <el-option v-for="item in summary.documents" :key="`${item.document_id ?? 'none'}-${item.document_name ?? ''}`" :label="`${groupLabel(item)}（${item.count}）`" :value="groupValue(item)" />
      </el-select>
      <el-radio-group v-model="viewMode" aria-label="笔记编排方式" @change="resetPageAndLoad">
        <el-radio-button value="timeline">按时间</el-radio-button>
        <el-radio-button value="document">按文档</el-radio-button>
      </el-radio-group>
      <el-select v-if="viewMode === 'timeline'" v-model="timeSort" class="sort-select" aria-label="时间排序" @change="resetPageAndLoad">
        <el-option label="最新在前" value="newest" />
        <el-option label="最早在前" value="oldest" />
      </el-select>
    </div>

    <div v-if="selectionMode" class="selection-toolbar card" aria-live="polite">
      <div>
        <strong>批量导出</strong>
        <span>已选择 {{ selectedCount }} 条，翻页后仍会保留选择</span>
      </div>
      <div class="selection-actions">
        <el-button text @click="toggleCurrentPageSelection">{{ currentPageAllSelected ? '取消本页' : '选择本页' }}</el-button>
        <el-button @click="cancelBatchSelection">取消</el-button>
        <el-button type="primary" :icon="Download" :loading="exporting" :disabled="!selectedCount" @click="exportSelectedNotes">
          导出选中
        </el-button>
      </div>
    </div>

    <div v-loading="loading" class="notes-content" aria-live="polite">
      <el-empty v-if="!loading && !notes.length" :description="keyword || documentId !== null ? '没有匹配的笔记' : '还没有笔记，阅读划词或手动记录一条吧'">
        <el-button v-if="!keyword && documentId === null" type="primary" @click="openCreate">新建第一条笔记</el-button>
      </el-empty>

      <section v-for="group in displayGroups" :key="group.key" class="note-group">
        <header v-if="viewMode === 'document'" class="group-heading">
          <div><el-icon><FolderOpened /></el-icon><h2>{{ group.name }}</h2></div>
          <span>本页 {{ group.items.length }} 条</span>
        </header>
        <div class="notes-grid">
          <article
              v-for="note in group.items"
              :key="note.id"
              class="note-card card"
              :class="{ selected: selectionMode && selectedNoteIds.has(note.id) }"
              role="button"
              tabindex="0"
              :aria-label="selectionMode ? `选择笔记：${note.title}` : `查看笔记：${note.title}`"
              :aria-pressed="selectionMode ? selectedNoteIds.has(note.id) : undefined"
              @click="handleCardClick(note)"
              @keydown.enter.self="handleCardClick(note)"
              @keydown.space.prevent.self="handleCardClick(note)"
          >
            <div v-if="selectionMode" class="note-selection-row" @click.stop>
              <el-checkbox
                  :model-value="selectedNoteIds.has(note.id)"
                  :aria-label="`选择笔记：${note.title}`"
                  @change="checked => toggleNoteSelection(note.id, checked)"
              >选择</el-checkbox>
            </div>
            <header class="note-card-heading">
              <div class="note-document-line">
                <span class="document-name" :title="note.document_name || '未关联文档'">{{ note.document_name || '未关联文档' }}</span>
                <el-tag size="small" effect="light" :type="documentStatus(note).type">
                  {{ documentStatus(note).label }}
                </el-tag>
              </div>
              <div v-if="!selectionMode" class="note-card-actions" @click.stop>
                <button
                    v-if="note.source_anchor && note.document_status === 'available'"
                    type="button"
                    class="source-link"
                    @click="locateSource(note)"
                ><el-icon><Location /></el-icon>定位原文</button>
                <el-dropdown trigger="click" @command="command => handleCardCommand(command, note)">
                  <button type="button" class="more-button" aria-label="笔记操作"><el-icon><MoreFilled /></el-icon></button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="edit" :icon="EditPen">编辑笔记</el-dropdown-item>
                      <el-dropdown-item command="delete" :icon="Delete" divided>删除笔记</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
              <div class="note-secondary-tags">
                <el-tag size="small" effect="plain" :type="note.source_type === 'ai_explanation' ? 'success' : 'info'">
                  {{ note.source_type === 'ai_explanation' ? 'AI 划词' : '手动笔记' }}
                </el-tag>
                <el-tag v-if="note.document_version" size="small" effect="plain" type="info" :title="`文档内容版本：${note.document_version}`">
                  v{{ note.document_version.slice(0, 8) }}
                </el-tag>
              </div>
            </header>

            <h3>{{ note.title }}</h3>
            <blockquote v-if="note.selected_text" class="selected-text">{{ note.selected_text }}</blockquote>
            <div class="note-content clamped">{{ note.content }}</div>
            <div v-if="note.remark" class="note-remark note-remark-compact">
              <span>我的备注</span>
              <p>{{ note.remark }}</p>
            </div>
            <footer class="note-meta">
              <div class="note-meta-info">
                <span>{{ formatTime(note.created_at) }}</span>
                <span v-if="note.model" :title="sourceLabel(note)">{{ sourceLabel(note) }}</span>
              </div>
              <span class="card-preview-hint"><el-icon><FullScreen /></el-icon>放大查看</span>
            </footer>
          </article>
        </div>
      </section>
    </div>

    <el-pagination
        v-if="total > pageSize"
        v-model:current-page="pageNum"
        v-model:page-size="pageSize"
        class="notes-pagination"
        background
        layout="total, sizes, prev, pager, next"
        :page-sizes="[12, 24, 48]"
        :total="total"
        @current-change="loadNotes"
        @size-change="resetPageAndLoad"
    />

    <el-dialog v-model="exportDocumentVisible" title="按文档导出" width="min(500px, calc(100vw - 24px))" destroy-on-close>
      <div class="document-export-dialog">
        <p>选择一个来源文档，将导出该文档下的全部笔记，不受页面搜索和筛选条件影响。</p>
        <el-select v-model="exportDocumentValue" filterable placeholder="选择来源文档" style="width: 100%">
          <el-option
              v-for="item in summary.documents"
              :key="`export-${item.document_id ?? 'none'}-${item.document_name ?? ''}`"
              :label="`${groupLabel(item)}（${item.count} 条）`"
              :value="groupValue(item)"
          />
        </el-select>
      </div>
      <template #footer>
        <el-button @click="exportDocumentVisible = false">取消</el-button>
        <el-button type="primary" :icon="Download" :loading="exporting" :disabled="exportDocumentValue === null" @click="exportDocumentNotes">
          导出该文档
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="笔记详情" width="min(760px, calc(100vw - 24px))" destroy-on-close class="note-preview-dialog">
      <article v-if="previewNote" class="note-detail">
        <header class="note-detail-heading">
          <div class="note-detail-tags">
            <el-tag effect="plain" :type="previewNote.source_type === 'ai_explanation' ? 'success' : 'info'">
              {{ previewNote.source_type === 'ai_explanation' ? 'AI 划词' : '手动笔记' }}
            </el-tag>
            <span class="detail-document-name">{{ previewNote.document_name || '未关联文档' }}</span>
            <el-tag effect="light" :type="documentStatus(previewNote).type">{{ documentStatus(previewNote).label }}</el-tag>
            <el-tag v-if="previewNote.document_version" effect="plain" type="info" :title="`文档内容版本：${previewNote.document_version}`">
              v{{ previewNote.document_version.slice(0, 8) }}
            </el-tag>
          </div>
          <div class="note-detail-actions">
            <el-button
                v-if="previewNote.source_anchor && previewNote.document_status === 'available'"
                type="primary"
                plain
                :icon="Location"
                @click="locateSource(previewNote)"
            >定位原文</el-button>
            <el-button :icon="EditPen" @click="openEdit(previewNote)">编辑</el-button>
            <el-button type="danger" plain :icon="Delete" @click="deletePreviewNote">删除</el-button>
          </div>
        </header>
        <h2>{{ previewNote.title }}</h2>
        <section v-if="previewNote.selected_text" class="note-detail-section">
          <strong>选中文字</strong>
          <blockquote>{{ previewNote.selected_text }}</blockquote>
        </section>
        <section class="note-detail-section">
          <strong>{{ previewNote.source_type === 'ai_explanation' ? 'AI 解释' : '笔记内容' }}</strong>
          <div class="note-detail-content">{{ previewNote.content }}</div>
        </section>
        <section v-if="previewNote.remark" class="note-detail-section note-detail-remark">
          <strong>我的备注</strong>
          <div>{{ previewNote.remark }}</div>
        </section>
        <footer class="note-detail-meta">
          <span>创建于 {{ formatTime(previewNote.created_at) }}</span>
          <span v-if="previewNote.model">{{ sourceLabel(previewNote) }}</span>
        </footer>
      </article>
    </el-dialog>

    <el-dialog v-model="editorVisible" :title="form.id ? '编辑笔记' : '新建笔记'" width="min(620px, calc(100vw - 24px))" destroy-on-close>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="标题" required>
          <el-input v-model="form.title" maxlength="200" show-word-limit placeholder="用一句话概括这条笔记" />
        </el-form-item>
        <el-form-item v-if="!form.id" label="关联文档（可选）">
          <el-select v-model="form.documentId" clearable filterable placeholder="选择来源文档" style="width:100%">
            <el-option v-for="doc in availableDocuments" :key="doc.id" :label="doc.name" :value="doc.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.selectedText" label="选中文字">
          <div class="editor-quote">{{ form.selectedText }}</div>
        </el-form-item>
        <el-form-item :label="form.sourceType === 'ai_explanation' ? 'AI 解释' : '笔记内容'" required>
          <el-input v-model="form.content" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" maxlength="50000" show-word-limit />
        </el-form-item>
        <el-form-item label="我的备注（可选）">
          <el-input v-model="form.remark" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" maxlength="5000" show-word-limit placeholder="记录你的理解、疑问或下一步行动" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveNote">保存笔记</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ArrowDown, Delete, Download, EditPen, FolderOpened, FullScreen, Location, MoreFilled, Plus, Search } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request, { notifyRequestError } from '@/utils/request'
import { listDocuments } from '@/api/documents'
import { formatTime } from '@/utils/format'
import { navigateToSource } from '@/utils/sourceAnchor'
import { useListLoader } from '@/composables/useListLoader'

const router = useRouter()

const notes = ref([])
const total = ref(0)

// 服务商显示名映射（deepseek → DeepSeek）；接口失败时回退为原样显示 id
const providerNames = reactive({})
onMounted(async () => {
  try {
    const { data } = await request.get('/ai/providers')
    for (const item of data || []) providerNames[item.id] = item.name
  } catch (_) { /* 展示降级：直接显示 provider id */ }
})
const sourceLabel = (note) =>
    [providerNames[note.provider] || note.provider, note.model].filter(Boolean).join(' · ')
const documentStatuses = Object.freeze({
  available: { label: '可阅读', type: 'success' },
  recycled: { label: '回收站', type: 'warning' },
  deleted: { label: '原文已删除', type: 'danger' },
  unlinked: { label: '未关联', type: 'info' },
})
const documentStatus = note => documentStatuses[note.document_status] || (
  note.document_id ? documentStatuses.available
    : note.document_name ? documentStatuses.deleted : documentStatuses.unlinked
)
const exporting = ref(false)
const saving = ref(false)
const keyword = ref('')
const documentId = ref(null)
const viewMode = ref('timeline')
const timeSort = ref('newest')
const pageNum = ref(1)
const pageSize = ref(12)
const summary = reactive({ total: 0, documents: [] })
const availableDocuments = ref([])
const previewVisible = ref(false)
const previewNote = ref(null)
const selectionMode = ref(false)
const selectedNoteIds = ref(new Set())
const exportDocumentVisible = ref(false)
const exportDocumentValue = ref(null)
const editorVisible = ref(false)
const form = reactive({ id: null, sourceType: 'manual', title: '', documentId: null, selectedText: '', content: '', remark: '' })
let searchTimer = null

// 已删文档的笔记 document_id 为空但保留原名；用「name:文档名」作为筛选值，
// 与「unlinked」（从未关联文档）和数字 document_id 三种取值互不冲突。
const groupLabel = (item) => item.document_name || (item.document_id === null ? '未关联文档' : '未命名文档')
const groupValue = (item) => {
  if (item.document_id !== null && item.document_id !== undefined) return item.document_id
  return item.document_name ? `name:${item.document_name}` : 'unlinked'
}
const apiDocumentId = computed(() => (typeof documentId.value === 'number' ? documentId.value : undefined))
const filterUnlinked = computed(() => documentId.value === 'unlinked')
const filterDocumentName = computed(() =>
    typeof documentId.value === 'string' && documentId.value.startsWith('name:') ? documentId.value.slice(5) : undefined)
const currentSort = computed(() => viewMode.value === 'document' ? 'document' : timeSort.value)
const selectedCount = computed(() => selectedNoteIds.value.size)
const currentPageAllSelected = computed(() =>
    notes.value.length > 0 && notes.value.every(note => selectedNoteIds.value.has(note.id)))
const displayGroups = computed(() => {
  if (viewMode.value !== 'document') return [{ key: 'timeline', name: '', items: notes.value }]
  const groups = new Map()
  for (const note of notes.value) {
    const key = `${note.document_id ?? 'none'}:${note.document_name || '未关联文档'}`
    if (!groups.has(key)) groups.set(key, { key, name: note.document_name || '未关联文档', items: [] })
    groups.get(key).items.push(note)
  }
  return [...groups.values()]
})

const queryParams = () => ({
  keyword: keyword.value.trim(),
  documentId: apiDocumentId.value,
  unlinked: filterUnlinked.value || undefined,
  documentName: filterDocumentName.value || undefined,
  sort: currentSort.value,
  pageNum: pageNum.value,
  pageSize: pageSize.value,
})

const { loading, load: loadList } = useListLoader(
  () => request.get('/notes', { params: queryParams() }),
  { onError: error => notifyRequestError(error, '笔记加载失败，请重试') },
)

async function loadNotes() {
  const response = await loadList()
  if (!response) return
  notes.value = response.data?.list || []
  total.value = response.data?.total || 0
}

async function loadSummary() {
  try {
    const response = await request.get('/notes/summary')
    summary.total = response.data?.total || 0
    summary.documents = response.data?.documents || []
  } catch (error) {
    notifyRequestError(error, '笔记统计加载失败，请重试')
  }
}

async function loadDocuments() {
  // 文档数量上限（200）超过单页 100，翻页取全量，避免“关联文档”下拉静默缺项
  const pageSize = 100
  const list = []
  for (let pageNum = 1; pageNum <= 20; pageNum++) {
    const response = await listDocuments({ pageNum, pageSize })
    const data = response.data || {}
    list.push(...(data.list || []))
    if (list.length >= (data.total || 0) || !(data.list || []).length) break
  }
  availableDocuments.value = list
}

function resetPageAndLoad() {
  pageNum.value = 1
  loadNotes()
}

function scheduleLoad() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(resetPageAndLoad, 280)
}

function openPreview(note) {
  previewNote.value = note
  previewVisible.value = true
}

function handleCardClick(note) {
  if (selectionMode.value) toggleNoteSelection(note.id)
  else openPreview(note)
}

function toggleNoteSelection(id, checked = !selectedNoteIds.value.has(id)) {
  const next = new Set(selectedNoteIds.value)
  if (checked) next.add(id)
  else next.delete(id)
  selectedNoteIds.value = next
}

function startBatchSelection() {
  if (selectionMode.value) return
  selectionMode.value = true
  selectedNoteIds.value = new Set()
}

function cancelBatchSelection() {
  selectionMode.value = false
  selectedNoteIds.value = new Set()
}

function toggleCurrentPageSelection() {
  const next = new Set(selectedNoteIds.value)
  if (currentPageAllSelected.value) notes.value.forEach(note => next.delete(note.id))
  else notes.value.forEach(note => next.add(note.id))
  selectedNoteIds.value = next
}

function locateSource(note) {
  if (!navigateToSource(router, note.source_anchor)) {
    ElMessage.warning('该笔记没有有效的原文定位')
  }
}

function resetForm() {
  Object.assign(form, { id: null, sourceType: 'manual', title: '', documentId: null, selectedText: '', content: '', remark: '' })
}

async function openCreate() {
  resetForm()
  editorVisible.value = true
  if (!availableDocuments.value.length) {
    try { await loadDocuments() } catch (_) {}
  }
}

function openEdit(note) {
  previewVisible.value = false
  Object.assign(form, {
    id: note.id,
    sourceType: note.source_type,
    title: note.title,
    documentId: note.document_id,
    selectedText: note.selected_text || '',
    content: note.content,
    remark: note.remark || '',
  })
  editorVisible.value = true
}

async function saveNote() {
  if (!form.title.trim()) return ElMessage.warning('请输入笔记标题')
  if (!form.content.trim()) return ElMessage.warning('请输入笔记内容')
  saving.value = true
  try {
    if (form.id) {
      await request.put(`/notes/${form.id}`, { title: form.title, content: form.content, remark: form.remark })
    } else {
      await request.post('/notes', {
        source_type: 'manual', document_id: form.documentId,
        title: form.title, content: form.content, remark: form.remark,
      })
    }
    editorVisible.value = false
    ElMessage.success(form.id ? '笔记已更新' : '笔记已创建')
    await Promise.all([loadNotes(), loadSummary()])
  } catch (error) {
    notifyRequestError(error, '笔记保存失败，请重试')
  } finally {
    saving.value = false
  }
}

async function deleteNote(note) {
  await ElMessageBox.confirm(`确定删除笔记「${note.title}」吗？`, '删除笔记', { type: 'warning' })
  await request.delete(`/notes/${note.id}`)
  toggleNoteSelection(note.id, false)
  ElMessage.success('笔记已删除')
  if (notes.value.length === 1 && pageNum.value > 1) pageNum.value -= 1
  await Promise.all([loadNotes(), loadSummary()])
}

async function deletePreviewNote() {
  const note = previewNote.value
  if (!note) return
  try {
    await deleteNote(note)
    previewVisible.value = false
    previewNote.value = null
  } catch (_) {
    // 用户取消删除时保持详情弹窗，便于继续阅读。
  }
}

function handleCardCommand(command, note) {
  if (command === 'edit') openEdit(note)
  if (command === 'delete') deleteNote(note).catch(() => {})
}

function localDateStamp() {
  const now = new Date()
  return [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-')
}

function safeFilePart(value) {
  return String(value || '未关联文档').replace(/[\\/:*?"<>|]/g, '-').replace(/\s+/g, ' ').trim().slice(0, 80)
}

async function downloadNotes(payload, filename) {
  exporting.value = true
  try {
    const blob = await request.post('/notes/export', payload, {
      responseType: 'blob', timeout: 120000, skipErrorToast: true,
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
    ElMessage.success('笔记已导出')
  } catch (error) {
    await notifyRequestError(error, '笔记导出失败，请重试')
  } finally {
    exporting.value = false
  }
}

function handleExportCommand(command) {
  if (command === 'document') {
    exportDocumentValue.value = null
    exportDocumentVisible.value = true
  } else if (command === 'selected') {
    startBatchSelection()
  } else if (command === 'all') {
    downloadNotes({ scope: 'all' }, `我的笔记-全量-${localDateStamp()}.md`)
  }
}

async function exportDocumentNotes() {
  const value = exportDocumentValue.value
  if (value === null) return ElMessage.warning('请选择来源文档')
  const item = summary.documents.find(document => groupValue(document) === value)
  const payload = { scope: 'document' }
  if (typeof value === 'number') payload.document_id = value
  else if (value === 'unlinked') payload.unlinked = true
  else payload.document_name = value.slice(5)
  await downloadNotes(payload, `我的笔记-${safeFilePart(groupLabel(item || {}))}-${localDateStamp()}.md`)
  exportDocumentVisible.value = false
}

async function exportSelectedNotes() {
  if (!selectedCount.value) return ElMessage.warning('请先选择需要导出的笔记')
  const count = selectedCount.value
  await downloadNotes(
      { scope: 'selected', note_ids: [...selectedNoteIds.value] },
      `我的笔记-批量${count}条-${localDateStamp()}.md`,
  )
  cancelBatchSelection()
}

onMounted(() => Promise.all([loadNotes(), loadSummary()]))
onBeforeUnmount(() => clearTimeout(searchTimer))
</script>

<style scoped>
.notes-page { max-width: 1240px; margin: 0 auto; }
.notes-heading { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-bottom: 14px; padding: 6px 4px; }
.notes-heading h1 { margin: 0 0 7px; font-size: 24px; color: #24384c; }
.notes-heading p { margin: 0; color: var(--ik-text-sub); }
.heading-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.heading-actions .el-button { margin-left: 0; }
.export-arrow { margin-left: 6px; }
.note-total { display: flex; align-items: baseline; gap: 5px; margin-right: 4px; color: var(--ik-text-sub); }
.note-total strong { color: var(--ik-blue); font-size: 25px; }
.note-total span { font-size: 12px; }
.notes-filter { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; padding: 12px; }
.keyword-input { flex: 1; min-width: 240px; }
.document-filter { width: 240px; }
.sort-select { width: 120px; }
.selection-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-bottom: 14px; padding: 11px 14px; border-color: rgba(0, 150, 180, .24); background: #f4fbfd; }
.selection-toolbar > div:first-child { display: flex; min-width: 0; align-items: baseline; gap: 9px; }
.selection-toolbar strong { color: #24384c; }
.selection-toolbar span { color: var(--ik-text-sub); font-size: 12px; }
.selection-actions { display: flex; flex: none; align-items: center; gap: 8px; }
.selection-actions :deep(.el-button) { margin-left: 0; }
.notes-content { min-height: 260px; }
.note-group { margin-bottom: 18px; }
.group-heading { display: flex; align-items: center; justify-content: space-between; padding: 6px 4px 10px; color: var(--ik-text-sub); }
.group-heading > div { display: flex; align-items: center; gap: 7px; min-width: 0; }
.group-heading .el-icon { color: var(--ik-cyan-deep); }
.group-heading h2 { margin: 0; overflow: hidden; color: #33475e; font-size: 16px; text-overflow: ellipsis; white-space: nowrap; }
.group-heading span { flex: none; font-size: 12px; }
.notes-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: start; gap: 12px; }
.note-card { display: flex; flex-direction: column; min-width: 0; padding: 11px 12px 12px; overflow: hidden; cursor: pointer; transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease; }
.note-card:hover { transform: translateY(-2px); border-color: rgba(0, 150, 180, .24); box-shadow: 0 10px 24px rgba(0, 69, 183, .11); }
.note-card.selected { border-color: var(--ik-cyan-deep); background: #f2fbfd; box-shadow: 0 0 0 2px rgba(0, 150, 180, .12); }
.note-card:focus-visible { outline: 2px solid var(--ik-blue); outline-offset: 2px; }
.note-selection-row { display: flex; justify-content: flex-end; margin: -3px 0 5px; padding-bottom: 6px; border-bottom: 1px solid #e2eff2; }
.note-selection-row :deep(.el-checkbox) { height: 24px; }
.note-selection-row :deep(.el-checkbox__label) { padding-left: 5px; color: var(--ik-text-sub); font-size: 12px; }
.note-card-heading { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; column-gap: 5px; row-gap: 2px; }
.note-document-line { display: flex; min-width: 0; align-items: center; gap: 4px; line-height: 1.2; }
.note-document-line :deep(.el-tag),
.note-secondary-tags :deep(.el-tag) { flex: none; height: 20px; padding: 0 6px; font-size: 10px; line-height: 18px; }
.note-card-actions { display: flex; flex: none; align-items: center; gap: 2px; }
.note-secondary-tags { grid-column: 1 / -1; display: flex; align-items: center; gap: 4px; min-height: 20px; }
.document-name { flex: 0 1 auto; min-width: 0; overflow: hidden; color: var(--ik-text-sub); font-size: 11px; line-height: 20px; text-overflow: ellipsis; white-space: nowrap; }
.more-button { display: inline-flex; padding: 4px; border: 0; border-radius: 6px; color: var(--ik-text-sub); background: transparent; cursor: pointer; }
.more-button:hover, .more-button:focus-visible { color: var(--ik-blue); background: #eaf6fb; outline: none; }
.note-card h3 { margin: 6px 0; overflow: hidden; color: #24384c; font-size: 16px; line-height: 1.35; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.selected-text { margin: 0 0 8px; padding: 7px 9px; overflow: hidden; color: var(--ik-text-sub); font-size: 11px; line-height: 1.5; background: #f5f9fc; border-left: 3px solid var(--ik-cyan); border-radius: 4px 8px 8px 4px; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.source-link { display: inline-flex; min-height: 24px; align-items: center; gap: 3px; margin: 0; padding: 3px 6px; border: 0; border-radius: 6px; color: var(--ik-blue); font-size: 11px; background: #edf8fc; white-space: nowrap; cursor: pointer; }
.source-link:hover, .source-link:focus-visible { color: #fff; background: var(--ik-cyan-deep); outline: none; }
.note-content { color: var(--ik-text); font-size: 13px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.note-content.clamped { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.note-remark { margin-top: 14px; padding: 10px 12px; background: #fffaf0; border: 1px solid #f4dfb1; border-radius: 9px; }
.note-remark span { color: #9a6b13; font-size: 11px; font-weight: 700; }
.note-remark p { margin: 5px 0 0; color: #5f4a24; font-size: 13px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.note-remark-compact { margin-top: 9px; padding: 6px 8px; }
.note-remark-compact p { margin-top: 2px; overflow: hidden; font-size: 11px; line-height: 1.4; text-overflow: ellipsis; white-space: nowrap; }
.note-meta { display: flex; align-items: flex-end; justify-content: space-between; gap: 8px; margin-top: 10px; padding-top: 9px; color: var(--ik-text-sub); font-size: 11px; border-top: 1px solid #edf3f6; }
.note-meta-info { display: flex; min-width: 0; flex-direction: column; gap: 2px; }
.note-meta-info span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-preview-hint { display: inline-flex; flex: none; align-items: center; gap: 3px; color: var(--ik-blue); }
.note-card:hover .card-preview-hint { color: var(--ik-cyan-deep); }
.notes-pagination { justify-content: center; margin-top: 20px; }
.document-export-dialog p { margin: 0 0 16px; color: var(--ik-text-sub); font-size: 13px; line-height: 1.7; }
.note-detail { color: var(--ik-text); }
.note-detail-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.note-detail-tags { display: flex; min-width: 0; align-items: center; flex-wrap: wrap; gap: 8px; }
.detail-document-name { color: var(--ik-text-sub); overflow-wrap: anywhere; }
.note-detail-actions { display: flex; flex: none; align-items: center; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.note-detail-actions :deep(.el-button) { margin-left: 0; }
.note-detail h2 { margin: 22px 0 18px; color: #24384c; font-size: 24px; line-height: 1.45; overflow-wrap: anywhere; }
.note-detail-section { margin-top: 18px; }
.note-detail-section > strong { display: block; margin-bottom: 8px; color: #33475e; font-size: 13px; }
.note-detail-section blockquote { margin: 0; padding: 12px 14px; color: var(--ik-text-sub); line-height: 1.75; white-space: pre-wrap; overflow-wrap: anywhere; background: #f5f9fc; border-left: 3px solid var(--ik-cyan); border-radius: 5px 10px 10px 5px; }
.note-detail-content { max-height: 42vh; overflow-y: auto; padding-right: 8px; font-size: 15px; line-height: 1.85; white-space: pre-wrap; overflow-wrap: anywhere; }
.note-detail-remark { padding: 12px 14px; background: #fffaf0; border: 1px solid #f4dfb1; border-radius: 10px; }
.note-detail-remark > div { color: #5f4a24; line-height: 1.75; white-space: pre-wrap; overflow-wrap: anywhere; }
.note-detail-meta { display: flex; justify-content: space-between; gap: 12px; margin-top: 22px; padding-top: 14px; color: var(--ik-text-sub); font-size: 12px; border-top: 1px solid var(--ik-border); }
.editor-quote { width: 100%; max-height: 120px; overflow-y: auto; padding: 10px 12px; color: var(--ik-text-sub); line-height: 1.65; white-space: pre-wrap; background: #f5f9fc; border-left: 3px solid var(--ik-cyan); border-radius: 6px; }
@media (max-width: 1280px) { .notes-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 1000px) { .notes-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .notes-heading { align-items: flex-start; flex-direction: column; } .heading-actions { justify-content: flex-start; } }
@media (max-width: 680px) { .notes-grid { grid-template-columns: 1fr; } .keyword-input, .document-filter, .sort-select { width: 100%; min-width: 100%; } .notes-filter .el-radio-group { width: 100%; } .notes-filter :deep(.el-radio-button) { flex: 1; } .notes-filter :deep(.el-radio-button__inner) { width: 100%; } .selection-toolbar, .selection-toolbar > div:first-child { align-items: flex-start; flex-direction: column; } .selection-actions { width: 100%; flex-wrap: wrap; } .note-detail-heading { flex-direction: column; } .note-detail-actions { width: 100%; justify-content: flex-start; } .note-detail h2 { margin-top: 18px; font-size: 21px; } .note-detail-meta { flex-direction: column; gap: 5px; } .notes-pagination { flex-wrap: wrap; } .notes-pagination :deep(.el-pagination__total), .notes-pagination :deep(.el-pagination__sizes) { display: none; } }
</style>
