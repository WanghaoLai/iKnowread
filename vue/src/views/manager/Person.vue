<template>
  <div style="width: 40%">
    <div class="card" style="padding: 30px">
      <el-form ref="formRef" :model="data.user" :rules="data.rules" label-width="100px" style="padding-right: 50px">
        <div style="margin: 20px 0; text-align: center">
          <el-upload :show-file-list="false" class="avatar-uploader" :action="uploadUrl" :data="{ account_id: data.user.id, role: data.user.role }" :on-success="handleFileUpload">
            <img v-if="data.user.avatar" :src="fileUrl(data.user.avatar)" class="avatar" />
            <el-icon v-else class="avatar-uploader-icon"><Plus /></el-icon>
          </el-upload>
        </div>
        <el-form-item label="账号" prop="username">
          <el-input disabled v-model="data.user.username" autocomplete="off" />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="data.user.name" autocomplete="off" />
        </el-form-item>
        <div style="text-align: center">
          <el-button type="primary" :icon="Check" @click="save">保存</el-button>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import {reactive, ref} from "vue"
import request from "@/utils/request";
import { fileUrl } from "@/utils/file";
import { Check, Plus } from "@element-plus/icons-vue";
import {ElMessage} from "element-plus";
import { getSession, setSession } from '@/utils/session'

// 文件上传的接口地址
const uploadUrl = import.meta.env.VITE_BASE_URL + '/files/upload'

const formRef = ref()
const data = reactive({
  user: getSession(),
  rules: {
    username: [
      {required: true, message: '请输入账号', trigger: 'blur'}
    ],
    name: [
      {required: true, message: '请输入名称', trigger: 'blur'}
    ],
  }
})

const handleFileUpload = (file) => {
  data.user.avatar = file.data
}

const emit = defineEmits(["updateUser"])
// 把当前修改的用户信息存储到后台数据库
const save = () => {
  formRef.value.validate(valid => {
    if (valid) {
      if (['admin', 'user'].includes(data.user.role)) {
        request.put('/accounts/' + data.user.id, {
          name: data.user.name,
          avatar: data.user.avatar || null,
        }).then(res => {
          if (res.code === '200') {
            ElMessage.success('更新成功')
            //把更新后的用户信息存储到缓存
            data.user = res.data
            setSession(res.data)
            emit('updateUser')
          } else {
            ElMessage.error(res.msg)
          }
        })
      }
    }
  })
}
</script>

<style scoped>
.avatar-uploader .avatar {
  width: 120px;
  height: 120px;
  display: block;
  border-radius: 12px;
}
</style>

<style>
.avatar-uploader .el-upload {
  border: 1px dashed #b3c7e9;
  border-radius: 12px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: border-color .25s;
}

.avatar-uploader .el-upload:hover {
  border-color: var(--ik-cyan-deep);
}

.el-icon.avatar-uploader-icon {
  font-size: 28px;
  color: #9db4c8;
  width: 120px;
  height: 120px;
  text-align: center;
}
</style>
