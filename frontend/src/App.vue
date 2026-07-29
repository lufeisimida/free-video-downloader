<template>
  <div class="min-h-screen flex flex-col bg-bg-main">
    <AppHeader
      :user="currentUser"
      :paymentEnabled="paymentEnabled"
      :registrationEnabled="registrationEnabled"
      @login="showAuthModal('login')"
      @register="showAuthModal('register')"
      @logout="handleLogout"
      @open-vip="handleOpenVip"
      @open-model-config="openModelConfig"
      @open-library="openLibrary"
    />
    <main class="flex-1">
      <HeroSection
        @parse="handleParse"
        @need-login="showAuthModal('login')"
        :loading="loading"
        :compact="!!videoData"
        :showSlogan="!videoData"
        :authenticated="!!currentUser"
      />
      <!-- 视频信息 + AI 总结：左右双栏同屏布局 -->
      <section v-if="videoData" class="py-4 sm:py-6 bg-white">
        <div class="max-w-7xl mx-auto px-4 sm:px-6">
          <div v-if="videoData.library_id" class="mb-4 flex flex-wrap items-center justify-between gap-3 border-y border-border-light bg-gray-50/70 px-3 py-2.5">
            <div class="flex min-w-0 items-center gap-2 text-xs text-text-muted">
              <svg class="h-4 w-4 shrink-0 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M3 6h7l2 2h9v11H3V6z" /></svg>
              <span class="shrink-0">目录标签</span>
              <select :value="videoData.folder_id ?? ''" @change="assignCurrentVideoFolder" class="h-8 max-w-64 rounded-md border border-border bg-white px-2 text-xs text-text-secondary focus:border-primary focus:outline-none">
                <option value="">未归档</option>
                <option v-for="folder in libraryFolderOptions" :key="folder.id" :value="folder.id">{{ '—'.repeat(folder.depth) }} {{ folder.name }}</option>
              </select>
            </div>
            <button @click="openLibrary" class="text-xs font-medium text-primary hover:text-primary-dark cursor-pointer">查看课程资料库</button>
          </div>
          <div class="flex flex-col lg:flex-row gap-6">
            <!-- 左栏：视频信息 -->
            <div class="w-full lg:w-2/5 lg:flex-shrink-0">
              <VideoResult
                :video="videoData"
                :downloading="downloading"
                :summarizing="summarizing"
                @download="handleDownload"
                @summarize="handleSummarize"
              />
            </div>
            <!-- 右栏：AI 总结 -->
            <div class="w-full lg:w-3/5 min-w-0">
              <VideoSummary
                :videoUrl="currentUrl"
                :videoTitle="videoData.title"
                :libraryVideoId="videoData.library_id"
                :user="currentUser"
                :force="forceSummary"
                :key="summaryKey"
                @loading-change="handleSummarizeLoadingChange"
                @need-login="showAuthModal('login')"
                @need-vip="handleNeedVip"
              />
            </div>
          </div>
        </div>
      </section>
      <FeatureSection />
      <HowToSection />
      <ComparisonSection />
      <PricingSection
        v-if="paymentEnabled"
        :user="currentUser"
        @open-vip="handleOpenVip"
        @need-login="showAuthModal('login')"
      />
      <PlatformSection />
    </main>
    <AppFooter />

    <!-- 支付成功/取消提示 -->
    <Teleport to="body">
      <div v-if="paymentToast" class="fixed top-20 left-1/2 -translate-x-1/2 z-[200] animate-toast-in">
        <div :class="[
          'flex items-center gap-3 px-6 py-4 rounded-2xl shadow-xl border',
          paymentToast === 'success' ? 'bg-green-50 border-green-200 text-green-800' : 'bg-orange-50 border-orange-200 text-orange-800'
        ]">
          <svg v-if="paymentToast === 'success'" class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <svg v-else class="w-5 h-5 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <span class="font-medium text-sm">
            {{ paymentToast === 'success' ? 'VIP 开通成功！已为你激活全部高级功能' : '支付已取消，你可以随时再次开通' }}
          </span>
        </div>
      </div>
    </Teleport>

    <AuthModal
      :visible="authModalVisible"
      :initialMode="authModalMode"
      :registrationEnabled="registrationEnabled"
      @close="authModalVisible = false"
      @success="handleAuthSuccess"
    />

    <ModelConfigPanel
      :visible="modelConfigVisible"
      @close="modelConfigVisible = false"
      @saved="handleModelConfigSaved"
    />

    <CourseLibraryPanel
      :visible="libraryPanelVisible"
      :refreshKey="libraryRefreshKey"
      @close="libraryPanelVisible = false"
      @open-video="openLibraryVideo"
      @changed="refreshLibrarySummary"
    />
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import AppHeader from './components/AppHeader.vue'
import HeroSection from './components/HeroSection.vue'
import VideoResult from './components/VideoResult.vue'
import VideoSummary from './components/VideoSummary.vue'
import FeatureSection from './components/FeatureSection.vue'
import HowToSection from './components/HowToSection.vue'
import ComparisonSection from './components/ComparisonSection.vue'
import PricingSection from './components/PricingSection.vue'
import PlatformSection from './components/PlatformSection.vue'
import AppFooter from './components/AppFooter.vue'
import AuthModal from './components/AuthModal.vue'
import ModelConfigPanel from './components/ModelConfigPanel.vue'
import CourseLibraryPanel from './components/CourseLibraryPanel.vue'
import { parseVideo, downloadViaServer } from './api/video.js'
import { fetchAuthConfig, fetchMe, logout as logoutApi, isLoggedIn } from './api/auth.js'
import { createCheckoutSession } from './api/payment.js'
import { getLibrary, getPendingReminders, markReminderShown, moveLibraryVideo } from './api/library.js'

