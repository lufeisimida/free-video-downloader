<template>
  <header class="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-border-light">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <a href="/" class="flex items-center gap-3" title="SaveAny - 免费在线万能视频下载器">
        <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-blue-600 flex items-center justify-center shadow-sm" role="img" aria-label="SaveAny Logo">
          <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <span class="text-lg font-semibold text-text-primary tracking-tight">SaveAny</span>
        <span class="hidden sm:inline text-xs text-text-muted bg-primary-light px-2 py-0.5 rounded-full">万能视频下载</span>
      </a>
      <nav class="hidden md:flex items-center gap-6 text-sm text-text-secondary" aria-label="主导航">
        <a href="#features" class="hover:text-primary transition-colors" title="查看SaveAny功能特性">功能特性</a>
        <a href="#how-to-use" class="hover:text-primary transition-colors" title="了解如何使用SaveAny下载视频">使用教程</a>
        <a href="#comparison" class="hover:text-primary transition-colors" title="SaveAny与其他工具对比">工具对比</a>
        <a v-if="paymentEnabled" href="#pricing" class="hover:text-primary transition-colors" title="查看SaveAny套餐价格">套餐价格</a>
        <button v-if="user" @click="$emit('open-library')" class="hover:text-primary transition-colors cursor-pointer" title="课程资料库">课程资料库</button>
        <button @click="$emit('open-model-config')" class="hover:text-primary transition-colors cursor-pointer" title="模型配置">模型配置</button>
        <button v-if="user && user.is_admin" @click="$emit('open-cookie-config')" class="hover:text-primary transition-colors cursor-pointer" title="解析 Cookie 配置">Cookie</button>
      </nav>
      <div class="flex items-center gap-2 sm:gap-3">
        <div class="hidden md:flex items-center gap-3">
          <button v-if="user" @click="$emit('open-library')" class="inline-flex h-9 w-9 items-center justify-center rounded-full text-text-secondary hover:bg-gray-50 hover:text-primary transition-colors cursor-pointer" title="课程资料库">
            <svg class="h-[18px] w-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M3 6h7l2 2h9v11H3V6z" /></svg>
          </button>
          <button @click="$emit('open-model-config')" class="inline-flex h-9 w-9 items-center justify-center rounded-full text-text-secondary hover:bg-gray-50 hover:text-primary transition-colors cursor-pointer" title="模型配置">
            <svg class="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.607 2.296.07 2.572-1.065z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
          <button v-if="user && user.is_admin" @click="$emit('open-cookie-config')" class="inline-flex h-9 w-9 items-center justify-center rounded-full text-text-secondary hover:bg-gray-50 hover:text-primary transition-colors cursor-pointer" title="解析 Cookie 配置">
            <svg class="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 2a10 10 0 100 20 10 10 0 00-10-10 3 3 0 01-3-3 3 3 0 01-3-3z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.5 9.5h.01M12 13h.01M15 16h.01" />
            </svg>
          </button>
        </div>
        <!-- 未登录 -->
        <template v-if="!user">
          <button @click="$emit('login')" class="inline-flex items-center px-3 sm:px-4 py-2 rounded-full text-sm font-medium text-text-secondary hover:text-primary hover:bg-gray-50 transition-colors cursor-pointer">
            登录
          </button>
          <button v-if="registrationEnabled" @click="$emit('register')" class="hidden sm:inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium text-white bg-primary hover:bg-blue-600 transition-colors shadow-sm cursor-pointer">
            免费注册
          </button>
        </template>

        <!-- 已登录 -->
        <template v-else>
          <button v-if="paymentEnabled && !user.is_vip" @click="$emit('open-vip')" class="hidden sm:inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium text-primary bg-primary-light hover:bg-blue-100 transition-colors cursor-pointer">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
            </svg>
            开通 VIP
          </button>
          <span v-else class="hidden sm:inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-gradient-to-r from-yellow-400 to-orange-400 text-white shadow-sm">
            <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
            </svg>
            VIP
          </span>

          <!-- 用户下拉菜单 -->
          <div class="relative" ref="menuRef">
            <button @click="menuOpen = !menuOpen" class="flex items-center gap-2 px-3 py-2 rounded-full hover:bg-gray-50 transition-colors cursor-pointer">
              <div class="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-blue-600 flex items-center justify-center text-white text-sm font-semibold">
                {{ user.email[0].toUpperCase() }}
              </div>
              <svg class="w-4 h-4 text-text-muted transition-transform" :class="{ 'rotate-180': menuOpen }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            <div v-if="menuOpen" class="absolute right-0 top-full mt-2 w-56 bg-white rounded-xl border border-border shadow-xl py-2 animate-menu-in">
              <div class="px-4 py-2 border-b border-border">
                <p class="text-sm font-medium text-text-primary truncate">{{ user.email }}</p>
                <p class="text-xs text-text-muted mt-0.5">
                  {{ user.is_vip ? 'VIP 会员' : '免费用户' }}
                  <span v-if="user.is_vip && user.vip_expire_at" class="ml-1">· 到期 {{ formatDate(user.vip_expire_at) }}</span>
                </p>
              </div>
              <button v-if="paymentEnabled && !user.is_vip" @click="menuOpen = false; $emit('open-vip')" class="w-full text-left px-4 py-2.5 text-sm text-primary hover:bg-primary-light transition-colors cursor-pointer flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                </svg>
                开通 VIP
              </button>
              <button @click="menuOpen = false; $emit('open-library')" class="w-full text-left px-4 py-2.5 text-sm text-text-secondary hover:bg-gray-50 transition-colors cursor-pointer flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M3 6h7l2 2h9v11H3V6z" /></svg>
                课程资料库
              </button>
              <button @click="menuOpen = false; $emit('open-model-config')" class="w-full text-left px-4 py-2.5 text-sm text-text-secondary hover:bg-gray-50 transition-colors cursor-pointer flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.607 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                模型配置
              </button>
              <button v-if="user.is_admin" @click="menuOpen = false; $emit('open-cookie-config')" class="w-full text-left px-4 py-2.5 text-sm text-text-secondary hover:bg-gray-50 transition-colors cursor-pointer flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 2a10 10 0 100 20 10 10 0 00-10-10 3 3 0 01-3-3 3 3 0 01-3-3z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.5 9.5h.01M12 13h.01M15 16h.01" /></svg>
                Cookie 配置
              </button>
              <button @click="menuOpen = false; $emit('logout')" class="w-full text-left px-4 py-2.5 text-sm text-text-secondary hover:bg-gray-50 transition-colors cursor-pointer flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
                退出登录
              </button>
            </div>
          </div>
        </template>

        <!-- 移动端汉堡按钮 -->
        <button
          @click="mobileNavOpen = !mobileNavOpen"
          class="md:hidden inline-flex h-9 w-9 items-center justify-center rounded-lg text-text-secondary hover:bg-gray-50 hover:text-primary transition-colors cursor-pointer"
          aria-label="打开菜单"
        >
          <svg v-if="!mobileNavOpen" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
          <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 移动端下拉导航 -->
    <div v-if="mobileNavOpen" ref="mobileNavRef" class="md:hidden border-t border-border-light bg-white animate-menu-in max-h-[calc(100vh-4rem)] overflow-y-auto">
      <nav class="px-4 py-3 flex flex-col gap-1 text-sm text-text-secondary" aria-label="移动端导航">
        <a href="#features" @click="mobileNavOpen = false" class="px-3 py-2.5 rounded-lg hover:bg-gray-50 hover:text-primary transition-colors">功能特性</a>
        <a href="#how-to-use" @click="mobileNavOpen = false" class="px-3 py-2.5 rounded-lg hover:bg-gray-50 hover:text-primary transition-colors">使用教程</a>
        <a href="#comparison" @click="mobileNavOpen = false" class="px-3 py-2.5 rounded-lg hover:bg-gray-50 hover:text-primary transition-colors">工具对比</a>
        <a v-if="paymentEnabled" href="#pricing" @click="mobileNavOpen = false" class="px-3 py-2.5 rounded-lg hover:bg-gray-50 hover:text-primary transition-colors">套餐价格</a>

        <template v-if="user">
          <div class="my-1 border-t border-border-light"></div>
          <button @click="mobileNavOpen = false; $emit('open-library')" class="px-3 py-2.5 rounded-lg text-left hover:bg-gray-50 hover:text-primary transition-colors">课程资料库</button>
          <button @click="mobileNavOpen = false; $emit('open-model-config')" class="px-3 py-2.5 rounded-lg text-left hover:bg-gray-50 hover:text-primary transition-colors">模型配置</button>
          <button v-if="user.is_admin" @click="mobileNavOpen = false; $emit('open-cookie-config')" class="px-3 py-2.5 rounded-lg text-left hover:bg-gray-50 hover:text-primary transition-colors">Cookie 配置</button>
          <button v-if="paymentEnabled && !user.is_vip" @click="mobileNavOpen = false; $emit('open-vip')" class="px-3 py-2.5 rounded-lg text-left font-medium text-primary hover:bg-primary-light transition-colors">开通 VIP</button>
          <button @click="mobileNavOpen = false; $emit('logout')" class="px-3 py-2.5 rounded-lg text-left text-text-secondary hover:bg-gray-50 hover:text-primary transition-colors">退出登录</button>
        </template>

        <template v-else>
          <div class="my-1 border-t border-border-light"></div>
          <button @click="mobileNavOpen = false; $emit('login')" class="px-3 py-2.5 rounded-lg text-left hover:bg-gray-50 hover:text-primary transition-colors">登录</button>
          <button v-if="registrationEnabled" @click="mobileNavOpen = false; $emit('register')" class="px-3 py-2.5 rounded-lg text-left font-medium text-primary hover:bg-primary-light transition-colors">免费注册</button>
        </template>
      </nav>
    </div>
  </header>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

defineProps({
  user: { type: Object, default: null },
  paymentEnabled: { type: Boolean, default: true },
  registrationEnabled: { type: Boolean, default: false },
})

defineEmits(['login', 'register', 'logout', 'open-vip', 'open-model-config', 'open-cookie-config', 'open-library'])

const menuOpen = ref(false)
const menuRef = ref(null)
const mobileNavOpen = ref(false)
const mobileNavRef = ref(null)

function formatDate(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function handleClickOutside(e) {
  if (menuRef.value && !menuRef.value.contains(e.target)) {
    menuOpen.value = false
  }
}

onMounted(() => document.addEventListener('click', handleClickOutside))
onBeforeUnmount(() => document.removeEventListener('click', handleClickOutside))
</script>

<style scoped>
@keyframes menu-in {
  from { opacity: 0; transform: translateY(-4px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.animate-menu-in {
  animation: menu-in 0.15s ease-out;
}
</style>
