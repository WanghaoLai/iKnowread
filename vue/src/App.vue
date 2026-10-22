<template>
  <div class="app-shell">
    <main class="app-content">
      <RouterView />
    </main>
    <AppFooter />
  </div>
</template>

<script setup>
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
