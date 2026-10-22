<template>
  <div class="layout">
    <header class="layout-header">
      <div class="header-left">
        <button type="button" class="menu-toggle" :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'" @click="toggleMenu">
          <el-icon :size="18"><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
        </button>
        <div class="brand">
          <img class="brand-logo" src="@/assets/imgs/logo.png" alt="iKnowread">
          <span class="brand-name">iKnowread</span>
        </div>
      </div>
      <el-dropdown trigger="click" placement="bottom-end" @command="handleAccountCommand">
        <button type="button" class="header-user" aria-label="账户菜单：个人资料、修改密码、退出系统">
          <img class="header-avatar" :src="fileUrl(data.user.avatar) || DEFAULT_AVATAR" alt="">
          <span class="header-username">{{ data.user.name || data.user.username }}</span>
          <el-icon class="header-arrow"><ArrowDown /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="person" :icon="User">个人资料</el-dropdown-item>
            <el-dropdown-item command="password" :icon="Lock">修改密码</el-dropdown-item>
            <el-dropdown-item command="logout" :icon="SwitchButton" divided>退出系统</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </header>

    <div class="layout-body">
      <aside class="layout-aside" :class="{ collapsed }">
        <el-menu
            class="side-menu"
            router
            :collapse="collapsed"
            :collapse-transition="false"
            :default-active="router.currentRoute.value.path"
            :default-openeds="['user']"
        >
          <el-menu-item index="/manager/home">
            <el-icon><HomeFilled /></el-icon>
            <span>系统首页</span>
          </el-menu-item>
          <el-menu-item index="/manager/document">
            <el-icon><Document /></el-icon>
            <span>我的文档</span>
          </el-menu-item>
          <el-menu-item index="/manager/recycle">
            <el-icon><Delete /></el-icon>
            <span>我的回收站</span>
          </el-menu-item>
          <el-menu-item index="/manager/reader">
            <el-icon><Reading /></el-icon>
            <span>在线阅读</span>
          </el-menu-item>
          <el-menu-item index="/manager/notes">
            <el-icon><Notebook /></el-icon>
            <span>我的笔记</span>
          </el-menu-item>
          <el-menu-item index="/manager/assistant">
            <el-icon><ChatDotRound /></el-icon>
            <span>智能助手</span>
          </el-menu-item>
          <el-menu-item index="/manager/api-config">
            <el-icon><Setting /></el-icon>
            <span>API配置</span>
          </el-menu-item>
          <el-sub-menu index="user" v-if="data.user.role === 'admin'">
            <template #title>
              <el-icon><Avatar /></el-icon>
              <span>用户管理</span>
            </template>
            <el-menu-item index="/manager/admin">
              <el-icon><User /></el-icon>
              <span>管理员信息</span>
            </el-menu-item>
            <el-menu-item index="/manager/user">
              <el-icon><User /></el-icon>
              <span>用户信息</span>
            </el-menu-item>
          </el-sub-menu>
        </el-menu>
      </aside>

      <main
          class="layout-main"
          :class="{ 'layout-main--reader': router.currentRoute.value.path === '/manager/reader' }"
      >
        <router-view @updateUser="updateUser" />
      </main>
    </div>

  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { fileUrl, DEFAULT_AVATAR } from "@/utils/file";
import { logoutAccount } from '@/api/auth'
import router from "@/router";
import {ElMessage} from "element-plus";
import { ArrowDown, Avatar, ChatDotRound, Delete, Document, Expand, Fold, HomeFilled, Lock, Notebook, Reading, Setting, SwitchButton, User } from '@element-plus/icons-vue'
import { clearSession, getSession } from '@/utils/session'

const data = reactive({
  user: getSession()
})

if (!data.user?.id) {
  ElMessage.error('请登录！')
  router.push('/login')
}

// 侧边栏收起状态（记忆到本地，刷新后保持）
const MENU_STATE_KEY = 'iknowread-menu-collapsed'
const collapsed = ref(localStorage.getItem(MENU_STATE_KEY) === '1')
const toggleMenu = () => {
  collapsed.value = !collapsed.value
  localStorage.setItem(MENU_STATE_KEY, collapsed.value ? '1' : '0')
}

