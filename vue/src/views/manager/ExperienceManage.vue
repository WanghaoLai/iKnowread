<template>
  <section class="experience-page">
    <header class="page-heading">
      <div>
        <h1>体验账号管理</h1>
        <p>统一配置公开体验入口、只读文档范围与 AI 每日用量。</p>
      </div>
      <el-button type="primary" :loading="saving" :disabled="loading" @click="save">保存配置</el-button>
    </header>

    <el-alert
      title="体验账号采用后端强制只读策略：不可上传、导入、删除文档，不可新增或修改高亮与笔记，也不能管理 API 配置。"
      type="warning"
      show-icon
      :closable="false"
    />

    <div v-loading="loading" class="settings-grid">
      <section class="card settings-card">
        <h2>账号与用量</h2>
        <el-form label-position="top">
          <el-form-item label="公开体验入口">
            <el-switch v-model="form.enabled" active-text="启用" inactive-text="停用" />
          </el-form-item>
          <el-form-item label="体验账号">
            <el-input :model-value="settings.account?.username || 'test'" disabled />
          </el-form-item>
          <el-form-item label="公开密码">
            <el-input v-model="form.public_password" show-password maxlength="128" />
            <div class="form-hint">修改后会同步更新账号真实密码，并使旧会话失效。</div>
          </el-form-item>
          <el-form-item label="管理员 AI 配置">
            <el-select v-model="form.ai_config_id" clearable placeholder="不开放 AI 划词" style="width:100%">
              <el-option
                v-for="config in settings.ai_configs || []"
                :key="config.id"
                :label="`${config.name} · ${config.provider_name} · ${config.model}`"
                :value="config.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="每日 AI 划词次数上限">
            <el-input-number v-model="form.daily_ai_limit" :min="0" :max="1000" />
            <div class="form-hint">设为 0 即停用 AI。今日已使用 {{ settings.ai_used_today || 0 }} 次。</div>
          </el-form-item>
        </el-form>
        <div class="quota-summary">
          <span>上传文档：<strong>0</strong></span>
          <span>存储空间：<strong>0 B</strong></span>
          <span>AI 剩余：<strong>{{ settings.ai_remaining_today || 0 }}</strong></span>
        </div>
      </section>

      <section class="card settings-card">
        <h2>只读内容显示</h2>
        <div class="visibility-item">
          <div><strong>管理员高亮</strong><small>体验用户可查看共享文档中的管理员高亮及备注</small></div>
          <el-switch v-model="form.show_highlights" />
        </div>
        <div class="visibility-item">
          <div><strong>管理员笔记</strong><small>体验用户可查看共享文档关联的管理员笔记</small></div>
          <el-switch v-model="form.show_notes" />
        </div>
        <p class="readonly-note">上述内容始终为只读。关闭后接口返回空列表，不只是前端隐藏。</p>
      </section>
    </div>

    <section class="card document-card">
      <header>
        <div>
          <h2>共享阅读文档</h2>
          <p>仅可选择当前管理员上传且未进入回收站的文档。</p>
        </div>
        <el-input v-model.trim="search" clearable placeholder="搜索文档" :prefix-icon="Search" @input="scheduleSearch" />
      </header>
      <el-table ref="tableRef" v-loading="documentsLoading" :data="documents" row-key="id" @selection-change="selectionChanged">
        <el-table-column type="selection" width="52" :reserve-selection="true" />
        <el-table-column prop="name" label="文档名" min-width="300" show-overflow-tooltip />
        <el-table-column label="格式" width="100"><template #default="scope">{{ scope.row.ext.toUpperCase() }}</template></el-table-column>
        <el-table-column label="大小" width="120"><template #default="scope">{{ formatSize(scope.row.size) }}</template></el-table-column>
        <el-table-column label="上传时间" width="180"><template #default="scope">{{ formatTime(scope.row.created_at) }}</template></el-table-column>
      </el-table>
      <footer>
        <span>已选择 {{ form.document_ids.length }} 份文档</span>
        <el-pagination v-model:current-page="pageNum" :page-size="pageSize" :total="total" layout="total, prev, pager, next" @current-change="loadDocuments" />
      </footer>
    </section>
  </section>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getExperienceSettings, listExperienceDocuments, updateExperienceSettings } from '@/api/experience'
import { formatSize, formatTime } from '@/utils/format'
import { notifyRequestError } from '@/utils/request'

