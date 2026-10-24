<template>
  <div class="home-dashboard">
    <div class="home-grid">
      <main class="home-primary">
        <section class="home-welcome" aria-labelledby="home-welcome-title">
          <div>
            <p class="welcome-eyebrow">IKNOWREAD 知识阅读空间</p>
            <h1 id="home-welcome-title">欢迎回来，{{ displayName }} <span aria-hidden="true">👋</span></h1>
            <p>继续阅读与探索你的知识库</p>
          </div>
          <div class="welcome-decoration" aria-hidden="true"><Reading /></div>
        </section>

        <form class="home-search" role="search" @submit.prevent="searchDocuments">
          <el-icon aria-hidden="true"><Search /></el-icon>
          <input v-model.trim="searchKeyword" type="search" maxlength="255" aria-label="搜索文档" placeholder="搜索文档、知识和笔记...">
          <button type="submit" :disabled="!searchKeyword" aria-label="开始搜索">
            搜索 <el-icon><ArrowRight /></el-icon>
          </button>
        </form>

        <section aria-labelledby="quick-actions-title">
          <h2 id="quick-actions-title" class="section-title">快捷操作</h2>
          <div class="quick-grid">
            <button v-for="action in quickActions" :key="action.label" type="button" class="quick-action" @click="router.push(action.to)">
              <span class="quick-icon"><el-icon><component :is="action.icon" /></el-icon></span>
              <span><strong>{{ action.label }}</strong><small>{{ action.description }}</small></span>
              <el-icon class="quick-arrow"><ArrowRight /></el-icon>
            </button>
          </div>
        </section>

        <section class="dashboard-card continue-card" aria-labelledby="continue-title">
          <header class="card-heading">
            <div><span class="heading-mark" aria-hidden="true"></span><h2 id="continue-title">继续阅读</h2></div>
            <button type="button" class="text-link" @click="router.push('/manager/reader')">查看全部 <el-icon><ArrowRight /></el-icon></button>
          </header>
          <button v-if="continueReading" type="button" class="continue-document" @click="openDocument(continueReading.document)">
            <span class="document-tile"><el-icon><Document /></el-icon></span>
            <span class="continue-copy">
              <strong :title="continueReading.document.name">{{ continueReading.document.name }}</strong>
              <small>{{ continueLabel(continueReading) }}</small>
              <span class="progress-track" aria-hidden="true"><span :style="{ width: `${Math.max(continueReading.percent, 2)}%` }"></span></span>
            </span>
            <span class="continue-percent">{{ continueReading.percent }}%</span>
          </button>
          <div v-else-if="loading" class="continue-state"><el-icon class="is-loading"><Loading /></el-icon><span>正在读取你的阅读进度…</span></div>
          <div v-else class="continue-state">
            <el-icon><Reading /></el-icon>
            <span>{{ documents.length ? '还没有阅读记录，选择一份文档开始吧' : '上传第一份文档，开始建立你的知识库' }}</span>
            <button type="button" @click="router.push(documents.length ? '/manager/reader' : '/manager/document?focus=upload')">{{ documents.length ? '开始阅读' : '上传文档' }}</button>
          </div>
        </section>

        <section class="recent-section" aria-labelledby="recent-title">
          <header class="card-heading recent-heading">
            <div><span class="heading-mark" aria-hidden="true"></span><h2 id="recent-title">最近文档</h2></div>
            <button type="button" class="text-link" @click="router.push('/manager/document')">管理文档 <el-icon><ArrowRight /></el-icon></button>
          </header>
          <div v-if="recentDocuments.length" class="recent-list">
            <button v-for="document in recentDocuments" :key="document.id" type="button" class="recent-row" @click="openDocument(document)">
              <span class="recent-icon"><el-icon><Document /></el-icon></span>
              <span class="recent-name" :title="document.name">{{ document.name }}</span>
              <span class="recent-type">{{ documentTypeLabel(document) }}</span>
              <el-icon class="recent-arrow"><ArrowRight /></el-icon>
            </button>
          </div>
          <div v-else-if="!loading" class="recent-empty">暂无文档，上传后会在这里显示。</div>
          <el-skeleton v-else :rows="3" animated />
        </section>
      </main>

      <aside class="home-sidebar" aria-label="阅读概览与任务">
        <section class="dashboard-card overview-card" aria-labelledby="overview-title">
          <header class="card-heading">
            <div><span class="heading-mark" aria-hidden="true"></span><h2 id="overview-title">我的阅读概览</h2></div>
            <el-icon class="heading-icon"><DataAnalysis /></el-icon>
          </header>
          <div class="overview-grid" aria-live="polite">
            <button type="button" @click="router.push('/manager/document')"><strong>{{ dashboard.documentTotal }}</strong><span>文档</span></button>
            <button type="button" @click="router.push('/manager/reader')"><strong>{{ readingEntries.length }}</strong><span>最近阅读</span></button>
            <button type="button" @click="router.push('/manager/notes')"><strong>{{ dashboard.noteTotal }}</strong><span>笔记</span></button>
            <button type="button" @click="router.push('/manager/document')"><strong>{{ processingTotal }}</strong><span>处理中</span></button>
          </div>
        </section>

        <section class="dashboard-card task-card" aria-labelledby="tasks-title">
          <header class="card-heading">
            <div><span class="heading-mark" aria-hidden="true"></span><h2 id="tasks-title">导入任务</h2></div>
            <button type="button" class="icon-link" aria-label="查看导入任务" @click="router.push('/manager/document?focus=web-import')"><el-icon><ArrowRight /></el-icon></button>
          </header>
          <div v-if="visibleJobs.length" class="task-list">
            <button v-for="job in visibleJobs" :key="job.id" type="button" @click="router.push('/manager/document?focus=web-import')">
              <span class="task-status" :class="`is-${job.status}`">
                <el-icon v-if="job.status === 'success'"><CircleCheck /></el-icon>
                <el-icon v-else-if="job.status === 'failed'"><Warning /></el-icon>
                <el-icon v-else-if="job.status === 'canceled'"><CircleClose /></el-icon>
                <el-icon v-else class="is-loading"><Loading /></el-icon>
              </span>
              <span class="task-copy"><strong>{{ webImportHost(job.source_url) }}</strong><small>{{ jobLabel(job) }}</small></span>
              <span v-if="['pending', 'processing'].includes(job.status)" class="task-progress">{{ job.progress || 0 }}%</span>
            </button>
          </div>
          <div v-else-if="loading" class="side-state">正在读取导入任务…</div>
          <div v-else class="side-state"><span>暂无网页导入任务</span><button type="button" @click="router.push('/manager/document?focus=web-import')">导入网页</button></div>
        </section>

        <button type="button" class="dashboard-card review-card" @click="router.push('/manager/notes')">
          <span class="review-icon"><el-icon><Notebook /></el-icon></span>
          <span><strong>知识回顾</strong><small v-if="dashboard.noteTotal">从 {{ dashboard.noteTotal }} 条笔记中重温重点内容</small><small v-else>阅读时保存 AI 解释，沉淀你的知识笔记</small></span>
          <el-icon class="review-arrow"><ArrowRight /></el-icon>
        </button>

        <div v-if="loadWarnings.length" class="load-warning" role="status">
          <el-icon><Warning /></el-icon><span>首页数据暂未加载，可稍后刷新重试。</span><button type="button" @click="loadDashboard">重试</button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, markRaw, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight, ChatDotRound, CircleCheck, CircleClose, DataAnalysis, Document,
  FolderOpened, Link, Loading, Notebook, Reading, Search, Upload, Warning,
} from '@element-plus/icons-vue'
import { getDashboard } from '@/api/dashboard'
import { getSession } from '@/utils/session'
import {
  collectReadingProgress, documentTypeLabel, webImportHost,
} from '@/utils/homeDashboard'

