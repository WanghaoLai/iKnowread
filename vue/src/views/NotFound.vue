<template>
  <div class="not-found">
    <div class="not-found-card card">
      <h1>404</h1>
      <p>页面不存在或已被移除</p>
      <el-button type="primary" @click="goHome">返回首页</el-button>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { getSession } from '@/utils/session'

const router = useRouter()
const goHome = () => router.push(getSession().id ? '/manager/home' : '/login')
</script>

<style scoped>
.not-found {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ik-bg, #f2f7fb);
}
.not-found-card {
  text-align: center;
  padding: 48px 64px;
}
.not-found-card h1 {
  margin: 0 0 8px;
  font-size: 64px;
  color: var(--ik-blue, #1f6feb);
  letter-spacing: 4px;
}
.not-found-card p {
  margin: 0 0 22px;
  color: var(--ik-text-sub, #7b93a8);
}
</style>