const updateUser = () => {
  data.user = getSession()
}

const logout = async () => {
  let serverConfirmed = false
  try {
    await logoutAccount({ skipErrorToast: true })
    serverConfirmed = true
  } catch (error) {
    // 401 表示该服务端会话已经失效，注销目标已经达成。
    serverConfirmed = error.response?.status === 401
    if (!serverConfirmed) {
      ElMessage.warning('本地登录资料已清除，但服务器未确认注销，当前会话可能仍然有效，请稍后重试')
    }
  } finally {
    clearSession()
    await router.push('/login')
  }
  if (serverConfirmed) ElMessage.success('退出成功')
}

const handleAccountCommand = (command) => {
  if (command === 'logout') {
    return logout()
  }
  if (command === 'person' || command === 'password') {
    return router.push(`/manager/${command}`)
  }
}
</script>

<style scoped>
/* 固定壳层：视口高度锁定，顶部栏与侧边栏固定，仅内容区滚动 */
.layout {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 顶部栏 */
.layout-header {
  position: relative;
  flex-shrink: 0;
  height: 60px;
  background: #fff;
  border-bottom: 1px solid var(--ik-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px 0 14px;
}
.layout-header::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--ik-gradient);
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.menu-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #33475e;
  cursor: pointer;
  transition: background-color .2s;
}
.menu-toggle:hover {
  background: #eaf6fb;
}
.menu-toggle:focus-visible {
  outline: 2px solid var(--ik-blue);
  outline-offset: 2px;
}
.brand {
  display: flex;
  align-items: center;
}
.brand-logo {
  width: 38px;
  height: 38px;
  border-radius: 12px;
}
.brand-name {
  margin-left: 10px;
  font-size: 23px;
  font-weight: 700;
  letter-spacing: .5px;
  background: linear-gradient(90deg, #00389d 30%, #0096b4 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
}
.header-user {
  display: flex;
  align-items: center;
  max-width: 240px;
  padding: 4px 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  font: inherit;
  cursor: pointer;
}
.header-user:hover {
  background: #eaf6fb;
}
.header-user:focus-visible {
  outline: 2px solid var(--ik-blue);
  outline-offset: 2px;
}
.header-avatar {
  flex-shrink: 0;
  object-fit: cover;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  border: 2px solid var(--ik-cyan);
}
.header-username {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-left: 8px;
  color: #33475e;
  font-weight: 500;
}
.header-arrow {
  flex-shrink: 0;
  margin-left: 8px;
  color: #33475e;
}

/* 主体区域 */
.layout-body {
  flex: 1;
  min-height: 0;          /* 允许 flex 子项收缩出滚动 */
  display: flex;
  overflow: hidden;
}
.layout-aside {
  flex-shrink: 0;
  width: 210px;
  border-right: 1px solid var(--ik-border);
  background: #fff;
  transition: width .25s;
  overflow: visible;      /* 不裁剪收起态的弹出子菜单 */
}
.layout-aside.collapsed {
  width: 64px;
}
.layout-main {
  flex: 1;
  width: 0;
  min-width: 0;
  min-height: 0;
  background-color: var(--ik-bg);
  padding: 14px;
  overflow-y: auto;       /* 仅内容区滚动 */
  overscroll-behavior: contain;
}
.layout-main--reader {
  overflow: hidden;
  overflow: clip;
}

/* 侧边导航 */
.side-menu {
  border-right: none;
  padding: 10px 8px;
  --el-menu-hover-bg-color: #eaf6fb;
  --el-menu-active-color: var(--ik-blue);
}
.layout-aside.collapsed .side-menu {
  padding: 10px 0;
}
.side-menu :deep(.el-menu-item),
.side-menu :deep(.el-sub-menu__title) {
  height: 46px;
  line-height: 46px;
  border-radius: 10px;
  margin: 3px 0;
  transition: background-color .2s, color .2s;
}
.side-menu :deep(.el-sub-menu .el-menu) {
  background: transparent;
}
.side-menu :deep(.el-menu-item.is-active) {
  background: var(--ik-gradient);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 4px 12px rgba(0, 70, 183, .3);
}
</style>