const router = useRouter()
const user = getSession()
const displayName = computed(() => user.name || user.username || '用户')
const searchKeyword = ref('')
const loading = ref(false)
const loadWarnings = ref([])
const dashboard = reactive({ documentTotal: 0, noteTotal: 0, processingTotal: 0 })
const documents = ref([])
const webJobs = ref([])
const serverReading = ref([])
let refreshTimer = null
let stopped = false
let loadVersion = 0

const quickActions = [
  { label: '上传文档', description: 'PDF、DOCX、Markdown', icon: markRaw(Upload), to: '/manager/document?focus=upload' },
  { label: '导入网页', description: '收藏网页到知识库', icon: markRaw(Link), to: '/manager/document?focus=web-import' },
  { label: 'AI 问答', description: '向智能助手提问', icon: markRaw(ChatDotRound), to: '/manager/assistant' },
  { label: '我的文档', description: '管理个人知识库', icon: markRaw(FolderOpened), to: '/manager/document' },
]

const readingEntries = computed(() => {
  const remote = serverReading.value.map(item => ({
    document: item.document,
    anchor: item.source_anchor,
    percent: Math.round((item.source_anchor?.progression || 0) * 100),
  }))
  const remoteIds = new Set(remote.map(item => item.document.id))
  return [
    ...remote,
    ...collectReadingProgress(documents.value).filter(item => !remoteIds.has(item.document.id)),
  ]
})
const continueReading = computed(() => readingEntries.value[0] || null)
const recentDocuments = computed(() => documents.value.slice(0, 5))
const visibleJobs = computed(() => webJobs.value.slice(0, 3))
const processingTotal = computed(() => dashboard.processingTotal)

