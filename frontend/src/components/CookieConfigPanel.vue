<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-[220] bg-slate-950/45 backdrop-blur-sm">
      <div class="min-h-screen overflow-y-auto px-4 py-6 sm:px-6">
        <div class="mx-auto max-w-2xl overflow-hidden rounded-2xl bg-white shadow-2xl border border-slate-200">
          <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
            <div>
              <h2 class="text-lg font-semibold text-slate-950">Cookie 配置</h2>
              <p class="mt-0.5 text-xs text-slate-500">{{ statusLabel }}</p>
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

          <div v-if="loading" class="flex min-h-[360px] items-center justify-center">
            <div class="h-10 w-10 rounded-full border-4 border-primary/20 border-t-primary animate-spin"></div>
          </div>

          <section v-else class="p-5 sm:p-6">
            <div v-if="error" class="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {{ error }}
            </div>

            <div class="mb-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600">
              服务器 IP 解析 B 站等平台常被风控拦截（<code class="rounded bg-white px-1 py-0.5 text-[11px]">HTTP 412</code>）。
              用浏览器插件 <strong>Get cookies.txt LOCALLY</strong> 登录后导出 <code class="rounded bg-white px-1 py-0.5 text-[11px]">bilibili.com</code>
              的 Cookie，把内容粘贴到下方即可。也支持直接粘贴 <code class="rounded bg-white px-1 py-0.5 text-[11px]">buvid3=xxx; SESSDATA=yyy</code> 这种原始 Cookie 串。
              建议用小号，Cookie 约一个月失效一次，失效后重新粘贴即可。
            </div>

            <label class="grid gap-1.5">
              <span class="flex items-center justify-between text-sm font-medium text-slate-700">
                <span>Cookie 内容</span>
                <span
                  :class="[
                    'rounded-full px-2 py-0.5 text-xs',
                    cookieSet ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                  ]"
                >
                  {{ cookieSet ? '已配置' : '未配置' }}
                </span>
              </span>
              <textarea
                v-model="cookies"
                rows="9"
                spellcheck="false"
                class="w-full rounded-xl border border-slate-300 px-3 py-2.5 font-mono text-xs text-slate-950 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                :placeholder="placeholder"
              ></textarea>
            </label>

            <p v-if="cookieNames" class="mt-2 text-xs text-slate-500">
              已保存的 Cookie 项：<span class="text-slate-700">{{ cookieNames }}</span>
            </p>
            <p v-if="updatedAt" class="mt-1 text-xs text-slate-400">最后更新：{{ updatedAt }}</p>

            <div class="mt-6 flex flex-col gap-3 border-t border-slate-200 pt-5">
              <div class="min-h-5 text-sm">
                <span v-if="testMessage" :class="testOk ? 'text-emerald-700' : 'text-red-700'">
                  {{ testMessage }}
                </span>
              </div>
              <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <button
                  v-if="cookieSet"
                  @click="remove"
                  :disabled="saving || testing || deleting"
                  class="inline-flex h-10 items-center gap-2 rounded-xl border border-red-200 px-4 text-sm font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  清除 Cookie
                </button>
                <span v-else></span>
                <div class="flex gap-2">
                  <button
                    @click="runTest"
                    :disabled="testing || saving || deleting"
                    class="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-300 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <svg class="h-4 w-4" :class="{ 'animate-spin': testing }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v6h6M20 20v-6h-6M5 19A9 9 0 0119 5M19 5h-5M19 5v5" />
                    </svg>
                    保存并测试
                  </button>
                  <button
                    @click="save"
                    :disabled="saving || testing || deleting"
                    class="inline-flex h-10 items-center gap-2 rounded-xl bg-primary px-5 text-sm font-semibold text-white shadow-sm hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <svg v-if="saving" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                    </svg>
                    <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                    </svg>
                    保存
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch } from 'vue'
import {
  clearCookieConfig,
  getCookieConfig,
  testCookieConfig,
  updateCookieConfig,
} from '../api/cookieConfig'

const props = defineProps({
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'saved'])

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const deleting = ref(false)
const error = ref('')
const testMessage = ref('')
const testOk = ref(false)

const cookies = ref('')
const cookieSet = ref(false)
const cookieNames = ref('')
const updatedAt = ref('')
const testUrl = ref('')

const placeholder = `# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\t...\n\n或直接粘贴：buvid3=xxx; SESSDATA=yyy; bili_jct=zzz`

const statusLabel = ref('未配置解析 Cookie')

watch(() => props.visible, (visible) => {
  if (visible) load()
})

function applyPayload(data) {
  cookieSet.value = !!data.cookie_set
  cookieNames.value = data.cookie_names || ''
  updatedAt.value = data.updated_at ? new Date(data.updated_at).toLocaleString() : ''
  testUrl.value = data.test_url || ''
  statusLabel.value = data.cookie_set ? '已配置，解析时自动带上' : '未配置解析 Cookie'
}

async function load() {
  loading.value = true
  error.value = ''
  testMessage.value = ''
  cookies.value = ''
  try {
    applyPayload(await getCookieConfig())
  } catch (err) {
    error.value = formatError(err, '读取 Cookie 配置失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  testMessage.value = ''
  try {
    const data = await updateCookieConfig(cookies.value)
    applyPayload(data)
    cookies.value = ''
    emit('saved', data)
    testOk.value = true
    testMessage.value = '已保存'
  } catch (err) {
    error.value = formatError(err, '保存 Cookie 配置失败')
  } finally {
    saving.value = false
  }
}

async function runTest() {
  testing.value = true
  error.value = ''
  testMessage.value = ''
  try {
    // 先保存当前输入（若有），再用已保存的 Cookie 实际解析测试
    if (cookies.value.trim()) {
      applyPayload(await updateCookieConfig(cookies.value))
      cookies.value = ''
    }
    const data = await testCookieConfig(testUrl.value)
    testOk.value = true
    testMessage.value = `解析成功：${data.title || data.url}`
    emit('saved')
  } catch (err) {
    testOk.value = false
    testMessage.value = formatError(err, '测试失败')
  } finally {
    testing.value = false
  }
}

async function remove() {
  if (!window.confirm('确定清除已保存的 Cookie 吗？')) return
  deleting.value = true
  error.value = ''
  testMessage.value = ''
  try {
    const data = await clearCookieConfig()
    applyPayload(data)
    cookies.value = ''
    emit('saved', data)
    testOk.value = true
    testMessage.value = '已清除'
  } catch (err) {
    error.value = formatError(err, '清除 Cookie 失败')
  } finally {
    deleting.value = false
  }
}

function formatError(err, fallback) {
  const detail = err.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail) return JSON.stringify(detail)
  return err.message || fallback
}
</script>
