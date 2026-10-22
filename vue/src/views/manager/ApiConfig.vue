<template>
  <section class="config-page" v-loading="loading">
    <div class="page-heading">
      <div><h1>API配置</h1><p>统一管理不同厂商的模型配置，并指定系统当前使用的模型。</p></div>
      <el-button @click="router.push('/manager/assistant')">前往智能助手</el-button>
    </div>
    <el-alert v-if="loadError" title="配置加载失败，请重试" type="error" :closable="false" class="load-error">
      <el-button link @click="load">重新加载</el-button>
    </el-alert>
    <div v-else class="config-layout">
      <aside class="config-list card" aria-label="已保存的模型配置">
        <div class="list-heading">
          <div><strong>模型配置</strong><span>{{ configs.length }} 项</span></div>
          <el-button type="primary" plain size="small" :icon="Plus" @click="newConfig">新增</el-button>
        </div>
        <div v-if="!configs.length" class="list-empty">
          <el-icon><Connection /></el-icon><p>还没有模型配置</p><span>新增后即可用于智能助手和文档解释。</span>
        </div>
        <button v-for="item in configs" :key="item.id" type="button" class="config-item"
          :class="{ selected: selectedId === item.id, active: item.is_active }" @click="selectConfig(item)">
          <span class="item-top"><strong>{{ item.name }}</strong><el-tag v-if="item.is_active" size="small" type="success">当前使用</el-tag></span>
          <span class="item-meta">{{ item.provider_name }} · {{ item.model }}</span>
          <span class="item-actions">
            <span>{{ item.has_api_key ? '密钥已保存' : '缺少密钥' }}</span>
            <el-button v-if="!item.is_active" link type="primary" size="small" :loading="activatingId === item.id" @click.stop="activate(item)">设为当前</el-button>
          </span>
        </button>
      </aside>

      <main class="editor card">
        <div class="editor-heading">
          <div><h2>{{ selectedId ? '编辑模型配置' : '新增模型配置' }}</h2><p>{{ selectedConfig?.is_active ? '此配置正用于智能助手和文档解释。' : '保存后可测试连接，再设为系统当前使用。' }}</p></div>
          <el-tag v-if="selectedConfig?.is_active" type="success">当前使用</el-tag>
        </div>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="busy" class="config-form">
          <div class="form-grid">
            <el-form-item label="配置名称" prop="name"><el-input v-model="form.name" maxlength="100" placeholder="例如：日常问答 · MiMo" /></el-form-item>
            <el-form-item label="模型服务商" prop="provider">
              <el-select v-model="form.provider" style="width: 100%" @change="changeProvider">
                <el-option v-for="provider in providers" :key="provider.id" :label="provider.name" :value="provider.id" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="接口地址（Base URL）" prop="base_url">
            <el-input v-model="form.base_url" maxlength="255" />
            <div class="hint">{{ activeProvider?.base_url_hint }} 系统自动添加 /chat/completions。</div>
          </el-form-item>
          <el-form-item :label="`${activeProvider?.name || '模型'} API Key`" prop="api_key">
            <el-input v-model="form.api_key" type="password" show-password autocomplete="new-password" :maxlength="512"
              :placeholder="keyRequired ? '请输入该服务商的 API Key' : '已保存密钥；留空保留，输入新密钥替换'" />
            <div class="hint">密钥加密保存且不会回显。 <a v-if="activeProvider" :href="activeProvider.api_key_url" target="_blank" rel="noopener noreferrer">前往官方平台获取 ↗</a></div>
          </el-form-item>
          <el-form-item label="模型名称（Model）" prop="model">
            <div class="model-picker">
              <el-select v-model="form.model" filterable allow-create default-first-option style="width: 100%" placeholder="选择或输入模型 ID" @visible-change="handleModelDropdown">
                <el-option v-for="model in modelOptions" :key="model.id" :label="model.name && model.name !== model.id ? `${model.name} (${model.id})` : model.id" :value="model.id" />
              </el-select>
              <el-button :loading="discovering" :disabled="!canDiscover" @click="discoverModels(selectedId, true)">获取可用模型</el-button>
            </div>
            <div class="hint">{{ modelDiscoveryHint }}</div>
          </el-form-item>
          <div class="parameter-grid">
            <el-form-item label="深度思考"><el-switch v-model="form.thinking" active-text="开启" inactive-text="关闭" /><div class="hint">开启后回答可能更慢，输出上限也可能包含思考过程。</div></el-form-item>
            <el-form-item label="温度（Temperature）" prop="temperature"><el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" :precision="1" :disabled="form.thinking" /><div class="hint">越低越稳定；思考模式下由服务商控制。</div></el-form-item>
            <el-form-item label="最大输出 token 数" prop="max_tokens"><el-input-number v-model="form.max_tokens" :min="1" :max="32768" :step="1024" :precision="0" /><div class="hint">系统上限 32,768，实际可用值取决于模型。</div></el-form-item>
          </div>
          <el-form-item label="系统提示词（可选）" prop="system_prompt"><el-input v-model="form.system_prompt" type="textarea" :rows="4" maxlength="8000" show-word-limit /></el-form-item>
          <el-alert v-if="testResult" :title="testResult.message" :type="testResult.success ? 'success' : 'error'" :closable="false" show-icon class="test-result" />
          <div class="actions">
            <el-button type="primary" :loading="saving" @click="save(false)">保存配置</el-button>
            <el-button :loading="testing" @click="save(true)">保存并测试</el-button>
            <el-button v-if="selectedId && !selectedConfig?.is_active" :loading="activatingId === selectedId" @click="activate(selectedConfig)">设为当前使用</el-button>
            <el-button v-if="selectedId" type="danger" plain :loading="deleting" @click="remove">删除</el-button>
          </div>
          <p class="hint">测试会向所选配置发送一条简短请求并产生少量 API 用量；保存本身不调用模型。</p>
        </el-form>
      </main>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Connection, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  activateAiConfig,
  createAiConfig,
  deleteAiConfig,
  getAiConfigModels,
  listAiConfigs,
  listAiProviders,
  testSavedAiConfig,
  updateAiConfig,
} from '@/api/ai'
import { notifyRequestError } from '@/utils/request'