const loading = ref(false)
const saving = ref(false)
const documentsLoading = ref(false)
const settings = reactive({ account: null, ai_configs: [], ai_used_today: 0, ai_remaining_today: 0 })
const form = reactive({
  enabled: true,
  public_password: 'test1234',
  ai_config_id: null,
  daily_ai_limit: 20,
  show_highlights: true,
  show_notes: true,
  document_ids: [],
})
const documents = ref([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = 50
const search = ref('')
const tableRef = ref()
let searchTimer = null

const applySettings = value => {
  Object.assign(settings, value || {})
  Object.assign(form, {
    enabled: Boolean(value?.enabled),
    public_password: value?.public_password || '',
    ai_config_id: value?.ai_config_id || null,
    daily_ai_limit: Number(value?.daily_ai_limit) || 0,
    show_highlights: Boolean(value?.show_highlights),
    show_notes: Boolean(value?.show_notes),
    document_ids: [...(value?.document_ids || [])],
  })
}

const loadSettings = async () => {
  loading.value = true
  try {
    const response = await getExperienceSettings({ skipErrorToast: true })
    applySettings(response.data)
  } catch (error) {
    notifyRequestError(error, '体验账号配置加载失败')
  } finally {
    loading.value = false
  }
}

const restoreSelections = async () => {
  await nextTick()
  for (const row of documents.value) {
    tableRef.value?.toggleRowSelection?.(row, form.document_ids.includes(row.id))
  }
}

const loadDocuments = async () => {
  documentsLoading.value = true
  try {
    const response = await listExperienceDocuments({
      name: search.value, pageNum: pageNum.value, pageSize,
    }, { skipErrorToast: true })
    documents.value = response.data?.list || []
    total.value = response.data?.total || 0
    await restoreSelections()
  } catch (error) {
    notifyRequestError(error, '可共享文档加载失败')
  } finally {
    documentsLoading.value = false
  }
}

const selectionChanged = rows => {
  const visibleIds = new Set(documents.value.map(item => item.id))
  const selectedVisible = new Set(rows.map(item => item.id))
  form.document_ids = [...new Set([
    ...form.document_ids.filter(id => !visibleIds.has(id)),
    ...documents.value.filter(item => selectedVisible.has(item.id)).map(item => item.id),
  ])]
}

const scheduleSearch = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    pageNum.value = 1
    loadDocuments()
  }, 250)
}

const save = async () => {
  if (saving.value) return
  if (form.public_password.length < 8) return ElMessage.warning('公开密码至少需要 8 位')
  saving.value = true
  try {
    const response = await updateExperienceSettings({ ...form }, { skipErrorToast: true })
    applySettings(response.data)
    ElMessage.success('体验账号配置已保存')
  } catch (error) {
    notifyRequestError(error, '体验账号配置保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadSettings()
  await loadDocuments()
})
onBeforeUnmount(() => clearTimeout(searchTimer))
</script>

<style scoped>
.experience-page { max-width: 1200px; margin: 0 auto; padding-bottom: 30px; }
.page-heading, .document-card > header, .document-card > footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-heading { margin: 4px 2px 16px; }
h1, h2, p { margin-top: 0; }
h1 { margin-bottom: 7px; color: #24384c; font-size: 24px; }
h2 { margin-bottom: 15px; color: #33475e; font-size: 18px; }
.page-heading p, .document-card p { margin-bottom: 0; color: var(--ik-text-sub); }
.settings-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(280px, .8fr); gap: 14px; margin: 14px 0; }
.settings-card, .document-card { padding: 18px; }
.form-hint, .readonly-note { margin-top: 6px; color: var(--ik-text-sub); font-size: 12px; }
.quota-summary { display: flex; flex-wrap: wrap; gap: 12px; padding: 12px; color: var(--ik-text-sub); background: #f4f9fc; border-radius: 10px; }
.quota-summary span { flex: 1; min-width: 110px; }
.quota-summary strong { color: var(--ik-blue); }
.visibility-item { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 0; border-bottom: 1px solid var(--ik-border); }
.visibility-item strong, .visibility-item small { display: block; }
.visibility-item small { margin-top: 5px; color: var(--ik-text-sub); line-height: 1.5; }
.document-card > header { margin-bottom: 12px; }
.document-card > header h2 { margin-bottom: 5px; }
.document-card > header .el-input { width: 280px; }
.document-card > footer { margin-top: 14px; color: var(--ik-text-sub); font-size: 13px; }
@media (max-width: 760px) { .settings-grid { grid-template-columns: 1fr; } .document-card > header, .document-card > footer { align-items: stretch; flex-direction: column; } .document-card > header .el-input { width: 100%; } }
</style>
