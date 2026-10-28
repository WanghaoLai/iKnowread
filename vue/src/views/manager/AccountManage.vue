<template>
  <div>

    <div class="card" style="margin-bottom: 5px;">
      <el-input v-model="data.name" style="width: 300px; margin-right: 10px" placeholder="请输入名称查询" :prefix-icon="Search"></el-input>
      <el-button type="primary" :icon="Search" :loading="loading" @click="load">查询</el-button>
      <el-button type="info" :icon="Refresh" style="margin: 0 10px" @click="reset">重置</el-button>
    </div>

    <div class="card" style="margin-bottom: 5px">
      <div style="margin-bottom: 10px">
        <el-button type="primary" :icon="Plus" @click="handleAdd">新增</el-button>
      </div>
      <el-table v-loading="loading" :data="data.tableData" stripe>
        <el-table-column label="用户名" prop="username">
          <template #default="scope">
            {{ scope.row.username }}
            <el-tag v-if="scope.row.is_experience" size="small" type="warning" effect="plain">体验账号</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="名称" prop="name"></el-table-column>
        <el-table-column label="头像">
          <template #default="scope">
            <el-image v-if="scope.row.avatar" preview-teleported :src="fileUrl(scope.row.avatar)" :preview-src-list="[fileUrl(scope.row.avatar)]" style="width: 40px; height: 40px; border-radius: 50%"></el-image>
          </template>
        </el-table-column>
        <el-table-column label="角色">
          <template #default="scope">{{ scope.row.role === 'admin' ? '管理员' : '用户' }}</template>
        </el-table-column>
        <el-table-column label="操作" align="center" width="220">
          <template #default="scope">
            <el-button type="primary" :icon="Edit" @click="handleEdit(scope.row)">编辑</el-button>
            <el-button type="danger" :icon="Delete" :disabled="scope.row.is_experience" @click="handleDelete(scope.row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="card">
      <el-pagination @current-change="load" background layout="total, prev, pager, next" v-model:page-size="data.pageSize" v-model:current-page="data.pageNum" :total="data.total"/>
    </div>

    <el-dialog :title="title" width="40%" v-model="data.formVisible" :close-on-click-modal="false" destroy-on-close>
      <el-form ref="formRef" :model="data.form" :rules="data.rules" label-width="100px" style="padding-right: 50px">
        <el-form-item label="账号" prop="username">
          <el-input :disabled="data.form.id > 0" v-model="data.form.username" autocomplete="off" />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="data.form.name" autocomplete="off" />
        </el-form-item>
        <el-form-item v-if="!data.form.id" label="初始密码" prop="password">
          <el-input v-model="data.form.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="头像" prop="avatar">
          <el-upload
              list-type="picture"
              :data="uploadData"
              :http-request="uploadAvatar"
              :on-success="avatarHandlers.onSuccess"
              :on-error="avatarHandlers.onError"
          >
            <el-button type="primary" :icon="Upload">上传图片</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
      <span class="dialog-footer">
        <el-button :disabled="data.submitting" @click="data.formVisible = false">取 消</el-button>
        <el-button type="primary" :icon="Check" :loading="data.submitting" @click="save">保 存</el-button>
      </span>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
// 用户/管理员共用同一个账号资源，仅角色筛选条件不同。
import { createAccount, deleteAccount, listAccounts, updateAccount } from '@/api/accounts'
import { notifyRequestError } from '@/utils/request'
import { uploadAvatar } from "@/api/files";
import { fileUrl, avatarUploadHandlers } from "@/utils/file";
import { Search, Refresh, Plus, Edit, Delete, Upload, Check } from "@element-plus/icons-vue";
import { reactive, ref, computed, watch } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
import { useListLoader } from '@/composables/useListLoader'

const props = defineProps({
  role: { type: String, required: true },
  title: { type: String, required: true },      // 编辑弹窗标题
})

// 编辑已有账号时头像直接入该账号目录；新建（无 id）先暂存 temp，由后端 add 归档
const uploadData = computed(() => data.form.id
    ? { account_id: data.form.id, role: props.role }
    : { role: props.role })

const formRef = ref()
const data = reactive({
  pageNum: 1,
  pageSize: 10,
  total: 0,
  formVisible: false,
  form: {},
  tableData: [],
  name: null,
  submitting: false,
  rules: {
    username: [
      { required: true, message: '请输入账号', trigger: 'blur' }
    ],
    name: [
      { required: true, message: '请输入名称', trigger: 'blur' }
    ],
    password: [
      { required: true, message: '请输入至少 8 位的初始密码', min: 8, trigger: 'blur' }
    ],
    avatar: [
      { required: true, message: '请上传头像', trigger: 'blur' }
    ],
  }
})

// 分页查询
const { loading, load: loadList } = useListLoader(
  requestOptions => listAccounts({
      role: props.role,
      pageNum: data.pageNum,
      pageSize: data.pageSize,
      name: data.name,
    }, requestOptions),
  { onError: error => notifyRequestError(error, '账号列表加载失败，请重试') },
)

async function load() {
  const res = await loadList()
  if (!res) return
  data.tableData = res.data?.list
  data.total = res.data?.total
}

// 新增
const handleAdd = () => {
  data.form = {}
  data.formVisible = true
}

// 编辑
const handleEdit = (row) => {
  data.form = JSON.parse(JSON.stringify(row))
  data.formVisible = true
}

// 新增保存
const add = async () => {
  return createAccount({ ...data.form, role: props.role }, {
    skipErrorToast: true,
  })
}

// 编辑保存
const update = async () => {
  return updateAccount(data.form.id, {
    name: data.form.name,
    avatar: data.form.avatar || null,
  }, {
    skipErrorToast: true,
  })
}

// 弹窗保存
const save = async () => {
  if (data.submitting) return
  data.submitting = true
  try {
    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return
    const res = await (data.form.id ? update() : add())
    if (res.code === '200') {
      data.formVisible = false
      ElMessage.success('操作成功')
      await load()
    } else {
      ElMessage.error(res.msg || '账号保存失败')
    }
  } catch (error) {
    await notifyRequestError(error, '账号保存失败，请重试')
  } finally {
    data.submitting = false
  }
}

// 删除
const handleDelete = async (id) => {
  try {
    await ElMessageBox.confirm('删除后数据无法恢复，您确定删除吗?', '删除确认', { type: 'warning' })
  } catch (reason) {
    if (reason !== 'cancel' && reason !== 'close') console.error('删除确认异常:', reason)
    return
  }
  try {
    const res = await deleteAccount(id, { skipErrorToast: true })
    if (res.code === '200') {
      ElMessage.success('操作成功')
      await load()
    } else {
      ElMessage.error(res.msg || '账号删除失败')
    }
  } catch (error) {
    await notifyRequestError(error, '账号删除失败，请重试')
  }
}

// 重置
const reset = () => {
  data.name = null
  load()
}

// 头像上传回调：成功把返回的相对路径写入表单，失败统一提示
const avatarHandlers = avatarUploadHandlers(path => { data.form.avatar = path })

// 两条路由复用同一组件实例，切换 用户信息/管理员信息 时按 role 重新加载
watch(() => props.role, () => {
  data.pageNum = 1
  data.name = null
  load()
})

load()
</script>
