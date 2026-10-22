<template>
  <div style="width: 40%">
    <div class="card" style="padding: 30px">
      <el-form ref="formRef" :model="data.user" :rules="data.rules" label-width="100px" style="padding-right: 50px">
        <div style="margin: 20px 0; text-align: center">
          <el-upload
              :show-file-list="false"
              class="avatar-uploader"
              :data="{ account_id: data.user.id, role: data.user.role }"
              :http-request="uploadAvatar"
              :on-success="avatarHandlers.onSuccess"
              :on-error="avatarHandlers.onError"
          >
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
          <el-button type="primary" :icon="Check" :loading="data.submitting" @click="save">保存</el-button>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import {reactive, ref} from "vue"
import { updateAccount } from '@/api/accounts'
import { notifyRequestError } from '@/utils/request'
import { uploadAvatar } from "@/api/files";
import { fileUrl, avatarUploadHandlers } from "@/utils/file";
import { Check, Plus } from "@element-plus/icons-vue";
import {ElMessage} from "element-plus";
import { getSession, setSession } from '@/utils/session'

const formRef = ref()
const data = reactive({
  user: getSession(),
  submitting: false,
  rules: {
    username: [
      {required: true, message: '请输入账号', trigger: 'blur'}
    ],
    name: [
      {required: true, message: '请输入名称', trigger: 'blur'}
    ],
  }
})

// 头像上传回调：成功把返回的相对路径写入当前用户，失败统一提示
const avatarHandlers = avatarUploadHandlers(path => { data.user.avatar = path })

const emit = defineEmits(["updateUser"])
// 把当前修改的用户信息存储到后台数据库
const save = async () => {
  if (data.submitting) return
  data.submitting = true
  try {
    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return
    if (!['admin', 'user'].includes(data.user.role)) {
      ElMessage.error('当前账号角色无效，请重新登录')
      return
    }
    const res = await updateAccount(data.user.id, {
      name: data.user.name,
      avatar: data.user.avatar || null,
    }, {
      skipErrorToast: true,
    })
    if (res.code === '200') {
      ElMessage.success('更新成功')
      data.user = res.data
      setSession(res.data)
      emit('updateUser')
    } else {
      ElMessage.error(res.msg || '个人资料保存失败')
    }
  } catch (error) {
    await notifyRequestError(error, '个人资料保存失败，请重试')
  } finally {
    data.submitting = false
  }
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