const DEFAULT_PROMPT = '你是 iKnowread 智能助手，请用清晰、准确的中文回答用户的问题。'
const router = useRouter()
const formRef = ref()
const providers = ref([])
const configs = ref([])
const discoveredModels = ref([])
const discoveredForId = ref(null)
const discovering = ref(false)
const selectedId = ref(null)
const originalProvider = ref('')
const hasKey = ref(false)
const loading = ref(true)
const loadError = ref(false)
const saving = ref(false)
const testing = ref(false)
const deleting = ref(false)
const activatingId = ref(null)
const testResult = ref(null)
const form = reactive({ name: '', provider: 'deepseek', base_url: '', model: '', api_key: '', temperature: 1, max_tokens: 4096, thinking: false, system_prompt: DEFAULT_PROMPT })

const activeProvider = computed(() => providers.value.find(item => item.id === form.provider))
const selectedConfig = computed(() => configs.value.find(item => item.id === selectedId.value))
const modelOptions = computed(() => {
  const byId = new Map()
  for (const item of discoveredModels.value) byId.set(item.id, item)
  for (const id of activeProvider.value?.models || []) if (!byId.has(id)) byId.set(id, { id, name: '' })
  if (form.model && !byId.has(form.model)) byId.set(form.model, { id: form.model, name: '' })
  return [...byId.values()]
})
const keyRequired = computed(() => !hasKey.value || (!!selectedId.value && originalProvider.value !== form.provider))
const canDiscover = computed(() => !!selectedId.value
  && originalProvider.value === form.provider
  && selectedConfig.value?.base_url === form.base_url.trim().replace(/\/$/, '')
  && !form.api_key.trim())
const modelDiscoveryHint = computed(() => {
  if (!selectedId.value) return '请先保存配置，系统随后会自动获取该账号可用的模型。'
  if (!canDiscover.value) return '服务商、接口地址或密钥有未保存的更改；保存后即可获取模型。'
  return '打开列表时自动从服务商刷新；仍可手动输入模型 ID。'
})
const busy = computed(() => saving.value || testing.value || deleting.value || activatingId.value !== null)
function officialBaseUrl(value) {
  const normalized = value.trim().replace(/\/$/, '')
  if (form.provider === 'deepseek') return ['https://api.deepseek.com', 'https://api.deepseek.com/v1'].includes(normalized)
  if (form.provider === 'glm') return normalized === 'https://open.bigmodel.cn/api/paas/v4'
  if (form.provider === 'mimo') return normalized === 'https://api.xiaomimimo.com/v1'
  if (form.provider === 'bailian') {
    return /^https:\/\/(?:dashscope(?:-intl)?\.aliyuncs\.com|[a-zA-Z0-9-]+\.(?:cn-beijing|ap-southeast-1|us-east-1|eu-central-1|ap-northeast-1|cn-hongkong)\.maas\.aliyuncs\.com)\/compatible-mode\/v1$/.test(normalized)
  }
  return false
}
const rules = {
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }, { min: 1, max: 100, message: '配置名称最多 100 字符', trigger: 'blur' }],
  provider: [{ required: true, message: '请选择模型服务商', trigger: 'change' }],
  base_url: [{ validator: (_, value, callback) => {
    if (!value.trim()) return callback(new Error('请输入官方接口地址'))
    if (!officialBaseUrl(value)) return callback(new Error(`请输入 ${activeProvider.value?.name || '服务商'} 的官方兼容接口地址`))
    callback()
  }, trigger: 'blur' }],
  model: [{ required: true, message: '请选择或输入模型名称', trigger: 'change' }, { pattern: /^[a-zA-Z0-9._:/-]{1,100}$/, message: '请输入有效的模型 ID（最多 100 字符）', trigger: 'change' }],
  api_key: [{ validator: (_, value, callback) => {
    if (keyRequired.value && !value.trim()) return callback(new Error('请填写该服务商的 API Key'))
    if (value.trim() && !/^[\x21-\x7e]{1,512}$/.test(value.trim())) return callback(new Error('API Key 不能包含空白或非英文字符'))
    callback()
  }, trigger: 'blur' }],
  temperature: [{ type: 'number', required: true, min: 0, max: 2, message: '请输入 0–2 之间的温度', trigger: 'change' }],
  max_tokens: [{ type: 'integer', required: true, min: 1, max: 32768, message: '请输入 1–32768 之间的整数', trigger: 'change' }],
}