const scheduleRefresh = () => {
  clearTimeout(refreshTimer)
  if (!stopped && processingTotal.value > 0) refreshTimer = setTimeout(loadDashboard, 5000)
}

async function loadDashboard() {
  const version = ++loadVersion
  loading.value = true
  try {
    const response = await getDashboard({ skipErrorToast: true })
    if (stopped || version !== loadVersion) return
    const data = response.data || {}
    dashboard.documentTotal = Number(data.document_total) || 0
    dashboard.noteTotal = Number(data.note_total) || 0
    dashboard.processingTotal = Number(data.processing_total) || 0
    documents.value = data.recent_documents || []
    serverReading.value = data.recent_reading || []
    webJobs.value = data.web_imports || []
    loadWarnings.value = []
  } catch (_) {
    if (stopped || version !== loadVersion) return
    loadWarnings.value = ['dashboard']
  }
  loading.value = false
  scheduleRefresh()
}

const searchDocuments = () => {
  if (searchKeyword.value) router.push({ path: '/manager/document', query: { name: searchKeyword.value } })
}
const openDocument = document => router.push({ path: '/manager/reader', query: { documentId: document.id } })
const continueLabel = entry => entry.anchor.source_format === 'pdf' ? `上次阅读 · 第 ${entry.anchor.page} 页` : `上次阅读 · 已读 ${entry.percent}%`
const jobLabel = job => ({ pending: '等待提取网页内容', processing: '正在提取网页内容', success: '文档解析完成', failed: '导入失败，点击查看', canceled: '任务已取消' })[job.status] || '状态未知'

loadDashboard()
onBeforeUnmount(() => {
  stopped = true
  loadVersion += 1
  clearTimeout(refreshTimer)
})
</script>

