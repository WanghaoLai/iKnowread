<template>
  <el-dialog
    :model-value="modelValue"
    :title="announcement ? '编辑公告' : '新增公告'"
    width="min(960px, 92vw)"
    :close-on-click-modal="false"
    :before-close="beforeClose"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
      <div class="form-heading">
        <el-form-item label="公告标题" prop="title" class="title-field">
          <el-input v-model="form.title" maxlength="200" show-word-limit placeholder="输入简洁、清晰的公告标题" />
        </el-form-item>
        <el-form-item v-if="!announcement" label="保存状态" prop="status" class="status-field">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="保存为草稿" value="draft" />
            <el-option label="立即发布" value="published" />
          </el-select>
        </el-form-item>
      </div>
      <div class="editor-grid">
        <el-form-item label="Markdown 内容" prop="content" class="content-field">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="17"
            maxlength="100000"
            resize="vertical"
            placeholder="支持标题、列表、链接、引用等 Markdown 语法"
          />
        </el-form-item>
        <section class="preview-pane" aria-label="公告预览">
          <div class="preview-heading">实时预览</div>
          <div v-if="form.content.trim()" class="markdown-preview" v-html="previewHtml"></div>
          <el-empty v-else :image-size="54" description="输入内容后在此预览" />
        </section>
      </div>
      <el-alert
        v-if="announcement?.status === 'published'"
        type="info"
        :closable="false"
        show-icon
        title="已发布公告保存修改后将生成新版本，所有用户会重新收到未读提醒。"
      />
    </el-form>
    <template #footer>
      <el-button :disabled="submitting" @click="requestClose">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  announcement: { type: Object, default: null },
  submitting: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'submit'])
const formRef = ref()
const form = reactive({ title: '', content: '', status: 'draft' })
const initialSnapshot = ref('')
const rules = {
  title: [
    { required: true, whitespace: true, message: '请输入公告标题', trigger: 'blur' },
    { max: 200, message: '标题最多 200 个字符', trigger: 'blur' },
  ],
  content: [{ required: true, whitespace: true, message: '请输入公告内容', trigger: 'blur' }],
}
const previewHtml = computed(() => renderMarkdown(form.content))
const snapshot = () => JSON.stringify({ title: form.title, content: form.content, status: form.status })

watch(() => props.modelValue, async visible => {
  if (!visible) return
  Object.assign(form, props.announcement
    ? { title: props.announcement.title, content: props.announcement.content, status: props.announcement.status }
    : { title: '', content: '', status: 'draft' })
  initialSnapshot.value = snapshot()
  await nextTick()
  formRef.value?.clearValidate()
})

async function beforeClose(done) {
  if (props.submitting) return
  if (snapshot() === initialSnapshot.value) return done()
  try {
    await ElMessageBox.confirm('尚有未保存的公告内容，确定关闭吗？', '放弃修改', {
      type: 'warning',
      confirmButtonText: '放弃修改',
      cancelButtonText: '继续编辑',
    })
    done()
  } catch (_) {
    // 用户选择继续编辑。
  }
}

function requestClose() {
  beforeClose(() => emit('update:modelValue', false))
}

async function submit() {
  if (props.submitting || !await formRef.value?.validate().catch(() => false)) return
  emit('submit', {
    title: form.title.trim(),
    content: form.content.trim(),
    ...(!props.announcement && { status: form.status }),
  })
}
</script>

<style scoped>
.form-heading { display: grid; grid-template-columns: minmax(0, 1fr) 170px; gap: 16px; }
.title-field, .status-field, .content-field { margin-bottom: 14px; }
.editor-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, .85fr); gap: 18px; align-items: stretch; margin-bottom: 14px; }
.preview-pane { min-height: 390px; max-height: 520px; border: 1px solid var(--ik-border); border-radius: 8px; background: #fbfcfe; overflow: auto; }
.preview-heading { position: sticky; top: 0; z-index: 1; padding: 10px 14px; border-bottom: 1px solid var(--ik-border); background: #f4f7fa; color: #66768a; font-size: 13px; font-weight: 600; }
.markdown-preview { padding: 14px 18px; color: #33475e; line-height: 1.75; overflow-wrap: anywhere; }
.markdown-preview :deep(h1), .markdown-preview :deep(h2), .markdown-preview :deep(h3) { color: #182b49; line-height: 1.35; }
.markdown-preview :deep(a) { color: var(--ik-blue); }
.markdown-preview :deep(img) { max-width: 100%; }
.markdown-preview :deep(code) { padding: 2px 5px; border-radius: 4px; background: #edf2f7; }
@media (max-width: 760px) {
  .form-heading, .editor-grid { grid-template-columns: 1fr; }
  .preview-pane { min-height: 260px; }
}
</style>
