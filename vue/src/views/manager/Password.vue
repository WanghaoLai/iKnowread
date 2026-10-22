<template>
  <div style="width: 40%">
    <div class="card" style="padding: 30px">
      <el-form ref="formRef" :rules="data.rules" :model="data.user" label-width="100px" style="padding-right: 50px">
        <el-form-item label="原密码" prop="password">
          <el-input v-model="data.user.password" type="password" autocomplete="current-password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="data.user.newPassword" type="password" autocomplete="new-password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input v-model="data.user.confirmPassword" type="password" autocomplete="new-password" show-password />
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
import { updatePassword } from '@/api/auth'
import { notifyRequestError } from '@/utils/request'
import { Check } from "@element-plus/icons-vue";
import {ElMessage} from "element-plus";
import router from "@/router";
import { clearSession } from '@/utils/session'

const formRef = ref()
const data = reactive({
  user: {},
  submitting: false,
  rules: {
    password: [
      {required: true, message: '请输入原密码', trigger: 'blur'}
    ],
    newPassword: [
      {required: true, message: '请输入新密码', trigger: 'blur'},
      {min: 8, message: '新密码至少需要 8 位', trigger: 'blur'}
    ],
    confirmPassword: [
      {required: true, message: '请确认新密码', trigger: 'blur'}
    ],
  }
})

// 把当前修改的用户信息存储到后台数据库
const save = async () => {
  if (data.submitting) return
  data.submitting = true
  try {
    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return
    if (data.user.password === data.user.newPassword) {
      ElMessage.error('新密码不能和原密码一致')
      return
    }
    if (data.user.newPassword !== data.user.confirmPassword) {
      ElMessage.error('确认新密码错误')
      return
    }
    const res = await updatePassword({
      password: data.user.password,
      newPassword: data.user.newPassword,
    }, {
      skipErrorToast: true,
    })
    if (res.code === '200') {
      ElMessage.success('修改密码成功')
      clearSession()
      await router.push('/login')
    } else {
      ElMessage.error(res.msg || '密码修改失败')
    }
  } catch (error) {
    await notifyRequestError(error, '密码修改失败，请重试')
  } finally {
    data.submitting = false
  }
}
</script>
