<template>
  <section class="assistant card" v-loading="loading">
    <header class="chat-heading">
      <div><h1>智能助手</h1><p>{{ config?.has_api_key ? `${config.provider_name} · ${config.model}` : '连接大模型，开始你的提问' }}</p></div>
      <div class="header-actions">
        <el-select v-if="configs.length > 1" v-model="currentConfigId" aria-label="切换当前模型配置" :disabled="sending || switching" :loading="switching" class="model-switch" @change="switchConfig">
          <el-option v-for="item in configs" :key="item.id" :label="`${item.provider_name} · ${item.model}`" :value="item.id" />
        </el-select>
        <el-button :disabled="sending || !messages.length" @click="newChat">新建对话</el-button>
        <el-button @click="router.push('/manager/api-config')">API配置</el-button>
      </div>
    </header>
    <el-alert v-if="loadError" title="无法读取模型配置" type="error" :closable="false">
      <el-button link @click="load">重新加载</el-button>
    </el-alert>
    <el-alert v-else-if="!loading && !config?.has_api_key" title="请先配置你的模型" type="info" :closable="false" show-icon>
      在 API配置页面新增并启用一个模型配置，即可开始对话。
      <el-button link type="primary" @click="router.push('/manager/api-config')">前往配置</el-button>
    </el-alert>
    <div ref="messageList" class="messages" role="log" aria-live="polite" :aria-busy="sending" aria-label="对话记录">
      <div v-if="!messages.length" class="empty-state">
        <el-icon class="assistant-icon"><ChatDotRound /></el-icon>
        <h2>有什么想一起探讨的？</h2>
        <p>解释一个概念、梳理思路，或开始一个新问题。</p>
        <div class="suggestions">
          <button v-for="question in suggestions" :key="question" type="button" :disabled="!config?.has_api_key" @click="draft = question">{{ question }}</button>
        </div>
      </div>
      <article v-for="(message, index) in messages" :key="index" class="message" :class="message.role">
        <img class="message-avatar" :src="message.role === 'user' ? userAvatar : botAvatar" :alt="message.role === 'user' ? '我的头像' : '智能助手头像'">
        <div class="message-main">
          <div class="message-label">{{ message.role === 'user' ? '你' : (message.provider_name ? `${message.provider_name} · ${message.model}` : '智能助手') }}</div>
          <div class="message-content">{{ message.content }}</div>
          <p v-if="message.finish_reason === 'length'" class="truncation">回答已达到输出上限，可以追问“请继续”或增加最大输出 token 数。</p>
        </div>
      </article>
      <div v-if="sending" class="waiting" role="status"><el-icon class="is-loading"><Loading /></el-icon> 正在回答，请稍候…</div>
    </div>
    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" class="error-message" />
    <footer class="composer">
      <label for="assistant-question" class="input-label">你的问题</label>
      <el-input id="assistant-question" v-model="draft" type="textarea" :autosize="{ minRows: 3, maxRows: 7 }" maxlength="8000" show-word-limit
        :disabled="sending || !config?.has_api_key" placeholder="输入问题，Enter 发送，Shift + Enter 换行" @keydown="handleKeydown" />
      <div class="composer-bottom">
        <span>携带最近 20 轮对话；离开或刷新页面后清空。AI 回答请按需核实。</span>
        <el-button type="primary" :icon="Promotion" :loading="sending" :disabled="!canSend" @click="send">发送</el-button>
      </div>
    </footer>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound, Loading, Promotion } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { activateAiConfig, chatWithAi, getActiveAiConfig, listAiConfigs } from '@/api/ai'
import { getSession } from '@/utils/session'
import { fileUrl, DEFAULT_AVATAR } from '@/utils/file'
import botAvatar from '@/assets/imgs/logo.png'

const router = useRouter()
// 智能助手用系统图标；用户用当前登录头像（无头像时回退系统图标）
const userAvatar = fileUrl(getSession().avatar) || DEFAULT_AVATAR
const config = ref(null)
const configs = ref([])
const currentConfigId = ref(null)
const loading = ref(true)
const loadError = ref(false)
const messages = ref([])
const draft = ref('')
const sending = ref(false)
const switching = ref(false)
const errorMessage = ref('')
const messageList = ref()
const suggestions = ['用简单的例子解释第一性原理', '如何高效阅读一篇学术论文？', '帮我制定一个循序渐进的学习计划']
const canSend = computed(() => config.value?.has_api_key && draft.value.trim() && !sending.value)
let controller

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const [activeResponse, configsResponse] = await Promise.all([getActiveAiConfig(), listAiConfigs()])
    config.value = activeResponse.data
    configs.value = configsResponse.data || []
    currentConfigId.value = config.value?.id || null
  }
  catch { loadError.value = true }
  finally { loading.value = false }
}

