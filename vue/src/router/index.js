import {createRouter, createWebHistory} from 'vue-router'
import { clearSession, getSession, setSession } from '@/utils/session'
import { fetchVerifiedSession } from './sessionGuard.js'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/login' },
    {
      path: '/manager',
      component: () => import('@/views/Manager.vue'),
      redirect: '/manager/home',
      children: [
        { path: 'assistant', component: () => import('@/views/manager/Assistant.vue')},
        { path: 'api-config', component: () => import('@/views/manager/ApiConfig.vue')},
        { path: 'person', component: () => import('@/views/manager/Person.vue')},
        { path: 'password', component: () => import('@/views/manager/Password.vue')},
        { path: 'home', component: () => import('@/views/manager/Home.vue')},
        { path: 'document', component: () => import('@/views/manager/Document.vue')},
        { path: 'recycle', component: () => import('@/views/manager/Recycle.vue')},
        { path: 'reader', component: () => import('@/views/manager/Reader.vue')},
        { path: 'notes', component: () => import('@/views/manager/Notes.vue')},
        { path: 'admin', component: () => import('@/views/manager/AccountManage.vue'), props: { role: 'admin', title: '管理员信息' }},
        { path: 'user', component: () => import('@/views/manager/AccountManage.vue'), props: { role: 'user', title: '用户信息' }},
      ]
    },
    { path: '/login', component: () => import('@/views/Login.vue')},
    { path: '/register', component: () => import('@/views/Register.vue')},
    { path: '/:pathMatch(.*)*', component: () => import('@/views/NotFound.vue')},
  ]
})

// 会话校验短缓存：60s 内多次导航复用上次 /me 结果，避免每次切菜单都打一次接口
const VERIFY_TTL_MS = 60_000
let lastVerifiedAt = 0

router.beforeEach(async (to) => {
  const user = getSession()
  if (to.path.startsWith('/manager') && !user.id) return '/login'
  if (to.path.startsWith('/manager')) {
    if (Date.now() - lastVerifiedAt < VERIFY_TTL_MS) {
      if (['/manager/admin', '/manager/user'].includes(to.path) && user.role !== 'admin') {
        return '/manager/home'
      }
      return
    }
    try {
      const verifiedUser = await fetchVerifiedSession(import.meta.env.VITE_BASE_URL || '')
      setSession(verifiedUser)
      lastVerifiedAt = Date.now()
      if (['/manager/admin', '/manager/user'].includes(to.path) && verifiedUser.role !== 'admin') {
        return '/manager/home'
      }
    } catch (_) {
      lastVerifiedAt = 0
      clearSession()
      return '/login'
    }
  }
})

export default router
