<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-logo"><img src="@/assets/imgs/logo.png" alt="iKnowread"></div>
      <div class="login-title">iKnowread</div>
      <div class="login-sub">欢 迎 登 录</div>
      <el-form ref="formRef" :model="data.form" :rules="data.rules" @submit.prevent="login">
        <el-form-item prop="username">
          <el-input
              v-model="data.form.username"
              :prefix-icon="User"
              size="large"
              placeholder="请输入账号"
              aria-label="账号"
              autocomplete="username"
              @input="clearLoginError"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
              ref="passwordInputRef"
              v-model="data.form.password"
              type="password"
              :prefix-icon="Lock"
              size="large"
              placeholder="请输入密码"
              aria-label="密码"
              autocomplete="current-password"
              show-password
              @input="clearLoginError"
          />
        </el-form-item>
        <el-form-item prop="role">
          <el-select v-model="data.form.role" size="large" style="width: 100%" aria-label="账号类型" @change="clearLoginError">
            <el-option value="admin" label="管理员"></el-option>
            <el-option value="user" label="用户"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item prop="captcha_code">
          <div class="captcha-field">
            <div class="captcha-row">
              <el-input
                  ref="captchaInputRef"
                  :model-value="data.form.captcha_code"
                  size="large"
                  maxlength="5"
                  placeholder="请输入验证码"
                  aria-label="验证码"
                  autocomplete="off"
                  @input="onCaptchaInput"
              />
              <button
                  type="button"
                  class="captcha-image-button"
                  :disabled="captchaLoading"
                  aria-label="看不清，换一张验证码"
                  title="点击换一张"
                  @click="refreshCaptcha(true)"
              >
                <img v-if="captchaImage" :src="captchaImage" alt="随机验证码" draggable="false">
                <span v-else>获取验证码</span>
                <span v-if="captchaLoading" class="captcha-loading"><el-icon class="is-loading"><Refresh /></el-icon></span>
              </button>
            </div>
            <span class="captcha-tip">不区分大小写，点击图片可更换</span>
          </div>
        </el-form-item>
        <el-alert
            v-if="loginError"
            class="login-error"
            :title="loginError"
            type="error"
            show-icon
            :closable="false"
        />
        <el-form-item>
          <el-button
              size="large"
              type="primary"
              native-type="submit"
              style="width: 100%"
              :loading="submitting"
              :disabled="captchaLoading || !captchaImage"
          >{{ submitting ? '登 录 中' : '登 录' }}</el-button>
        </el-form-item>
      </el-form>
      <div v-if="registrationEnabled" class="login-foot">
        还没有账号？请 <router-link to="/register">注册</router-link>
      </div>
    </div>

  </div>
</template>

