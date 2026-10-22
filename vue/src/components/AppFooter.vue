<template>
  <footer class="app-footer" aria-label="网站版权和备案信息">
    <span>© 2026 iKnowread开发团队</span>
    <span class="app-footer-divider" aria-hidden="true"></span>
    <a
      href="https://beian.miit.gov.cn/"
      target="_blank"
      rel="noopener noreferrer"
    >赣ICP备2026027332号-1</a>
  </footer>
</template>

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
  color: var(--ik-blue);
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

  .app-footer-divider {
    display: none;
  }
}
</style>
