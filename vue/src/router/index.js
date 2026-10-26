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
        { path: 'assistant', component: () => import('@/views/manager/Assistant.vue'), meta: { denyExperience: true }},
        { path: 'api-config', component: () => import('@/views/manager/ApiConfig.vue'), meta: { denyExperience: true }},
        { path: 'person', component: () => import('@/views/manager/Person.vue'), meta: { denyExperience: true }},
        { path: 'password', component: () => import('@/views/manager/Password.vue'), meta: { denyExperience: true }},
        { path: 'home', component: () => import('@/views/manager/Home.vue')},
        { path: 'document', component: () => import('@/views/manager/Document.vue')},
        { path: 'recycle', component: () => import('@/views/manager/Recycle.vue'), meta: { denyExperience: true }},
        { path: 'reader', component: () => import('@/views/manager/Reader.vue')},
        { path: 'notes', component: () => import('@/views/manager/Notes.vue')},
        { path: 'announcements', component: () => import('@/views/manager/AnnouncementManage.vue'), meta: { requiresAdmin: true }},
        { path: 'experience', component: () => import('@/views/manager/ExperienceManage.vue'), meta: { requiresAdmin: true }},
        { path: 'admin', component: () => import('@/views/manager/AccountManage.vue'), props: { role: 'admin', title: '管理员信息' }, meta: { requiresAdmin: true }},
        { path: 'user', component: () => import('@/views/manager/AccountManage.vue'), props: { role: 'user', title: '用户信息' }, meta: { requiresAdmin: true }},
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
  const requiresAdmin = to.matched.some(record => record.meta.requiresAdmin)
  const denyExperience = to.matched.some(record => record.meta.denyExperience)
  if (to.path.startsWith('/manager') && !user.id) return '/login'
  if (to.path.startsWith('/manager')) {
    if (Date.now() - lastVerifiedAt < VERIFY_TTL_MS) {
      if (requiresAdmin && user.role !== 'admin') {
        return '/manager/home'
      }
      if (denyExperience && user.is_experience) return '/manager/home'
      return
    }
    try {
      const verifiedUser = await fetchVerifiedSession(import.meta.env.VITE_BASE_URL || '')
      setSession(verifiedUser)
      lastVerifiedAt = Date.now()
      if (requiresAdmin && verifiedUser.role !== 'admin') {
        return '/manager/home'
      }
      if (denyExperience && verifiedUser.is_experience) return '/manager/home'
    } catch (_) {
      lastVerifiedAt = 0
      clearSession()
      return '/login'
    }
  }
})

export default router
