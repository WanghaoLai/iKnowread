<template>
  <section class="notes-page">
    <header class="notes-heading">
      <div>
        <h1>我的笔记</h1>
        <p>收纳阅读时的重要解释和思考，随时整理、检索与导出。</p>
      </div>
      <div class="heading-actions">
        <div class="note-total"><strong>{{ summary.total }}</strong><span>条笔记</span></div>
        <el-button :icon="Download" :loading="exporting" :disabled="!total" @click="exportNotes">导出笔记</el-button>
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
        <el-option v-for="item in summary.documents" :key="`${item.document_id}-${item.document_name}`" :label="`${item.document_name}（${item.count}）`" :value="item.document_id ?? 'unlinked'" />
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
          <article v-for="note in group.items" :key="note.id" class="note-card card">
            <header class="note-card-heading">
              <div class="note-tags">
                <el-tag size="small" effect="plain" :type="note.source_type === 'ai_explanation' ? 'success' : 'info'">
                  {{ note.source_type === 'ai_explanation' ? 'AI 划词' : '手动笔记' }}
                </el-tag>
                <span class="document-name" :title="note.document_name || '未关联文档'">{{ note.document_name || '未关联文档' }}</span>
              </div>
              <el-dropdown trigger="click" @command="command => handleCardCommand(command, note)">
                <button type="button" class="more-button" aria-label="笔记操作"><el-icon><MoreFilled /></el-icon></button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="edit" :icon="EditPen">编辑笔记</el-dropdown-item>
                    <el-dropdown-item command="delete" :icon="Delete" divided>删除笔记</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </header>

            <h3>{{ note.title }}</h3>
            <blockquote v-if="note.selected_text" class="selected-text">{{ note.selected_text }}</blockquote>
            <div class="note-content" :class="{ clamped: !expanded.has(note.id) }">{{ note.content }}</div>
            <button v-if="note.content.length > 220" type="button" class="expand-button" @click="toggleExpanded(note.id)">
              {{ expanded.has(note.id) ? '收起' : '展开全文' }}
            </button>
            <div v-if="note.remark" class="note-remark">
              <span>我的备注</span>
              <p>{{ note.remark }}</p>
            </div>
            <footer class="note-meta">
              <span>{{ formatTime(note.created_at) }}</span>
              <span v-if="note.model" :title="sourceLabel(note)">
                {{ sourceLabel(note) }}
              </span>
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
import { Delete, Download, EditPen, FolderOpened, MoreFilled, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/utils/request'
import { formatTime } from '@/utils/format'

const notes = ref([])
const total = ref(0)
const loading = ref(false)

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
const expanded = ref(new Set())
const editorVisible = ref(false)
const form = reactive({ id: null, sourceType: 'manual', title: '', documentId: null, selectedText: '', content: '', remark: '' })
let searchTimer = null
let loadSequence = 0

const apiDocumentId = computed(() => documentId.value === 'unlinked' ? undefined : documentId.value)
const filterUnlinked = computed(() => documentId.value === 'unlinked')
const currentSort = computed(() => viewMode.value === 'document' ? 'document' : timeSort.value)
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
  sort: currentSort.value,
  pageNum: pageNum.value,
  pageSize: pageSize.value,
})

async function loadNotes() {
  const sequence = ++loadSequence
  loading.value = true
  try {
    const response = await request.get('/notes', { params: queryParams() })
    if (sequence !== loadSequence) return
    notes.value = response.data?.list || []
    total.value = response.data?.total || 0
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function loadSummary() {
  const response = await request.get('/notes/summary')
  summary.total = response.data?.total || 0
  summary.documents = response.data?.documents || []
}

async function loadDocuments() {
  const response = await request.get('/document/selectPage', { params: { pageNum: 1, pageSize: 100 } })
  availableDocuments.value = response.data?.list || []
}

function resetPageAndLoad() {
  pageNum.value = 1
  loadNotes()
}

function scheduleLoad() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(resetPageAndLoad, 280)
}

function toggleExpanded(id) {
  const next = new Set(expanded.value)
  next.has(id) ? next.delete(id) : next.add(id)
  expanded.value = next
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
  } finally {
    saving.value = false
  }
}

async function deleteNote(note) {
  await ElMessageBox.confirm(`确定删除笔记「${note.title}」吗？`, '删除笔记', { type: 'warning' })
  await request.delete(`/notes/${note.id}`)
  ElMessage.success('笔记已删除')
  if (notes.value.length === 1 && pageNum.value > 1) pageNum.value -= 1
  await Promise.all([loadNotes(), loadSummary()])
}

