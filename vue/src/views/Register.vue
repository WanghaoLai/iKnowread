<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-logo"><img src="@/assets/imgs/logo.png" alt="iKnowread"></div>
      <div class="login-title">iKnowread</div>
      <div class="login-sub">欢 迎 注 册</div>
      <el-form :model="data.form" ref="formRef" :rules="data.rules" @submit.prevent="register">
        <el-form-item prop="username">
          <el-input :prefix-icon="User" size="large" v-model="data.form.username" placeholder="请输入账号" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input :prefix-icon="Lock" size="large" v-model="data.form.password" type="password" autocomplete="new-password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item prop="confirmPassword">
          <el-input :prefix-icon="Lock" size="large" v-model="data.form.confirmPassword" type="password" autocomplete="new-password" placeholder="请确认密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-button size="large" type="primary" native-type="submit" style="width: 100%" :loading="submitting">注 册</el-button>
        </el-form-item>
      </el-form>
      <div class="login-foot">
        已有账号？请 <router-link to="/login">登录</router-link>
      </div>
    </div>

  </div>
</template>

<script setup>
  import { onMounted, reactive, ref } from "vue";
  import { User, Lock } from "@element-plus/icons-vue";
  import request, { notifyRequestError } from "@/utils/request";
  import {ElMessage} from "element-plus";
  import router from "@/router";
  import '@/assets/css/auth.css'

  const validatePass = (rule, value, callback) => {
    if (!value) {
      callback(new Error('请确认密码'))
    } else if (value !== data.form.password) {
      callback(new Error('两次输入密码不一致'))
    } else {
      callback()
    }
  }

  const data = reactive({
    form: {},
    rules: {
      username: [
        { required: true, message: '请输入账号', trigger: 'blur' },
      ],
      password: [
        { required: true, message: '请输入密码', trigger: 'blur' },
        { min: 8, message: '密码至少需要 8 位', trigger: 'blur' },
      ],
      confirmPassword: [
        { validator: validatePass, trigger: 'blur' },
      ],
    }
  })


  const formRef = ref()
  const submitting = ref(false)

  onMounted(async () => {
    try {
      const res = await request.get('/capabilities')
      if (!res.data?.registration_enabled) {
        ElMessage.info('当前系统未开放自助注册')
        router.replace('/login')
      }
    } catch (_) {
      router.replace('/login')
    }
  })

  // 点击注册按钮的时候会触发这个方法
  const register = async () => {
    if (submitting.value) return
    try {
      await formRef.value.validate()
    } catch (_) {
      return
    }
    submitting.value = true
    try {
      const res = await request.post('/register', {
        username: data.form.username?.trim(),
        password: data.form.password,
      })
      if (res.code === '200') {
        ElMessage.success('注册成功')
        await router.push('/login')
      } else {
        ElMessage.error(res.msg || '注册失败，请稍后重试')
      }
    } catch (error) {
      notifyRequestError(error, '注册失败，请稍后重试')
    } finally {
      submitting.value = false
    }
  }

</script>

<style scoped>
/* 样式复用 assets/css/auth.css */
</style>