<script setup>
  import { nextTick, onMounted, reactive, ref } from "vue";
  import { Lock, Refresh, User } from "@element-plus/icons-vue";
  import { getCapabilities, getCaptcha, loginAccount } from '@/api/auth'
  import { ElMessage } from "element-plus";
  import router from "@/router";
  import '@/assets/css/auth.css'
  import { setSession } from '@/utils/session'

  const data = reactive({
    form: { username: '', password: '', role: 'user', captcha_id: '', captcha_code: '' },
    rules: {
      username: [
        { required: true, message: '请输入账号', trigger: 'blur' },
      ],
      password: [
        { required: true, message: '请输入密码', trigger: 'blur' },
      ],
      captcha_code: [
        { required: true, message: '请输入验证码', trigger: 'blur' },
        { len: 5, message: '请输入完整的 5 位验证码', trigger: 'blur' },
      ],
    }
  })

  const formRef = ref()
  const passwordInputRef = ref()
  const captchaInputRef = ref()
  const registrationEnabled = ref(false)
  const submitting = ref(false)
  const loginError = ref('')
  const captchaImage = ref('')
  const captchaLoading = ref(false)

  onMounted(async () => {
    const captchaRequest = refreshCaptcha(false)
    try {
      const res = await getCapabilities({ skipErrorToast: true })
      registrationEnabled.value = Boolean(res.data?.registration_enabled)
    } catch (_) {
      registrationEnabled.value = false
    }
    await captchaRequest
  })

  const clearLoginError = () => {
    loginError.value = ''
  }

  const onCaptchaInput = (value) => {
    data.form.captcha_code = String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 5)
    formRef.value?.clearValidate('captcha_code')
    clearLoginError()
  }

  const refreshCaptcha = async (clearError = true) => {
    if (captchaLoading.value) return false
    captchaLoading.value = true
    data.form.captcha_id = ''
    data.form.captcha_code = ''
    formRef.value?.clearValidate('captcha_code')
    if (clearError) clearLoginError()
    try {
      const res = await getCaptcha({
        params: { timestamp: Date.now() }, timeout: 10000, skipErrorToast: true,
      })
      data.form.captcha_id = res.data?.captcha_id || ''
      captchaImage.value = res.data?.image || ''
      if (!data.form.captcha_id || !captchaImage.value) throw new Error('验证码响应不完整')
      return true
    } catch (_) {
      captchaImage.value = ''
      loginError.value = '验证码加载失败，请点击验证码区域重试'
      return false
    } finally {
      captchaLoading.value = false
    }
  }

  const login = async () => {
    if (submitting.value) return
    data.form.username = data.form.username?.trim() || ''
    clearLoginError()
    try {
      await formRef.value.validate()
    } catch (_) {
      return
    }

    submitting.value = true
    try {
      const res = await loginAccount(data.form, { skipErrorToast: true })
      if (res.code !== '200') {
        loginError.value = res.msg || '登录失败，请稍后重试'
        return
      }
      ElMessage.success('登录成功')
      setSession(res.data)
      await router.push('/manager/home')
    } catch (error) {
      const status = error.response?.status
      const message = status === 401
          ? '账号、密码或账号类型不正确，请检查后重试'
          : (error.response?.data?.msg || error.response?.data?.detail || '登录失败，请稍后重试')
      if (status && status !== 429) {
        const refreshed = await refreshCaptcha(false)
        if (!refreshed) return
      }
      loginError.value = message
      if (status === 401) {
        data.form.password = ''
        await nextTick()
        passwordInputRef.value?.focus()
      } else if (message.includes('验证码')) {
        await nextTick()
        captchaInputRef.value?.focus()
      }
    } finally {
      submitting.value = false
    }
  }

</script>

<style scoped>
/* 样式复用 assets/css/auth.css */
.login-error { margin: -4px 0 18px; }
.login-error :deep(.el-alert__title) { line-height: 1.5; }
.captcha-field { width: 100%; }
.captcha-row { display: flex; align-items: stretch; gap: 10px; }
.captcha-row .el-input { flex: 1; min-width: 0; }
.captcha-image-button {
  position: relative;
  flex: none;
  width: 142px;
  height: 40px;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
  border-radius: 7px;
  color: var(--ik-text-sub);
  background: #f6fafc;
  cursor: pointer;
}
.captcha-image-button:hover:not(:disabled), .captcha-image-button:focus-visible { border-color: var(--ik-cyan-deep); outline: none; }
.captcha-image-button:disabled { cursor: wait; }
.captcha-image-button img { width: 100%; height: 100%; object-fit: cover; user-select: none; }
.captcha-loading { position: absolute; inset: 0; display: grid; place-items: center; color: var(--ik-blue); background: rgba(255, 255, 255, .72); }
.captcha-tip { display: block; margin-top: 5px; color: var(--ik-text-sub); font-size: 11px; line-height: 1.4; }
@media (max-width: 480px) { .captcha-image-button { width: 126px; } }
@media (max-height: 680px) { .login-box { padding-top: 24px; padding-bottom: 22px; } .login-sub { margin-bottom: 18px; } }
</style>
