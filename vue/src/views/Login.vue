<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-logo"><img src="@/assets/imgs/logo.png" alt="iKnowread"></div>
      <div class="login-title">iKnowread</div>
      <div class="login-sub">欢 迎 登 录</div>
      <el-form :model="data.form"  ref="formRef" :rules="data.rules">
        <el-form-item prop="username">
          <el-input :prefix-icon="User" size="large" v-model="data.form.username" placeholder="请输入账号" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input :prefix-icon="Lock" size="large" v-model="data.form.password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item prop="role">
          <el-select size="large" style="width: 100%" v-model="data.form.role">
            <el-option value="admin" label="管理员"></el-option>
            <el-option value="user" label="用户"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button size="large" type="primary" style="width: 100%" @click="login">登 录</el-button>
        </el-form-item>
      </el-form>
      <div v-if="registrationEnabled" class="login-foot">
        还没有账号？请 <router-link to="/register">注册</router-link>
      </div>
    </div>

  </div>
</template>

<script setup>
  import { onMounted, reactive, ref } from "vue";
  import { User, Lock } from "@element-plus/icons-vue";
  import request from "@/utils/request";
  import {ElMessage} from "element-plus";
  import router from "@/router";
  import '@/assets/css/auth.css'
  import { setSession } from '@/utils/session'

  const data = reactive({
    form: { role: 'user' },
    rules: {
      username: [
        { required: true, message: '请输入账号', trigger: 'blur' },
      ],
      password: [
        { required: true, message: '请输入密码', trigger: 'blur' },
      ],
    }
  })

  const formRef = ref()
  const registrationEnabled = ref(false)

  onMounted(async () => {
    try {
      const res = await request.get('/capabilities')
      registrationEnabled.value = Boolean(res.data?.registration_enabled)
    } catch (_) {
      registrationEnabled.value = false
    }
  })

  // 点击登录按钮的时候会触发这个方法
  const login = () => {
    formRef.value.validate((valid => {
      if (valid) {
        // 调用后台的接口
        request.post('/login', data.form).then(res => {
          if (res.code === '200') {
            ElMessage.success("登录成功")
            setSession(res.data)
            router.push('/manager/home')
          } else {
            ElMessage.error(res.msg)
          }
        })
      }
    })).catch(error => {
      console.error(error)
    })
  }

</script>

<style scoped>
/* 样式复用 assets/css/auth.css */
</style>