async function scrollToEnd() {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

function handleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault()
    send()
  }
}

function newChat() {
  messages.value = []
  draft.value = ''
  errorMessage.value = ''
}

async function switchConfig(configId) {
  if (!configId || configId === config.value?.id) return
  switching.value = true
  try {
    const { data } = await activateAiConfig(configId)
    config.value = data
    configs.value = configs.value.map(item => ({ ...item, is_active: item.id === configId }))
    newChat()
    ElMessage.success(`已切换为「${data.name}」，并开始新对话`)
  } catch (_) {
    currentConfigId.value = config.value?.id || null
  } finally {
    switching.value = false
  }
}

async function send() {
  if (!canSend.value) return
  const content = draft.value.trim()
  // 成对保留上下文，避免截断后以 assistant 消息开头。
  const history = messages.value.slice(-40).map(({ role, content }) => ({ role, content }))
  while (history.length && history.reduce((sum, item) => sum + item.content.length, content.length) > 120000) history.splice(0, 2)
  messages.value.push({ role: 'user', content })
  draft.value = ''
  sending.value = true
  errorMessage.value = ''
  controller = new AbortController()
  scrollToEnd()
  try {
    const { data } = await chatWithAi({ messages: [...history, { role: 'user', content }] }, { timeout: 135000, signal: controller.signal })
    messages.value.push({ role: 'assistant', ...data })
  } catch (error) {
    messages.value.pop()
    draft.value = content
    if (error.code !== 'ERR_CANCELED') errorMessage.value = error.response?.data?.msg || '回答失败，问题已保留，请重新发送。'
  } finally {
    sending.value = false
    controller = null
    scrollToEnd()
  }
}

onMounted(load)
onBeforeUnmount(() => controller?.abort())
</script>

<style scoped>
.assistant { display: flex; flex-direction: column; height: calc(100dvh - 88px); min-height: 560px; max-width: 1200px; margin: 0 auto; padding: 24px; }
.chat-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; padding-bottom: 20px; border-bottom: 1px solid var(--ik-border); }
h1 { margin: 0 0 7px; font-size: 24px; }
p { margin: 0; color: var(--ik-text-sub); line-height: 1.7; }
.header-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.header-actions .el-button { margin-left: 0; }
.model-switch { width: 250px; }
.messages { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 24px 4px; }
.empty-state { text-align: center; padding: 40px 8px; }
.assistant-icon { font-size: 38px; color: var(--ik-cyan-deep); background: #eaf6fb; padding: 18px; box-sizing: content-box; border-radius: 22px; }
h2 { font-size: 22px; margin: 20px 0 10px; }
.suggestions { display: flex; justify-content: center; flex-wrap: wrap; gap: 10px; margin-top: 24px; }
.suggestions button { font: inherit; font-size: 13px; color: var(--ik-blue); border: 1px solid var(--ik-border); background: #f5fbff; border-radius: 10px; padding: 12px; cursor: pointer; }
.suggestions button:disabled { color: var(--ik-text-sub); cursor: not-allowed; }
.message { margin-bottom: 24px; max-width: 90%; display: flex; gap: 10px; align-items: flex-start; }
.message.user { margin-left: auto; flex-direction: row-reverse; }
.message-avatar { flex-shrink: 0; width: 36px; height: 36px; object-fit: cover; margin-top: 17px; }
.message.assistant .message-avatar { border-radius: 12px; }
.user .message-avatar { border-radius: 50%; border: 2px solid var(--ik-cyan); }
.message-main { min-width: 0; }
.message-label { color: var(--ik-text-sub); font-size: 12px; margin-bottom: 8px; }
.user .message-label { text-align: right; }
.message-content { padding: 16px 18px; border-radius: 12px; background: #f4f8fb; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.8; }
.user .message-content { background: #e8f4ff; }
.waiting { display: flex; gap: 8px; align-items: center; color: var(--ik-cyan-deep); font-size: 14px; }
.truncation { font-size: 12px; margin-top: 8px; }
.error-message { margin-bottom: 12px; }
.composer { padding-top: 16px; border-top: 1px solid var(--ik-border); }
.input-label { display: block; font-size: 13px; margin-bottom: 8px; }
.composer-bottom { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 12px; }
.composer-bottom span { font-size: 12px; color: var(--ik-text-sub); line-height: 1.6; }
@media (max-width: 800px) { .assistant { padding: 16px; } .empty-state { padding: 20px 0; } .message { max-width: 100%; } .model-switch { width: 100%; } }
</style>