const paymentEnabled = import.meta.env.VITE_PAYMENT_ENABLED !== 'false'
const registrationEnabled = ref(false)

onMounted(() => {
  loadAuthConfig()
  restoreUser()
  checkPaymentResult()
})

// ===== 用户状态管理 =====
const currentUser = ref(null)
const authModalVisible = ref(false)
const authModalMode = ref('login')
const modelConfigVisible = ref(false)
const libraryPanelVisible = ref(false)
const libraryRefreshKey = ref(0)
const libraryFolders = ref([])
let reminderTimer = null

const libraryFolderOptions = computed(() => {
  const byParent = new Map()
  for (const folder of libraryFolders.value) {
    const key = folder.parent_id ?? null
    if (!byParent.has(key)) byParent.set(key, [])
    byParent.get(key).push(folder)
  }
  const result = []
  const walk = (parentId, depth) => {
    for (const folder of byParent.get(parentId) || []) {
      result.push({ ...folder, depth })
      walk(folder.id, depth + 1)
    }
  }
  walk(null, 0)
  return result
})

function showAuthModal(mode = 'login') {
  authModalMode.value = mode === 'register' && registrationEnabled.value ? 'register' : 'login'
  authModalVisible.value = true
}

async function loadAuthConfig() {
  try {
    const config = await fetchAuthConfig()
    registrationEnabled.value = Boolean(config.registration_enabled)
  } catch {
    registrationEnabled.value = false
  }
}

function handleAuthSuccess(user) {
  currentUser.value = user
  refreshLibrarySummary()
  startReminderPolling()
}

function handleLogout() {
  logoutApi()
  currentUser.value = null
  modelConfigVisible.value = false
  libraryPanelVisible.value = false
  libraryFolders.value = []
  videoData.value = null
  currentUrl.value = ''
  if (reminderTimer) window.clearInterval(reminderTimer)
  reminderTimer = null
}

async function restoreUser() {
  if (!isLoggedIn()) return
  try {
    currentUser.value = await fetchMe()
    await refreshLibrarySummary()
    startReminderPolling()
  } catch {
    handleLogout()
  }
}

async function pollLearningReminders() {
  if (!currentUser.value || !('Notification' in window) || Notification.permission !== 'granted') return
  try {
    const reminders = await getPendingReminders()
    const shown = []
    for (const reminder of reminders) {
      new Notification(reminder.title, { body: reminder.body, tag: `saveany-reminder-${reminder.id}` })
      shown.push(reminder.id)
    }
    if (shown.length) await markReminderShown(shown)
  } catch {}
}

function startReminderPolling() {
  if (reminderTimer) window.clearInterval(reminderTimer)
  pollLearningReminders()
  reminderTimer = window.setInterval(pollLearningReminders, 60000)
}