function handleCardCommand(command, note) {
  if (command === 'edit') openEdit(note)
  if (command === 'delete') deleteNote(note).catch(() => {})
}

async function exportNotes() {
  exporting.value = true
  try {
    const blob = await request.get('/notes/export', {
      params: { keyword: keyword.value.trim(), documentId: apiDocumentId.value, unlinked: filterUnlinked.value || undefined, sort: currentSort.value },
      responseType: 'blob', timeout: 120000,
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const now = new Date()
    const localDate = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-')
    link.download = `我的笔记-${localDate}.md`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
    ElMessage.success('笔记已导出')
  } finally {
    exporting.value = false
  }
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
.note-total { display: flex; align-items: baseline; gap: 5px; margin-right: 4px; color: var(--ik-text-sub); }
.note-total strong { color: var(--ik-blue); font-size: 25px; }
.note-total span { font-size: 12px; }
.notes-filter { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; padding: 12px; }
.keyword-input { flex: 1; min-width: 240px; }
.document-filter { width: 240px; }
.sort-select { width: 120px; }
.notes-content { min-height: 260px; }
.note-group { margin-bottom: 18px; }
.group-heading { display: flex; align-items: center; justify-content: space-between; padding: 6px 4px 10px; color: var(--ik-text-sub); }
.group-heading > div { display: flex; align-items: center; gap: 7px; min-width: 0; }
.group-heading .el-icon { color: var(--ik-cyan-deep); }
.group-heading h2 { margin: 0; overflow: hidden; color: #33475e; font-size: 16px; text-overflow: ellipsis; white-space: nowrap; }
.group-heading span { flex: none; font-size: 12px; }
.notes-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.note-card { display: flex; flex-direction: column; min-width: 0; padding: 18px; }
.note-card-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.note-tags { display: flex; align-items: center; gap: 8px; min-width: 0; }
.document-name { overflow: hidden; color: var(--ik-text-sub); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.more-button { display: inline-flex; padding: 6px; border: 0; border-radius: 7px; color: var(--ik-text-sub); background: transparent; cursor: pointer; }
.more-button:hover, .more-button:focus-visible { color: var(--ik-blue); background: #eaf6fb; outline: none; }
.note-card h3 { margin: 14px 0 10px; color: #24384c; font-size: 17px; line-height: 1.45; }
.selected-text { margin: 0 0 12px; padding: 9px 11px; overflow: hidden; color: var(--ik-text-sub); font-size: 12px; line-height: 1.65; background: #f5f9fc; border-left: 3px solid var(--ik-cyan); border-radius: 4px 8px 8px 4px; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.note-content { color: var(--ik-text); font-size: 14px; line-height: 1.75; white-space: pre-wrap; overflow-wrap: anywhere; }
.note-content.clamped { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 5; }
.expand-button { align-self: flex-start; margin: 6px 0 0; padding: 0; border: 0; color: var(--ik-blue); background: transparent; cursor: pointer; }
.note-remark { margin-top: 14px; padding: 10px 12px; background: #fffaf0; border: 1px solid #f4dfb1; border-radius: 9px; }
.note-remark span { color: #9a6b13; font-size: 11px; font-weight: 700; }
.note-remark p { margin: 5px 0 0; color: #5f4a24; font-size: 13px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.note-meta { display: flex; justify-content: space-between; gap: 12px; margin-top: auto; padding-top: 16px; color: var(--ik-text-sub); font-size: 11px; }
.note-meta span:last-child { max-width: 55%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.notes-pagination { justify-content: center; margin-top: 20px; }
.editor-quote { width: 100%; max-height: 120px; overflow-y: auto; padding: 10px 12px; color: var(--ik-text-sub); line-height: 1.65; white-space: pre-wrap; background: #f5f9fc; border-left: 3px solid var(--ik-cyan); border-radius: 6px; }
@media (max-width: 900px) { .notes-grid { grid-template-columns: 1fr; } .notes-heading { align-items: flex-start; flex-direction: column; } .heading-actions { justify-content: flex-start; } }
@media (max-width: 640px) { .keyword-input, .document-filter, .sort-select { width: 100%; min-width: 100%; } .notes-filter .el-radio-group { width: 100%; } .notes-filter :deep(.el-radio-button) { flex: 1; } .notes-filter :deep(.el-radio-button__inner) { width: 100%; } .note-card { padding: 15px; } .note-meta { flex-direction: column; gap: 5px; } .note-meta span:last-child { max-width: 100%; } .notes-pagination { flex-wrap: wrap; } .notes-pagination :deep(.el-pagination__total), .notes-pagination :deep(.el-pagination__sizes) { display: none; } }
</style>