function providerDefaults(providerId = 'deepseek') {
  const provider = providers.value.find(item => item.id === providerId) || providers.value[0]
  return { name: provider ? `${provider.name} · ${provider.models[0]}` : '', provider: provider?.id || providerId, base_url: provider?.default_base_url || '', model: provider?.models[0] || '', api_key: '', temperature: 1, max_tokens: 4096, thinking: false, system_prompt: DEFAULT_PROMPT }
}
async function resetValidation() { await nextTick(); formRef.value?.clearValidate() }
function selectConfig(item) {
  selectedId.value = item.id
  originalProvider.value = item.provider
  hasKey.value = item.has_api_key
  const { id, provider_name, has_api_key, is_active, created_at, updated_at, ...values } = item
  Object.assign(form, values, { api_key: '' })
  discoveredModels.value = []
  discoveredForId.value = null
  testResult.value = null
  resetValidation()
}
function newConfig() {
  selectedId.value = null
  originalProvider.value = ''
  hasKey.value = false
  Object.assign(form, providerDefaults())
  discoveredModels.value = []
  discoveredForId.value = null
  testResult.value = null
  resetValidation()
}
function changeProvider(providerId) {
  const provider = providers.value.find(item => item.id === providerId)
  if (!provider) return
  form.base_url = provider.default_base_url
  form.model = provider.models[0]
  form.api_key = ''
  discoveredModels.value = []
  discoveredForId.value = null
  if (!selectedId.value) form.name = `${provider.name} · ${provider.models[0]}`
  testResult.value = null
  resetValidation()
}
async function load(preferredId = null) {
  loading.value = true
  loadError.value = false
  try {
    const [providerResponse, configResponse] = await Promise.all([listAiProviders(), listAiConfigs()])
    providers.value = providerResponse.data || []
    configs.value = configResponse.data || []
    const target = configs.value.find(item => item.id === preferredId) || configs.value.find(item => item.is_active) || configs.value[0]
    if (target) selectConfig(target); else newConfig()
  } catch (_) { loadError.value = true }
  finally { loading.value = false }
}
function payload() {
  return { name: form.name.trim(), provider: form.provider, base_url: form.base_url.trim(), model: form.model.trim(), api_key: form.api_key.trim() || null, temperature: form.temperature, max_tokens: form.max_tokens, thinking: form.thinking, system_prompt: form.system_prompt }
}
async function discoverModels(configId, notify = false) {
  if (!configId || discovering.value) return
  discovering.value = true
  try {
    const { data } = await getAiConfigModels(configId, { timeout: 35000 })
    if (selectedId.value !== configId) return
    discoveredModels.value = data.models || []
    discoveredForId.value = configId
    if (notify) {
      if (data.source === 'provider') ElMessage.success(data.message)
      else ElMessage.info(data.message)
    }
  } catch (error) {
    notifyRequestError(error, '模型列表获取失败，请重试')
  } finally { discovering.value = false }
}
function handleModelDropdown(visible) {
  if (visible && canDiscover.value && discoveredForId.value !== selectedId.value) {
    discoverModels(selectedId.value, false)
  }
}
async function save(withTest) {
  if (busy.value || !await formRef.value.validate().catch(() => false)) return
  saving.value = true
  testResult.value = null
  try {
    const response = selectedId.value
      ? await updateAiConfig(selectedId.value, payload())
      : await createAiConfig(payload())
    const savedId = response.data.id
    form.api_key = ''
    hasKey.value = true
    originalProvider.value = response.data.provider
    ElMessage.success('配置已保存')
    await load(savedId)
    await discoverModels(savedId, true).catch(() => {})
    if (withTest) {
      testing.value = true
      const result = await testSavedAiConfig(savedId, { timeout: 135000 })
      testResult.value = { success: true, message: result.data.message }
    }
  } catch (error) {
    notifyRequestError(error, '配置保存失败，请重试')
    if (withTest) testResult.value = { success: false, message: error.response?.data?.msg || '保存或连接测试失败' }
  } finally { saving.value = false; testing.value = false }
}
async function activate(item) {
  if (!item || activatingId.value !== null) return
  activatingId.value = item.id
  try { await activateAiConfig(item.id); ElMessage.success(`已切换为「${item.name}」`); await load(item.id) }
  catch (error) { notifyRequestError(error, '配置激活失败，请重试') }
  finally { activatingId.value = null }
}
async function remove() {
  if (!selectedConfig.value) return
  try {
    await ElMessageBox.confirm(`确定删除「${selectedConfig.value.name}」吗？${selectedConfig.value.is_active ? '删除后系统会自动启用另一项可用配置。' : ''}`, '删除模型配置', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch (_) { return }
  deleting.value = true
  try { await deleteAiConfig(selectedId.value); ElMessage.success('配置已删除'); await load() }
  catch (error) { notifyRequestError(error, '配置删除失败，请重试') }
  finally { deleting.value = false }
}

watch(form, () => { testResult.value = null }, { deep: true })
onMounted(load)
</script>

<style scoped>
.config-page { max-width: 1240px; margin: 0 auto; padding: 0 4px; }
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; flex-wrap: wrap; margin: 4px 0 20px; }
h1 { margin: 0 0 8px; font-size: 24px; } h2 { margin: 0 0 6px; font-size: 20px; }
p { margin: 0; color: var(--ik-text-sub); line-height: 1.7; } .load-error { margin-bottom: 16px; }
.config-layout { display: grid; grid-template-columns: minmax(260px, 320px) minmax(0, 1fr); gap: 20px; align-items: start; }
.config-list, .editor { padding: 22px; } .config-list { position: sticky; top: 20px; }
.list-heading, .editor-heading, .item-top, .item-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.list-heading { margin-bottom: 16px; } .list-heading strong { font-size: 17px; } .list-heading span { margin-left: 8px; color: var(--ik-text-sub); font-size: 12px; }
.list-empty { text-align: center; padding: 32px 8px; color: var(--ik-text-sub); } .list-empty .el-icon { font-size: 30px; color: var(--ik-cyan-deep); }
.list-empty p { margin: 10px 0 2px; color: var(--ik-text); } .list-empty span { font-size: 12px; line-height: 1.6; }
.config-item { width: 100%; display: block; text-align: left; border: 1px solid var(--ik-border); background: #fff; border-radius: 12px; padding: 14px; margin-top: 10px; color: inherit; cursor: pointer; transition: border-color .2s, background .2s, box-shadow .2s; }
.config-item:hover, .config-item.selected { border-color: var(--ik-cyan); background: #f6fbfe; } .config-item.selected { box-shadow: 0 0 0 2px rgba(42, 154, 207, .08); } .config-item.active { border-left: 4px solid var(--ik-cyan-deep); }
.item-top strong { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; } .item-meta { display: block; margin-top: 7px; color: var(--ik-text-sub); font-size: 12px; overflow-wrap: anywhere; }
.item-actions { margin-top: 10px; min-height: 22px; font-size: 11px; color: var(--ik-text-sub); }
.editor-heading { padding-bottom: 20px; margin-bottom: 22px; border-bottom: 1px solid var(--ik-border); } .config-form { max-width: 820px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; } .parameter-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.model-picker { width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }
.hint { color: var(--ik-text-sub); font-size: 12px; line-height: 1.7; margin-top: 7px; width: 100%; } .hint a { color: var(--ik-blue); text-decoration: none; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; } .actions .el-button { margin-left: 0; } .test-result { margin-bottom: 16px; }
@media (max-width: 900px) { .config-layout { grid-template-columns: 1fr; } .config-list { position: static; } .parameter-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 620px) { .form-grid, .parameter-grid { grid-template-columns: 1fr; gap: 0; } .model-picker { grid-template-columns: 1fr; } .config-list, .editor { padding: 17px; } .page-heading { align-items: flex-start; } }
</style>
