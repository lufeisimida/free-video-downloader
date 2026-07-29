<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-[220] bg-slate-950/45 backdrop-blur-sm">
      <div class="min-h-screen overflow-y-auto px-4 py-6 sm:px-6">
        <div class="mx-auto max-w-5xl overflow-hidden rounded-2xl bg-white shadow-2xl border border-slate-200">
          <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
            <div>
              <h2 class="text-lg font-semibold text-slate-950">模型配置</h2>
              <p class="mt-0.5 text-xs text-slate-500">
                {{ activeLabel }}
              </p>
            </div>
            <button
              @click="$emit('close')"
              class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 transition-colors"
              title="关闭"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div v-if="loading" class="flex min-h-[420px] items-center justify-center">
            <div class="h-10 w-10 rounded-full border-4 border-primary/20 border-t-primary animate-spin"></div>
          </div>

          <div v-else class="grid gap-0 lg:grid-cols-[280px_1fr]">
            <aside class="border-b border-slate-200 bg-slate-50/70 p-4 lg:border-b-0 lg:border-r">
              <div class="mb-3 flex items-center justify-between gap-2">
                <p class="text-xs font-medium uppercase tracking-wide text-slate-500">配置列表</p>
                <button
                  @click="startCreate"
                  class="inline-flex h-8 items-center rounded-lg bg-white px-2.5 text-xs font-medium text-primary border border-slate-200 hover:border-primary/40"
                >
                  + 新建
                </button>
              </div>

              <div v-if="!profiles.length" class="rounded-xl border border-dashed border-slate-300 bg-white px-3 py-6 text-center text-xs text-slate-500">
                还没有模型配置，请在右侧添加
              </div>

              <div class="grid gap-2">
                <button
                  v-for="profile in profiles"
                  :key="profile.id"
                  @click="selectProfile(profile)"
                  :class="[
                    'rounded-xl border px-3 py-3 text-left transition-all',
                    form.id === profile.id
                      ? 'border-primary bg-white text-slate-950 shadow-sm'
                      : 'border-transparent text-slate-600 hover:border-slate-200 hover:bg-white'
                  ]"
                >
                  <span class="flex items-start justify-between gap-2">
                    <span class="min-w-0">
                      <span class="block truncate text-sm font-semibold">{{ profile.name }}</span>
                      <span class="mt-1 block truncate text-xs text-slate-500">{{ profile.model }}</span>
                      <span class="mt-0.5 block truncate text-[11px] text-slate-400">{{ profile.base_url }}</span>
                    </span>
                    <span
                      v-if="profile.is_active"
                      class="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700"
                    >
                      使用中
                    </span>
                  </span>
                </button>
              </div>
            </aside>

            <section class="p-5 sm:p-6">
              <div v-if="error" class="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {{ error }}
              </div>

              <p class="mb-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600">
                可保存多套中转站配置并一键切换。Base URL 可填
                <code class="rounded bg-white px-1 py-0.5 text-[11px]">https://52mx.net</code>
                或
                <code class="rounded bg-white px-1 py-0.5 text-[11px]">https://52mx.net/v1</code>
                （不带 /v1 会自动补全）。
              </p>

              <div class="grid gap-4">
                <label class="grid gap-1.5">
                  <span class="text-sm font-medium text-slate-700">配置名称</span>
                  <input
                    v-model.trim="form.name"
                    type="text"
                    class="h-11 rounded-xl border border-slate-300 px-3 text-sm text-slate-950 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                    placeholder="例如：52mx Claude"
                  />
                </label>

                <label class="grid gap-1.5">
                  <span class="text-sm font-medium text-slate-700">Base URL</span>
                  <input
                    v-model.trim="form.base_url"
                    type="url"
                    class="h-11 rounded-xl border border-slate-300 px-3 text-sm text-slate-950 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                    :placeholder="defaults.base_url || 'https://api.openai.com/v1'"
                  />
                </label>

                <label class="grid gap-1.5">
                  <span class="text-sm font-medium text-slate-700">模型名称</span>
                  <input
                    v-model.trim="form.model"
                    type="text"
                    class="h-11 rounded-xl border border-slate-300 px-3 text-sm text-slate-950 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                    :placeholder="defaults.model || 'gpt-4o-mini'"
                  />
                </label>

                <label class="grid gap-1.5">
                  <span class="flex items-center justify-between text-sm font-medium text-slate-700">
                    <span>API Key</span>
                    <span
                      :class="[
                        'rounded-full px-2 py-0.5 text-xs',
                        form.api_key_set || form.api_key ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                      ]"
                    >
                      {{ form.api_key_set || form.api_key ? '已配置' : '未配置' }}
                    </span>
                  </span>
                  <div class="relative">
                    <input
                      v-model.trim="form.api_key"
                      :type="showApiKey ? 'text' : 'password'"
                      autocomplete="off"
                      class="h-11 w-full rounded-xl border border-slate-300 px-3 pr-11 text-sm text-slate-950 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                      :placeholder="form.api_key_set ? '留空则保留当前密钥' : 'sk-...'"
                    />
                    <button
                      type="button"
                      @click="showApiKey = !showApiKey"
                      class="absolute right-2 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                      :title="showApiKey ? '隐藏密钥' : '显示密钥'"
                    >
                      <svg v-if="!showApiKey" class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                      <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 012.223-3.592m3.292-2.268A9.956 9.956 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411M15 12a3 3 0 00-3-3m0 0l-4.243-4.243M12 9l4.243 4.243M3 3l18 18" />
                      </svg>
                    </button>
                  </div>
                </label>
              </div>

              <div class="mt-6 flex flex-col gap-3 border-t border-slate-200 pt-5">
                <div class="min-h-5 text-sm">
                  <span v-if="testMessage" :class="testOk ? 'text-emerald-700' : 'text-red-700'">
                    {{ testMessage }}
                  </span>
                </div>
                <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
                  <div class="flex flex-wrap gap-2">
                    <button
                      v-if="form.id && !form.is_active"
                      @click="activate"
                      :disabled="saving || testing || activating"
                      class="inline-flex h-10 items-center gap-2 rounded-xl border border-emerald-300 bg-emerald-50 px-4 text-sm font-medium text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      设为当前使用
                    </button>
                    <button
                      v-if="form.id"
                      @click="remove"
                      :disabled="saving || testing || activating || deleting"
                      class="inline-flex h-10 items-center gap-2 rounded-xl border border-red-200 px-4 text-sm font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      删除
                    </button>
                  </div>
                  <div class="flex gap-2">
                    <button
                      @click="runTest"
                      :disabled="testing || saving || activating || deleting"
                      class="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-300 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <svg class="h-4 w-4" :class="{ 'animate-spin': testing }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v6h6M20 20v-6h-6M5 19A9 9 0 0119 5M19 5h-5M19 5v5" />
                      </svg>
                      测试连接
                    </button>
                    <button
                      @click="save"
                      :disabled="saving || testing || activating || deleting"
                      class="inline-flex h-10 items-center gap-2 rounded-xl bg-primary px-5 text-sm font-semibold text-white shadow-sm hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <svg v-if="saving" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                      </svg>
                      <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                      </svg>
                      {{ form.id ? '保存修改' : '保存并启用' }}
                    </button>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  activateModelProfile,
  createModelProfile,
  deleteModelProfile,
  getModelConfig,
  testModelConfig,
  updateModelProfile,
} from '../api/modelConfig'

