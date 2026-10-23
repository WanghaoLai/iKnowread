<template>
  <section class="announcement-page">
    <header class="page-heading">
      <div>
        <h1>公告管理</h1>
        <p>编辑系统通知并控制发布时间；修改已发布公告会作为新版本再次提醒用户。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增公告</el-button>
    </header>

    <div class="filters card">
      <el-input
        v-model="filters.keyword"
        clearable
        :prefix-icon="Search"
        placeholder="按标题搜索"
        @keyup.enter="search"
      />
      <el-select v-model="filters.status" clearable placeholder="全部状态">
        <el-option label="草稿" value="draft" />
        <el-option label="已发布" value="published" />
        <el-option label="已下架" value="offline" />
      </el-select>
      <el-button type="primary" :icon="Search" :loading="loading" @click="search">查询</el-button>
      <el-button :icon="Refresh" @click="reset">重置</el-button>
    </div>

    <div class="table-card card">
      <el-table v-loading="loading" :data="rows" stripe empty-text="暂无公告">
        <el-table-column label="标题" min-width="250">
          <template #default="{ row }">
            <div class="title-cell">
              <strong>{{ row.title }}</strong>
              <span>创建人：{{ row.created_by_name || '已删除账号' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="105">
          <template #default="{ row }">
            <el-tag :type="announcementStatus(row.status).type">{{ announcementStatus(row.status).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发布版本" width="100" align="center">
          <template #default="{ row }">{{ row.published_revision || '-' }}</template>
        </el-table-column>
        <el-table-column label="发布时间" width="180">
          <template #default="{ row }">{{ formatTime(row.published_at) }}</template>
        </el-table-column>
        <el-table-column label="最后更新" width="180">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
            <el-button
              v-if="row.status !== 'published'"
              link
              type="success"
              :loading="changingId === row.id"
              @click="changeStatus(row, 'published')"
            >{{ row.published_revision ? '重新发布' : '发布' }}</el-button>
            <el-button
              v-else
              link
              type="warning"
              :loading="changingId === row.id"
              @click="changeStatus(row, 'offline')"
            >下架</el-button>
            <el-button link type="danger" :icon="Delete" :loading="deletingId === row.id" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="pagination.pageNum"
          v-model:page-size="pagination.pageSize"
          background
          layout="total, sizes, prev, pager, next"
          :page-sizes="[10, 20, 50]"
          :total="pagination.total"
          @current-change="load"
          @size-change="changePageSize"
        />
      </div>
    </div>

    <AnnouncementEditorDialog
      v-model="editorVisible"
      :announcement="editing"
      :submitting="submitting"
      @submit="save"
    />
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Delete, Edit, Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AnnouncementEditorDialog from '@/components/AnnouncementEditorDialog.vue'
import {
  createAnnouncement,
  deleteAnnouncement,
  listAdminAnnouncements,
  updateAnnouncement,
  updateAnnouncementStatus,
} from '@/api/announcements'
import { useListLoader } from '@/composables/useListLoader'
import { announcementStatus } from '@/utils/announcements'
import { formatTime } from '@/utils/format'
import { notifyRequestError } from '@/utils/request'

const filters = reactive({ keyword: '', status: '' })
const pagination = reactive({ pageNum: 1, pageSize: 10, total: 0 })
const rows = ref([])
const editorVisible = ref(false)
const editing = ref(null)
const submitting = ref(false)
const changingId = ref(null)
const deletingId = ref(null)

const { loading, load: loadList, invalidate } = useListLoader(
  signal => listAdminAnnouncements({
    keyword: filters.keyword.trim(),
    status: filters.status || undefined,
    pageNum: pagination.pageNum,
    pageSize: pagination.pageSize,
  }, { signal, skipErrorToast: true }),
  {
    cancellable: true,
    onError: error => {
      if (error?.code !== 'ERR_CANCELED') notifyRequestError(error, '公告列表加载失败，请重试')
    },
  },
)

async function load() {
  const response = await loadList()
  if (!response) return
  rows.value = response.data?.list || []
  pagination.total = Number(response.data?.total || 0)
  if (!rows.value.length && pagination.pageNum > 1) {
    pagination.pageNum -= 1
    await load()
  }
}

function search() {
  pagination.pageNum = 1
  load()
}

function reset() {
  filters.keyword = ''
  filters.status = ''
  search()
}

function changePageSize() {
  pagination.pageNum = 1
  load()
}

function openCreate() {
  editing.value = null
  editorVisible.value = true
}

function openEdit(row) {
  editing.value = { ...row }
  editorVisible.value = true
}

async function save(payload) {
  if (submitting.value) return
  const changed = !editing.value
    || editing.value.title !== payload.title
    || editing.value.content !== payload.content
  if (!changed) {
    editorVisible.value = false
    ElMessage.info('公告内容没有变化')
    return
  }
  submitting.value = true
  try {
    if (editing.value) await updateAnnouncement(editing.value.id, payload, { skipErrorToast: true })
    else await createAnnouncement(payload, { skipErrorToast: true })
    editorVisible.value = false
    ElMessage.success(editing.value?.status === 'published' ? '公告已更新并重新提醒用户' : '公告保存成功')
    await load()
  } catch (error) {
    await notifyRequestError(error, '公告保存失败，请重试')
  } finally {
    submitting.value = false
  }
}

async function changeStatus(row, status) {
  const publishing = status === 'published'
  const message = publishing
    ? `${row.published_revision ? '重新发布' : '发布'}后，所有用户都会收到未读提醒。确定继续吗？`
    : '下架后用户通知面板将不再显示该公告，确定继续吗？'
  try {
    await ElMessageBox.confirm(message, publishing ? '发布公告' : '下架公告', {
      type: 'warning',
      confirmButtonText: publishing ? '确认发布' : '确认下架',
    })
  } catch (_) { return }
  changingId.value = row.id
  try {
    await updateAnnouncementStatus(row.id, status, { skipErrorToast: true })
    ElMessage.success(publishing ? '公告已发布' : '公告已下架')
    await load()
  } catch (error) {
    await notifyRequestError(error, '公告状态更新失败，请重试')
  } finally {
    changingId.value = null
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除公告“${row.title}”吗？该操作无法恢复。`, '删除公告', {
      type: 'warning',
      confirmButtonText: '确认删除',
    })
  } catch (_) { return }
  deletingId.value = row.id
  try {
    await deleteAnnouncement(row.id, { skipErrorToast: true })
    ElMessage.success('公告已删除')
    await load()
  } catch (error) {
    await notifyRequestError(error, '公告删除失败，请重试')
  } finally {
    deletingId.value = null
  }
}

onMounted(load)
onBeforeUnmount(invalidate)
</script>

<style scoped>
.announcement-page { max-width: 1440px; margin: 0 auto; }
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin: 4px 2px 18px; }
.page-heading h1 { margin: 0 0 7px; color: #182b49; font-size: 25px; }
.page-heading p { margin: 0; color: #738297; }
.filters { display: grid; grid-template-columns: minmax(240px, 380px) 160px auto auto 1fr; align-items: center; gap: 10px; margin-bottom: 14px; }
.table-card { padding-bottom: 12px; }
.title-cell { display: flex; flex-direction: column; gap: 5px; }
.title-cell strong { color: #26394f; }
.title-cell span { color: #8a97a8; font-size: 12px; }
.pagination-wrap { display: flex; justify-content: flex-end; padding-top: 14px; }
@media (max-width: 760px) {
  .page-heading { align-items: flex-start; }
  .filters { grid-template-columns: 1fr 1fr; }
}
</style>
