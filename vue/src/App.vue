<template>
  <el-config-provider :locale="zhCn">
    <div class="app-shell">
      <main class="app-content">
        <RouterView />
      </main>
      <AppFooter />
    </div>
  </el-config-provider>
</template>

<script setup>
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import AppFooter from '@/components/AppFooter.vue'
</script>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

.app-content {
  flex: 1;
  min-height: 0;
}

.app-content > :deep(*) {
  height: 100%;
}
</style>