const props = defineProps({
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'saved'])

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const activating = ref(false)
const deleting = ref(false)
const error = ref('')
const testMessage = ref('')
const testOk = ref(false)
const showApiKey = ref(false)
const profiles = ref([])
const defaults = reactive({
  base_url: 'https://api.openai.com/v1',
  model: 'gpt-4o-mini',
})

const form = reactive({
  id: null,
  name: '',
  base_url: '',
  model: '',
  api_key: '',
  api_key_set: false,
  is_active: false,
})

const activeLabel = computed(() => {
  const active = profiles.value.find(item => item.is_active)
  if (active) return `当前使用：${active.name} · ${active.model}`
  return '可保存多套配置并随时切换'
})

watch(() => props.visible, (visible) => {
  if (visible) load()
})

function resetForm() {
  form.id = null
  form.name = ''
  form.base_url = defaults.base_url
  form.model = defaults.model
  form.api_key = ''
  form.api_key_set = false
  form.is_active = false
  showApiKey.value = false
}

function selectProfile(profile) {
  form.id = profile.id
  form.name = profile.name || ''
  form.base_url = profile.base_url || ''
  form.model = profile.model || ''
  form.api_key = ''
  form.api_key_set = !!profile.api_key_set
  form.is_active = !!profile.is_active
  showApiKey.value = false
  testMessage.value = ''
  error.value = ''
}

