<template>
  <footer class="app-footer" aria-label="网站版权和备案信息">
    <span>© 2026 iKnowread开发团队</span>
    <span class="app-footer-divider" aria-hidden="true"></span>
    <a
      href="https://beian.miit.gov.cn/"
      target="_blank"
      rel="noopener noreferrer"
    >赣ICP备2026027332号-1</a>
    <span class="app-footer-divider" aria-hidden="true"></span>
    <a
      class="app-footer-police-record"
      href="https://beian.mps.gov.cn/#/query/webSearch?code=36073202361022"
      target="_blank"
      rel="noopener noreferrer"
    >
      <img :src="publicSecurityIcon" alt="" width="18" height="20">
      <span>赣公网安备36073202361022号</span>
    </a>
  </footer>
</template>

<script setup>
import publicSecurityIcon from '@/assets/imgs/public-security-record.png'
</script>

<style scoped>
.app-footer {
  position: relative;
  z-index: 10;
  flex-shrink: 0;
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 8px 16px;
  border-top: 1px solid rgba(0, 69, 183, .12);
  background: #fff;
  color: var(--ik-text-sub);
  font-size: 13px;
  line-height: 1.5;
  text-align: center;
}

.app-footer a {
  color: var(--ik-text-sub);
  font-weight: 500;
}

.app-footer a:hover {
  color: var(--ik-cyan-deep);
  text-decoration: underline;
}

.app-footer a:focus-visible {
  border-radius: 3px;
  outline: 2px solid var(--ik-blue);
  outline-offset: 2px;
}

.app-footer-divider {
  width: 1px;
  height: 14px;
  background: var(--ik-border);
}

.app-footer-police-record {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.app-footer-police-record img {
  width: 18px;
  height: 20px;
  flex-shrink: 0;
  object-fit: contain;
}

@media (max-width: 520px) {
  .app-footer {
    gap: 2px;
    padding: 6px 12px;
    font-size: 12px;
  }

  .app-footer span:first-child,
  .app-footer a {
    flex-basis: 100%;
  }

  .app-footer-police-record span {
    flex-basis: auto;
  }

  .app-footer-divider {
    display: none;
  }
}
</style>