// ===== VIP 购买 =====
async function handleOpenVip() {
  if (!paymentEnabled) {
    alert('支付功能已关闭')
    return
  }
  if (!requireLogin('请先登录后再开通会员')) return
  try {
    const { checkout_url } = await createCheckoutSession('monthly')
    window.location.href = checkout_url
  } catch (err) {
    const msg = err.response?.data?.detail || err.message || '创建支付失败'
    alert(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
}

function handleNeedVip() {
  if (paymentEnabled) {
    handleOpenVip()
  }
}

function handleModelConfigSaved() {
  if (videoData.value) {
    summaryKey.value++
  }
}

function openModelConfig() {
  if (!requireLogin()) return
  modelConfigVisible.value = true
}

function requireLogin(message = '请先登录后再使用') {
  if (currentUser.value && isLoggedIn()) return true
  logoutApi()
  alert(message)
  showAuthModal('login')
  return false
}

function openLibrary() {
  if (!requireLogin('请先登录后再使用课程资料库')) return
  libraryPanelVisible.value = true
  libraryRefreshKey.value++
}

async function refreshLibrarySummary() {
  if (!currentUser.value || !isLoggedIn()) return
  try {
    const data = await getLibrary()
    libraryFolders.value = data.folders || []
    libraryRefreshKey.value++
  } catch (err) {
    if (err.response?.status === 401) handleExpiredLogin()
  }
}

async function assignCurrentVideoFolder(event) {
  if (!videoData.value?.library_id) return
  const folderId = event.target.value === '' ? null : Number(event.target.value)
  try {
    const updated = await moveLibraryVideo(videoData.value.library_id, folderId)
    videoData.value.folder_id = updated.folder_id
    libraryRefreshKey.value++
  } catch (err) {
    alert('设置目录失败：' + (err.response?.data?.detail || err.message || '请稍后重试'))
  }
}

function openLibraryVideo(url) {
  libraryPanelVisible.value = false
  handleParse(url)
}

function handleExpiredLogin(message = '登录已失效，请重新登录') {
  handleLogout()
  alert(message)
  showAuthModal('login')
}

// ===== 支付结果处理 =====
const paymentToast = ref(null)

function checkPaymentResult() {
  const params = new URLSearchParams(window.location.search)
  const payment = params.get('payment')
  if (payment === 'success' || payment === 'cancel') {
    paymentToast.value = payment
    window.history.replaceState({}, '', window.location.pathname)
    if (payment === 'success' && isLoggedIn()) {
      setTimeout(async () => {
        try { currentUser.value = await fetchMe() } catch {}
      }, 1000)
    }
    setTimeout(() => { paymentToast.value = null }, 5000)
  }
}

// ===== 视频功能 =====
const loading = ref(false)
const downloading = ref(false)
const videoData = ref(null)
const currentUrl = ref('')
const summaryKey = ref(0)
const summarizing = ref(false)
const forceSummary = ref(false)

function handleSummarize() {
  if (!requireLogin('请先登录后再使用 AI 总结')) return
  forceSummary.value = true
  summaryKey.value++
}

function handleSummarizeLoadingChange(isLoading) {
  summarizing.value = isLoading
}

async function handleParse(url) {
  if (!requireLogin('请先登录后再解析视频')) return
  loading.value = true
  videoData.value = null
  currentUrl.value = url
  forceSummary.value = false
  try {
    const res = await parseVideo(url)
    if (res.success) {
      videoData.value = res.data
      summaryKey.value++
      await refreshLibrarySummary()
    } else {
      alert('解析失败：' + (res.error || '未知错误'))
    }
  } catch (err) {
    if (err.response?.status === 401) {
      handleExpiredLogin()
      return
    }
    const msg = err.response?.data?.detail?.error || err.response?.data?.detail || err.message
    alert('解析失败：' + msg)
  } finally {
    loading.value = false
  }
}

async function handleDownload(formatId) {
  if (!requireLogin('请先登录后再下载视频')) return
  downloading.value = true
  try {
    const response = await downloadViaServer(currentUrl.value, formatId)
    const contentDisposition = response.headers['content-disposition']
    let filename = 'video.mp4'
    if (contentDisposition) {
      const match = contentDisposition.match(/filename\*?=(?:UTF-8'')?([^;\n]+)/i)
      if (match) filename = decodeURIComponent(match[1].replace(/"/g, ''))
    }
    const blob = new Blob([response.data])
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    if (err.response?.status === 401) {
      handleExpiredLogin()
      return
    }
    alert('下载失败：' + (err.message || '请稍后重试'))
  } finally {
    downloading.value = false
  }
}
</script>

<style>
@keyframes toast-in {
  from { opacity: 0; transform: translate(-50%, -10px); }
  to { opacity: 1; transform: translate(-50%, 0); }
}
.animate-toast-in {
  animation: toast-in 0.3s ease-out;
}
</style>
