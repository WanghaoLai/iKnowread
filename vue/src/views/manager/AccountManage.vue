<template>
  <div>

    <div class="card" style="margin-bottom: 5px;">
      <el-input v-model="data.name" style="width: 300px; margin-right: 10px" placeholder="请输入名称查询" :prefix-icon="Search"></el-input>
      <el-button type="primary" :icon="Search" @click="load">查询</el-button>
      <el-button type="info" :icon="Refresh" style="margin: 0 10px" @click="reset">重置</el-button>
    </div>

    <div class="card" style="margin-bottom: 5px">
      <div style="margin-bottom: 10px">
        <el-button type="primary" :icon="Plus" @click="handleAdd">新增</el-button>
      </div>
      <el-table :data="data.tableData" stripe>
        <el-table-column label="用户名" prop="username"></el-table-column>
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
            <el-button type="danger" :icon="Delete" @click="handleDelete(scope.row.id)">删除</el-button>
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
          <el-input v-model="data.form.password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="头像" prop="avatar">
          <el-upload :action="uploadUrl" list-type="picture" :data="uploadData" :on-success="handleImgSuccess">
            <el-button type="primary" :icon="Upload">上传图片</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
      <span class="dialog-footer">
        <el-button @click="data.formVisible = false">取 消</el-button>
        <el-button type="primary" :icon="Check" @click="save">保 存</el-button>
      </span>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
// 用户/管理员共用同一个账号资源，仅角色筛选条件不同。
import request from "@/utils/request";
import { fileUrl } from "@/utils/file";
import { Search, Refresh, Plus, Edit, Delete, Upload, Check } from "@element-plus/icons-vue";
import { reactive, ref, computed, watch } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";

const props = defineProps({
  role: { type: String, required: true },
  title: { type: String, required: true },      // 编辑弹窗标题
})

// 文件上传的接口地址
const uploadUrl = import.meta.env.VITE_BASE_URL + '/files/upload'
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
const load = () => {
  request.get('/accounts', {
    params: {
      role: props.role,
      pageNum: data.pageNum,
      pageSize: data.pageSize,
      name: data.name
    }
  }).then(res => {
    data.tableData = res.data?.list
    data.total = res.data?.total
  })
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
const add = () => {
  request.post('/accounts', { ...data.form, role: props.role }).then(res => {
    if (res.code === '200') {
      load()
      ElMessage.success('操作成功')
      data.formVisible = false
    } else {
      ElMessage.error(res.msg)
    }
  })
}

// 编辑保存
const update = () => {
  request.put('/accounts/' + data.form.id, {
    name: data.form.name,
    avatar: data.form.avatar || null,
  }).then(res => {
    if (res.code === '200') {
      load()
      ElMessage.success('操作成功')
      data.formVisible = false
    } else {
      ElMessage.error(res.msg)
    }
  })
}

// 弹窗保存
const save = () => {
  formRef.value.validate(valid => {
    if (valid) {
      // data.form有id就是更新，没有就是新增
      data.form.id ? update() : add()
    }
  })
}

// 删除
const handleDelete = (id) => {
  ElMessageBox.confirm('删除后数据无法恢复，您确定删除吗?', '删除确认', { type: 'warning' }).then(res => {
    request.delete('/accounts/' + id).then(res => {
      if (res.code === '200') {
        load()
        ElMessage.success('操作成功')
      } else {
        ElMessage.error(res.msg)
      }
    })
  }).catch(err => {
    // 用户主动取消属正常流程，其余异常要有迹可查
    if (err !== 'cancel' && err !== 'close') console.error('删除确认异常:', err)
  })
}

// 重置
const reset = () => {
  data.name = null
  load()
}

// 处理文件上传的钩子
const handleImgSuccess = (res) => {
  data.form.avatar = res.data  // res.data就是文件上传返回的文件路径，获取到路径后赋值表单的属性
}

// 两条路由复用同一组件实例，切换 用户信息/管理员信息 时按 role 重新加载
watch(() => props.role, () => {
  data.pageNum = 1
  data.name = null
  load()
})

load()
</script>
