<template>
  <div>

    <div class="card" style="margin-bottom: 5px;">
      <el-alert
          class="recycle-tip"
          type="info"
          :closable="false"
          show-icon
          title="恢复文档时会同时恢复原内容版本、高亮及高亮备注"
      />
      <el-input v-model="data.name" style="width: 300px; margin-right: 10px" placeholder="请输入文件名查询" :prefix-icon="Search" @keyup.enter="search"></el-input>
      <el-button type="primary" :icon="Search" @click="search">查询</el-button>
      <el-button type="info" :icon="Refresh" style="margin: 0 10px" @click="reset">重置</el-button>
    </div>

    <div class="card" style="margin-bottom: 5px">
      <el-table v-loading="loading" :data="data.tableData" stripe>
        <el-table-column label="文件名" prop="name" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            <div class="doc-name">
              <el-icon class="doc-icon"><Document /></el-icon>
              <span>{{ scope.row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="格式" align="center" width="90">
          <template #default="scope">
            <el-tag :type="tagType(scope.row.ext)" effect="light">{{ (scope.row.ext || '').toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" align="center" width="110">
          <template #default="scope">{{ formatSize(scope.row.size) }}</template>
        </el-table-column>
        <el-table-column label="删除时间" align="center" width="170">
          <template #default="scope">{{ formatTime(scope.row.deleted_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" align="center" width="220">
          <template #default="scope">
            <el-button
                type="primary"
                size="small"
                :icon="RefreshRight"
                :loading="data.actionId === scope.row.id && data.actionType === 'restore'"
                :disabled="data.actionId !== null && data.actionId !== scope.row.id"
                @click="handleRestore(scope.row)"
            >一键恢复</el-button>
            <el-button
                type="danger"
                size="small"
                :icon="Delete"
                :loading="data.actionId === scope.row.id && data.actionType === 'purge'"
                :disabled="data.actionId !== null && data.actionId !== scope.row.id"
                @click="handlePurge(scope.row)"
            >彻底删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !data.tableData.length" description="回收站是空的，删除的文档会在这里等待恢复" :image-size="90" />
    </div>

    <div class="card">
      <el-pagination @current-change="load" background layout="total, prev, pager, next" v-model:page-size="data.pageSize" v-model:current-page="data.pageNum" :total="data.total"/>
    </div>

  </div>
</template>

<script setup>
import { onBeforeUnmount, reactive } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Search, Refresh, RefreshRight, Delete, Document } from "@element-plus/icons-vue";
import { formatSize, formatTime, documentTagType as tagType } from '@/utils/format'
import { listRecycledDocuments, purgeDocument, restoreDocument } from '@/api/documents'
import { notifyRequestError } from '@/utils/request'
import { useListLoader } from '@/composables/useListLoader'

const data = reactive({
  tableData: [],
  total: 0,
  pageNum: 1,
  pageSize: 10,
  name: null,
  actionId: null,
  actionType: '',
})

const { loading, load: loadList, invalidate } = useListLoader(
  requestOptions => listRecycledDocuments({
      pageNum: data.pageNum,
      pageSize: data.pageSize,
      name: data.name,
    }, requestOptions),
  {
    cancellable: true,
    onError: error => notifyRequestError(error, '回收站加载失败，请重试'),
  },
)

// 分页查询回收站中的文档；旧请求会被取消且不能覆盖新筛选结果。
const load = async () => {
  const res = await loadList()
  if (!res) return false
  data.tableData = res.data?.list || []
  data.total = res.data?.total || 0
  return true
}

const search = () => {
  data.pageNum = 1
  return load()
}

const reloadAfterRemoval = async () => {
  if (!await load()) return
  if (!data.tableData.length && data.pageNum > 1) {
    data.pageNum -= 1
    await load()
  }
}

// 恢复是可逆操作，点击后直接执行，减少无意义的二次确认。
const handleRestore = async (row) => {
  if (data.actionId !== null) return
  data.actionId = row.id
  data.actionType = 'restore'
  try {
    const res = await restoreDocument(row.id)
    if (res.code === '200') {
      await reloadAfterRemoval()
      ElMessage.success(`「${row.name}」及其高亮、备注已恢复`)
    } else {
      ElMessage.error(res.msg || '文档恢复失败，请重试')
    }
  } catch (error) {
    notifyRequestError(error, '文档恢复失败，请重试')
  } finally {
    data.actionId = null
    data.actionType = ''
  }
}

// 彻底删除：文件与高亮内容永久清除，无法再恢复
const handlePurge = async (row) => {
  if (data.actionId !== null) return
  try {
    await ElMessageBox.confirm(
      `彻底删除「${row.name}」后，文件及其高亮、备注将无法恢复，确定删除吗？`,
      '彻底删除',
      { type: 'warning', confirmButtonText: '彻底删除', cancelButtonText: '取消' }
    )
  } catch (_) {
    return
  }
  data.actionId = row.id
  data.actionType = 'purge'
  try {
    const res = await purgeDocument(row.id)
    if (res.code === '200') {
      await reloadAfterRemoval()
      ElMessage.success('已彻底删除')
    } else {
      ElMessage.error(res.msg || '彻底删除失败，请重试')
    }
  } catch (error) {
    notifyRequestError(error, '彻底删除失败，请重试')
  } finally {
    data.actionId = null
    data.actionType = ''
  }
}

const reset = () => {
  data.name = null
  data.pageNum = 1
  load()
}

load()
onBeforeUnmount(invalidate)
</script>

<style scoped>
.recycle-tip { margin-bottom: 14px; }
.doc-name {
  display: flex;
  align-items: center;
}
.doc-icon {
  color: var(--ik-text-sub);
  margin-right: 6px;
  flex-shrink: 0;
}
</style>
