<template>
  <div>

    <div class="welcome-banner">
      <div class="welcome-title">欢迎回来，{{ data.user.name }}</div>
      <div class="welcome-sub">祝您今天过得开心，阅读愉快！</div>
    </div>

    <div class="card info-card">
      <div class="info-title">iKnowread 管理系统</div>
      <div class="info-line">基于 Vue3 + FastAPI 前后端分离架构</div>
    </div>

  </div>
</template>

<script setup>
import { reactive } from "vue";
import { getSession } from '@/utils/session'

const data = reactive({
  user: getSession(),
})
</script>

<style scoped>
.welcome-banner {
  position: relative;
  overflow: hidden;
  background: var(--ik-gradient);
  border-radius: 14px;
  padding: 30px 32px;
  color: #fff;
  margin-bottom: 12px;
}
.welcome-banner::after {
  content: '';
  position: absolute;
  right: -46px;
  top: -70px;
  width: 230px;
  height: 230px;
  border-radius: 50%;
  background: rgba(255, 255, 255, .12);
}
.welcome-title {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 1px;
}
.welcome-sub {
  margin-top: 8px;
  font-size: 14px;
  opacity: .85;
}
.info-card {
  padding: 24px 32px;
}
.info-title {
  font-size: 16px;
  font-weight: 600;
  color: #24384c;
}
.info-line {
  margin-top: 6px;
  font-size: 14px;
  color: var(--ik-text-sub);
}
</style>