<style scoped>
.home-dashboard { width: min(100%, 1320px); margin: 0 auto; padding: 8px 6px 26px; }
.home-grid { display: grid; grid-template-columns: minmax(0, 1fr) 350px; gap: 22px; align-items: start; }
.home-primary, .home-sidebar { min-width: 0; }
.home-sidebar { display: grid; gap: 16px; }
.home-welcome { position: relative; display: flex; min-height: 142px; align-items: center; justify-content: space-between; overflow: hidden; padding: 26px 30px; color: #fff; background: var(--ik-gradient); border-radius: 18px; box-shadow: 0 12px 30px rgba(0, 69, 183, .18); }
.home-welcome::before, .home-welcome::after { position: absolute; content: ''; border: 1px solid rgba(255, 255, 255, .18); border-radius: 50%; }
.home-welcome::before { width: 180px; height: 180px; right: -30px; top: -90px; }
.home-welcome::after { width: 100px; height: 100px; right: 80px; bottom: -72px; }
.home-welcome > div:first-child { position: relative; z-index: 1; }
.welcome-eyebrow { margin: 0 0 8px !important; font-size: 11px !important; font-weight: 700; letter-spacing: 1.5px; opacity: .76; }
.home-welcome h1 { margin: 0; font-size: clamp(24px, 3vw, 32px); line-height: 1.25; }
.home-welcome p { margin: 10px 0 0; font-size: 15px; opacity: .86; }
.welcome-decoration { position: relative; z-index: 1; display: grid; width: 68px; height: 68px; place-items: center; font-size: 35px; background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.22); border-radius: 22px; transform: rotate(6deg); }
.home-search { display: flex; height: 58px; align-items: center; gap: 13px; margin: 16px 0 24px; padding: 0 9px 0 20px; background: #fff; border: 1px solid var(--ik-border); border-radius: 15px; box-shadow: 0 5px 18px rgba(0, 69, 183, .06); }
.home-search > .el-icon { flex: none; color: var(--ik-cyan-deep); font-size: 21px; }
.home-search input { flex: 1; min-width: 0; height: 100%; padding: 0; color: var(--ik-text); font: inherit; font-size: 15px; background: transparent; border: 0; outline: 0; }
.home-search input::placeholder { color: #8ba0b2; }
.home-search input::-webkit-search-cancel-button { display: none; }
.home-search button { display: inline-flex; height: 40px; align-items: center; gap: 5px; padding: 0 15px; color: #fff; font: inherit; font-size: 13px; font-weight: 600; background: var(--ik-gradient); border: 0; border-radius: 10px; cursor: pointer; }
.home-search button:disabled { cursor: default; opacity: .45; }
.section-title { margin: 0 0 12px; color: var(--ik-text); font-size: 18px; }
.quick-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.quick-action { display: flex; min-width: 0; min-height: 90px; align-items: center; gap: 14px; padding: 15px 17px; text-align: left; background: #fff; border: 1px solid var(--ik-border); border-radius: 15px; box-shadow: 0 3px 12px rgba(0,69,183,.04); cursor: pointer; transition: border-color .2s, box-shadow .2s, transform .2s; }
.quick-action:hover { border-color: #abd8e8; box-shadow: 0 8px 22px rgba(0,69,183,.09); transform: translateY(-2px); }
.quick-icon { display: grid; flex: none; width: 45px; height: 45px; place-items: center; color: var(--ik-blue); font-size: 23px; background: linear-gradient(135deg, #edf5ff, #e5fbf9); border-radius: 13px; }
.quick-action > span:nth-child(2) { min-width: 0; }
.quick-action strong, .quick-action small { display: block; }
.quick-action strong { color: var(--ik-text); font-size: 16px; }
.quick-action small { margin-top: 5px; overflow: hidden; color: var(--ik-text-sub); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.quick-arrow { flex: none; margin-left: auto; color: #9db0bf; }
.dashboard-card { background: #fff; border: 1px solid var(--ik-border); border-radius: 17px; box-shadow: 0 5px 18px rgba(0,69,183,.055); }
.continue-card { padding: 18px 20px 20px; }
.card-heading { display: flex; min-height: 30px; align-items: center; justify-content: space-between; gap: 12px; }
.card-heading > div { display: flex; min-width: 0; align-items: center; gap: 9px; }
.card-heading h2 { margin: 0; color: var(--ik-text); font-size: 18px; }
.heading-mark { width: 4px; height: 18px; background: var(--ik-gradient); border-radius: 4px; }
.heading-icon { color: var(--ik-cyan-deep); font-size: 21px; }
.text-link, .icon-link { display: inline-flex; flex: none; align-items: center; gap: 4px; padding: 5px; color: var(--ik-text-sub); font: inherit; font-size: 12px; background: transparent; border: 0; border-radius: 7px; cursor: pointer; }
.text-link:hover, .icon-link:hover { color: var(--ik-blue); background: #eef8fc; }
.continue-document { display: flex; width: 100%; align-items: center; gap: 14px; margin-top: 13px; padding: 9px 8px; text-align: left; background: transparent; border: 0; border-radius: 12px; cursor: pointer; }
.continue-document:hover { background: #f5fbfd; }
.document-tile { display: grid; flex: none; width: 52px; height: 52px; place-items: center; color: var(--ik-blue); font-size: 24px; background: linear-gradient(135deg, #edf5ff, #eafbf9); border-radius: 14px; }
.continue-copy { flex: 1; min-width: 0; }
.continue-copy strong, .continue-copy small { display: block; }
.continue-copy strong { overflow: hidden; color: var(--ik-text); font-size: 15px; text-overflow: ellipsis; white-space: nowrap; }
.continue-copy small { margin-top: 5px; color: var(--ik-text-sub); font-size: 12px; }
.progress-track { display: block; height: 5px; margin-top: 10px; overflow: hidden; background: #edf2f5; border-radius: 8px; }
.progress-track > span { display: block; height: 100%; background: var(--ik-gradient); border-radius: inherit; }
.continue-percent { flex: none; align-self: flex-end; margin-bottom: 2px; color: var(--ik-cyan-deep); font-size: 12px; font-weight: 700; }
.continue-state { display: flex; min-height: 76px; align-items: center; gap: 10px; margin-top: 10px; padding: 12px; color: var(--ik-text-sub); font-size: 13px; background: #f7fbfd; border-radius: 12px; }
.continue-state > .el-icon { color: var(--ik-cyan-deep); font-size: 20px; }
.continue-state button, .side-state button { margin-left: auto; padding: 6px 10px; color: var(--ik-blue); font: inherit; font-size: 12px; font-weight: 600; background: #eaf6fb; border: 0; border-radius: 7px; cursor: pointer; }
.recent-section { margin-top: 20px; }
.recent-heading { padding: 0 4px 8px; }
.recent-list { overflow: hidden; background: #fff; border: 1px solid var(--ik-border); border-radius: 15px; }
.recent-row { display: flex; width: 100%; min-width: 0; height: 54px; align-items: center; gap: 12px; padding: 0 15px; text-align: left; background: #fff; border: 0; border-bottom: 1px solid #edf3f7; cursor: pointer; }
.recent-row:last-child { border-bottom: 0; }
.recent-row:hover { background: #f4fbfd; }
.recent-icon { display: grid; flex: none; width: 30px; height: 30px; place-items: center; color: var(--ik-cyan-deep); background: #eaf8fb; border-radius: 8px; }
.recent-name { flex: 1; min-width: 0; overflow: hidden; color: var(--ik-text); font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.recent-type { flex: none; color: #8ca0b0; font-size: 11px; }
.recent-arrow { flex: none; color: #b0bec9; font-size: 13px; }
.recent-empty { padding: 32px; color: var(--ik-text-sub); text-align: center; background: #fff; border: 1px dashed var(--ik-border); border-radius: 15px; }
.overview-card, .task-card { padding: 18px; }
.overview-grid { display: grid; grid-template-columns: repeat(2, 1fr); margin-top: 12px; }
.overview-grid button { min-height: 88px; padding: 13px 10px; text-align: left; background: transparent; border: 0; border-right: 1px solid #edf3f7; border-bottom: 1px solid #edf3f7; cursor: pointer; }
.overview-grid button:nth-child(2n) { border-right: 0; padding-left: 20px; }
.overview-grid button:nth-last-child(-n+2) { border-bottom: 0; }
.overview-grid button:hover { background: #f5fbfd; }
.overview-grid strong, .overview-grid span { display: block; }
.overview-grid strong { color: var(--ik-blue-deep); font-size: 28px; line-height: 1; }
.overview-grid span { margin-top: 10px; color: var(--ik-text-sub); font-size: 12px; }
.task-list { margin-top: 10px; }
.task-list > button { display: flex; width: 100%; align-items: center; gap: 10px; padding: 11px 3px; text-align: left; background: transparent; border: 0; border-bottom: 1px solid #edf3f7; cursor: pointer; }
.task-list > button:last-child { border-bottom: 0; }
.task-list > button:hover .task-copy strong { color: var(--ik-blue); }
.task-status { display: grid; flex: none; width: 28px; height: 28px; place-items: center; font-size: 19px; background: #eef4f6; border-radius: 50%; }
.task-status.is-success { color: #17a673; background: #eaf8f2; }
.task-status.is-failed { color: #d95757; background: #fff0f0; }
.task-status.is-canceled { color: #8a9aa7; }
.task-status.is-pending, .task-status.is-processing { color: var(--ik-blue); background: #edf4ff; }
.task-copy { flex: 1; min-width: 0; }
.task-copy strong, .task-copy small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-copy strong { color: var(--ik-text); font-size: 13px; }
.task-copy small { margin-top: 4px; color: var(--ik-text-sub); font-size: 11px; }
.task-progress { flex: none; color: var(--ik-blue); font-size: 11px; font-weight: 700; }
.side-state { display: flex; min-height: 76px; align-items: center; margin-top: 10px; padding: 11px; color: var(--ik-text-sub); font-size: 12px; background: #f7fbfd; border-radius: 10px; }
.review-card { display: flex; width: 100%; align-items: center; gap: 12px; padding: 18px; text-align: left; cursor: pointer; transition: border-color .2s, transform .2s; }
.review-card:hover { border-color: #abd8e8; transform: translateY(-2px); }
.review-icon { display: grid; flex: none; width: 42px; height: 42px; place-items: center; color: #fff; font-size: 21px; background: var(--ik-gradient); border-radius: 12px; }
.review-card > span:nth-child(2) { flex: 1; min-width: 0; }
.review-card strong, .review-card small { display: block; }
.review-card strong { color: var(--ik-text); font-size: 16px; }
.review-card small { margin-top: 5px; color: var(--ik-text-sub); font-size: 12px; line-height: 1.45; }
.review-arrow { flex: none; color: #9db0bf; }
.load-warning { display: flex; align-items: center; gap: 7px; padding: 10px 12px; color: #9a6d20; font-size: 11px; background: #fff9e9; border: 1px solid #f3dfaa; border-radius: 10px; }
.load-warning button { margin-left: auto; padding: 2px 0; color: #8a611d; font: inherit; font-weight: 700; background: transparent; border: 0; cursor: pointer; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--ik-blue); outline-offset: 2px; }
@media (max-width: 1100px) { .home-grid { grid-template-columns: minmax(0, 1fr) 310px; gap: 15px; } }
@media (max-width: 900px) { .home-grid { grid-template-columns: 1fr; } .home-sidebar { grid-template-columns: repeat(2, minmax(0, 1fr)); } .overview-card { grid-row: span 2; } }
@media (max-width: 620px) { .home-dashboard { padding: 0 0 20px; } .home-welcome { min-height: 132px; padding: 22px; } .welcome-decoration { display: none; } .quick-grid, .home-sidebar { grid-template-columns: 1fr; } .overview-card { grid-row: auto; } .home-search button { width: 40px; padding: 0; justify-content: center; font-size: 0; } .home-search button .el-icon { font-size: 14px; } }
</style>