function startCreate() {
  resetForm()
  testMessage.value = ''
  error.value = ''
}

async function load() {
  loading.value = true
  error.value = ''
  testMessage.value = ''
  try {
    const data = await getModelConfig()
    profiles.value = data.profiles || []
    defaults.base_url = data.default_base_url || defaults.base_url
    defaults.model = data.default_model || defaults.model

    const active = data.active_profile || profiles.value.find(item => item.is_active) || profiles.value[0]
    if (active) selectProfile(active)
    else startCreate()
  } catch (err) {
    error.value = formatError(err, '读取模型配置失败')
  } finally {
    loading.value = false
  }
}

function applyPayload(data) {
  profiles.value = data.profiles || []
  const selectedId = form.id
  const next = profiles.value.find(item => item.id === selectedId)
    || data.active_profile
    || profiles.value.find(item => item.is_active)
    || profiles.value[0]
  if (next) selectProfile(next)
  else startCreate()
}

async function save() {
  saving.value = true
  error.value = ''
  testMessage.value = ''
  try {
    let data
    if (form.id) {
      data = await updateModelProfile(form.id, {
        name: form.name,
        base_url: form.base_url,
        model: form.model,
        api_key: form.api_key,
      })
    } else {
      data = await createModelProfile({
        name: form.name,
        base_url: form.base_url,
        model: form.model,
        api_key: form.api_key,
        activate: true,
      })
      if (data.profile?.id) form.id = data.profile.id
    }
    applyPayload(data)
    emit('saved', data)
    testOk.value = true
    testMessage.value = form.id ? '已保存' : '已保存并启用'
  } catch (err) {
    error.value = formatError(err, '保存模型配置失败')
  } finally {
    saving.value = false
  }
}

async function activate() {
  if (!form.id) return
  activating.value = true
  error.value = ''
  testMessage.value = ''
  try {
    const data = await activateModelProfile(form.id)
    applyPayload(data)
    emit('saved', data)
    testOk.value = true
    testMessage.value = '已切换为当前使用'
  } catch (err) {
    error.value = formatError(err, '切换模型配置失败')
  } finally {
    activating.value = false
  }
}

async function remove() {
  if (!form.id) return
  if (!window.confirm('确定删除这个模型配置吗？')) return
  deleting.value = true
  error.value = ''
  testMessage.value = ''
  try {
    const data = await deleteModelProfile(form.id)
    form.id = null
    applyPayload(data)
    emit('saved', data)
    testOk.value = true
    testMessage.value = '已删除'
  } catch (err) {
    error.value = formatError(err, '删除模型配置失败')
  } finally {
    deleting.value = false
  }
}

async function runTest() {
  testing.value = true
  error.value = ''
  testMessage.value = ''
  try {
    const data = await testModelConfig({
      profile_id: form.id || undefined,
      base_url: form.base_url,
      model: form.model,
      api_key: form.api_key,
    })
    testOk.value = true
    testMessage.value = `${data.model}: ${data.response || 'OK'}`
  } catch (err) {
    testOk.value = false
    testMessage.value = formatError(err, '测试连接失败')
  } finally {
    testing.value = false
  }
}

function formatError(err, fallback) {
  const detail = err.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail) return JSON.stringify(detail)
  return err.message || fallback
}
</script>
