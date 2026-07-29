<template>
  <div class="bg-white rounded-2xl border border-border shadow-lg overflow-hidden h-full flex flex-col">
        <!-- 标签页导航 -->
        <div class="flex overflow-x-auto border-b border-border-light">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            @click="switchTab(tab.key)"
            :class="[
              'relative flex shrink-0 items-center gap-2 px-4 py-3.5 text-sm font-medium transition-all cursor-pointer sm:px-5',
              activeTab === tab.key
                ? 'text-primary'
                : 'text-text-secondary hover:text-text-primary'
            ]"
          >
            <span>{{ tab.icon }}</span>
            <span>{{ tab.label }}</span>
            <div
              v-if="activeTab === tab.key"
              class="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"
            ></div>
          </button>
        </div>

        <!-- 内容区域 -->
        <div class="p-5 sm:p-6 min-h-[400px] flex-1 overflow-y-auto">
          <!-- 加载状态 -->
          <div v-if="loading && !summaryText && activeTab === 'summary'" class="flex flex-col items-center justify-center py-16">
            <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-4"></div>
            <p class="text-text-secondary text-sm">{{ loadingMessage }}</p>
            <div v-if="progressPercent !== null" class="mt-4 w-full max-w-[280px]">
              <div class="h-2 overflow-hidden rounded-full bg-primary/10">
                <div
                  class="h-full rounded-full bg-primary transition-[width] duration-300 ease-out"
                  :style="{ width: `${progressPercent}%` }"
                ></div>
              </div>
              <p class="mt-1.5 text-center text-xs tabular-nums text-text-muted">{{ progressPercent }}%</p>
            </div>
          </div>

          <!-- 总结摘要 Tab -->
          <div v-show="activeTab === 'summary'">
            <div v-if="summaryText || regeneratingPart === 'summary'" class="mb-3 flex items-center justify-end gap-2">
              <button
                v-if="summaryText"
                @click="regenerateSummary"
                :disabled="loading || !!regeneratingPart"
                class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-slate-100 hover:text-primary disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
                title="忽略缓存，重新生成总结"
              >
                <svg class="h-3.5 w-3.5" :class="{ 'animate-spin': regeneratingPart === 'summary' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v6h6M20 20v-6h-6M5 19A9 9 0 0119 5M19 5h-5M19 5v5" />
                </svg>
                {{ regeneratingPart === 'summary' ? '重新生成中...' : '重新生成' }}
              </button>
              <button
                v-if="summaryText"
                @click="copySummary"
                class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary-light cursor-pointer"
                title="复制 Markdown 摘要"
              >
                <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V5a2 2 0 012-2h7a2 2 0 012 2v10a2 2 0 01-2 2h-2M7 7h6a2 2 0 012 2v10a2 2 0 01-2 2H7a2 2 0 01-2-2V9a2 2 0 012-2z" />
                </svg>
                {{ summaryCopied ? '已复制' : '复制摘要' }}
              </button>
            </div>
            <div
              v-if="summaryText"
              class="prose prose-slate prose-sm max-w-none summary-prose"
              @click="handleSummaryClick"
              v-html="renderedSummary"
            ></div>
            <div v-if="loading && summaryText" class="mt-2 inline-flex items-center gap-1.5 text-xs text-text-muted">
              <span class="w-1.5 h-1.5 bg-primary rounded-full animate-pulse"></span>
              AI 正在生成中...
            </div>
            <!-- 免费用户剩余次数提示 -->
            <div v-if="quotaInfo && quotaInfo.remaining >= 0 && !loading" class="mt-4 p-3 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-between">
              <span class="text-sm text-blue-700">
                今日剩余 AI 总结次数：<strong>{{ quotaInfo.remaining }}</strong> / {{ quotaInfo.limit }}
              </span>
              <button v-if="quotaInfo.remaining <= 1" @click="emit('need-vip')" class="text-xs font-medium text-primary hover:underline cursor-pointer">
                升级 VIP 无限使用
              </button>
            </div>
          </div>

          <!-- 字幕文本 Tab -->
          <div v-show="activeTab === 'subtitle'">
            <div v-if="subtitleData.segments && subtitleData.segments.length > 0">
              <div class="flex items-center justify-between mb-4">
                <div class="text-sm text-text-secondary">
                  共 {{ subtitleData.segments.length }} 条字幕
                  <span v-if="subtitleData.language" class="ml-2 px-2 py-0.5 bg-primary-light text-primary rounded-full text-xs">
                    {{ subtitleTypeLabel(subtitleData.subtitle_type) }} · {{ subtitleData.language }}
                  </span>
                  <span v-if="subtitleData.cache_hit" class="ml-2 rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                    历史缓存
                  </span>
                </div>
                <div class="flex items-center gap-3">
                  <!-- 下载字幕按钮 -->
                  <div class="relative" ref="subtitleDropdownRef">
                    <button
                      @click="showSubtitleDropdown = !showSubtitleDropdown"
                      class="flex items-center gap-1.5 text-xs text-primary hover:text-primary-dark transition-colors cursor-pointer px-2.5 py-1.5 rounded-lg hover:bg-primary-light"
                    >
                      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      下载字幕
                      <svg class="w-3 h-3 transition-transform" :class="showSubtitleDropdown ? 'rotate-180' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    <div
                      v-if="showSubtitleDropdown"
                      class="absolute right-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-border-light py-1 z-10 min-w-[120px]"
                    >
                      <button
                        v-for="fmt in subtitleFormats"
                        :key="fmt.key"
                        @click="downloadSubtitle(fmt.key)"
                        class="w-full text-left px-3 py-2 text-xs text-text-primary hover:bg-bg-section transition-colors cursor-pointer flex items-center justify-between"
                      >
                        <span>{{ fmt.label }}</span>
                        <span class="text-text-muted">.{{ fmt.ext }}</span>
                      </button>
                    </div>
                  </div>
                  <button
                    @click="subtitleExpanded = !subtitleExpanded"
                    class="text-xs text-primary hover:text-primary-dark transition-colors cursor-pointer"
                  >
                    {{ subtitleExpanded ? '收起' : '展开全部' }}
                  </button>
                </div>
              </div>
              <div
                ref="subtitleListRef"
                :class="['space-y-1 overflow-y-auto', subtitleExpanded ? 'max-h-none' : 'max-h-[500px]']"
              >
                <div
                  v-for="(seg, idx) in subtitleData.segments"
                  :key="idx"
                  :data-subtitle-index="idx"
                  :class="[
                    'flex gap-3 py-2 px-3 rounded-lg transition-colors group',
                    highlightedSubtitleIndex === idx ? 'bg-amber-50 ring-1 ring-amber-200' : 'hover:bg-bg-section',
                  ]"
                >
                  <span class="flex-shrink-0 text-xs text-primary font-mono pt-0.5 min-w-[60px]">
                    {{ formatTime(seg.start) }}
                  </span>
                  <span class="text-sm text-text-primary leading-relaxed">{{ seg.text }}</span>
                </div>
              </div>
            </div>
            <div v-else-if="!loading" class="flex flex-col items-center justify-center py-16 text-text-muted">
              <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p class="text-sm">该视频暂无可用字幕</p>
            </div>
            <div v-else class="flex flex-col items-center justify-center py-16">
              <div class="w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-3"></div>
              <p class="text-text-muted text-sm">{{ loadingMessage }}</p>
              <div v-if="progressPercent !== null" class="mt-4 w-full max-w-[280px]">
                <div class="h-2 overflow-hidden rounded-full bg-primary/10">
                  <div
                    class="h-full rounded-full bg-primary transition-[width] duration-300 ease-out"
                    :style="{ width: `${progressPercent}%` }"
                  ></div>
                </div>
                <p class="mt-1.5 text-center text-xs tabular-nums text-text-muted">{{ progressPercent }}%</p>
              </div>
            </div>
          </div>

          <!-- 思维导图 Tab -->
          <div v-show="activeTab === 'mindmap'">
            <div v-if="mindmapMarkdown || regeneratingPart === 'mindmap'" class="relative">
              <!-- 工具栏 -->
              <div class="flex items-center justify-end gap-2 mb-3">
                <button
                  @click="regenerateMindmap"
                  :disabled="loading || !!regeneratingPart"
                  class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-slate-100 hover:text-primary disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
                  title="忽略缓存，重新生成思维导图"
                >
                  <svg class="h-3.5 w-3.5" :class="{ 'animate-spin': regeneratingPart === 'mindmap' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v6h6M20 20v-6h-6M5 19A9 9 0 0119 5M19 5h-5M19 5v5" />
                  </svg>
                  {{ regeneratingPart === 'mindmap' ? '重新生成中...' : '重新生成' }}
                </button>
                <button
                  v-if="mindmapMarkdown"
                  @click="copyMindmap"
                  class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary-light cursor-pointer"
                  title="复制思维导图 Markdown"
                >
                  <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V5a2 2 0 012-2h7a2 2 0 012 2v10a2 2 0 01-2 2h-2M7 7h6a2 2 0 012 2v10a2 2 0 01-2 2H7a2 2 0 01-2-2V9a2 2 0 012-2z" />
                  </svg>
                  {{ mindmapCopied ? '已复制' : '复制 Markdown' }}
                </button>
                <button
                  @click="downloadMindmapPng"
                  class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg text-primary hover:bg-primary-light transition-colors cursor-pointer"
                  title="下载 PNG 图片"
                >
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  PNG
                </button>
                <button
                  @click="downloadMindmapSvg"
                  class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg text-primary hover:bg-primary-light transition-colors cursor-pointer"
                  title="下载 SVG 矢量图"
                >
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  SVG
                </button>
                <button
                  @click="toggleFullscreen"
                  class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg text-primary hover:bg-primary-light transition-colors cursor-pointer"
                  :title="isFullscreen ? '退出全屏' : '全屏展示'"
                >
                  <svg v-if="!isFullscreen" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                  </svg>
                  <svg v-else class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
                  </svg>
                  {{ isFullscreen ? '退出全屏' : '全屏' }}
                </button>
              </div>
              <div
                ref="mindmapContainer"
                class="mindmap-wrapper w-full border border-border-light rounded-xl bg-white overflow-hidden"
                :class="isFullscreen ? 'mindmap-fullscreen' : 'min-h-[500px]'"
              >
                <svg ref="mindmapSvg" class="w-full h-full" :style="isFullscreen ? 'height: 100%' : 'min-height: 500px'"></svg>
                <!-- 全屏模式下的退出按钮 -->
                <button
                  v-if="isFullscreen"
                  @click="toggleFullscreen"
                  class="fixed top-4 right-4 z-50 flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white/90 backdrop-blur shadow-lg text-sm text-text-primary hover:bg-white transition-colors cursor-pointer border border-border-light"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  退出全屏
                </button>
              </div>
            </div>
            <div v-else-if="loading || regeneratingPart === 'mindmap'" class="flex flex-col items-center justify-center py-16">
              <div class="w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-3"></div>
              <p class="text-text-muted text-sm">{{ regeneratingPart === 'mindmap' ? '正在重新生成思维导图...' : '正在生成思维导图...' }}</p>
            </div>
            <div v-else class="flex flex-col items-center justify-center py-16 text-text-muted">
              <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
              <p class="text-sm">请先生成总结以查看思维导图</p>
            </div>
          </div>

          <!-- 理解测试 Tab -->
          <div v-show="activeTab === 'quiz'">
            <div v-if="quizLoading && !quizData" class="flex flex-col items-center justify-center py-16">
              <div class="mb-4 h-11 w-11 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
              <p class="text-sm text-text-secondary">{{ quizProgress.message || 'AI 正在根据视频内容命题...' }}</p>
              <p class="mt-1 text-xs text-text-muted">题目会按题型分批生成并立即显示</p>
            </div>

            <div v-else-if="quizError && !quizData" class="flex flex-col items-center justify-center py-16 text-center">
              <svg class="mb-3 h-10 w-10 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v4m0 4h.01M10.3 3.7L2.6 17a2 2 0 001.73 3h15.34a2 2 0 001.73-3L13.7 3.7a2 2 0 00-3.4 0z" />
              </svg>
              <p class="max-w-sm text-sm text-text-secondary">{{ quizError }}</p>
              <button
                v-if="!loading"
                @click="loadQuiz"
                class="mt-4 text-sm font-medium text-primary hover:text-primary-dark cursor-pointer"
              >重新生成</button>
            </div>

            <div v-else-if="quizData">
              <div
                v-if="quizLoading"
                class="mb-4 border-y border-primary/15 bg-primary/[0.04] px-1 py-3"
                aria-live="polite"
              >
                <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span class="font-medium text-primary">{{ quizProgress.message || '正在生成下一批题目...' }}</span>
                  <span class="tabular-nums text-text-muted">
                    已生成 {{ quizProgress.completedQuestions || quizData.questions.length }} / {{ quizProgress.totalQuestions || 16 }} 题
                  </span>
                </div>
                <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-primary/10">
                  <div
                    class="h-full rounded-full bg-primary transition-[width] duration-500"
                    :style="{ width: `${quizGenerationPercent}%` }"
                  ></div>
                </div>
              </div>

              <div v-if="quizError" class="mb-4 flex flex-wrap items-center justify-between gap-3 border-y border-amber-200 bg-amber-50 px-1 py-3 text-xs text-amber-800">
                <span>{{ quizError }}</span>
                <button @click="regenerateQuiz" class="shrink-0 font-medium text-amber-900 hover:text-primary cursor-pointer">重新生成</button>
              </div>

              <div v-if="quizHistory.length || quizResult || quizSavedAt" class="mb-4 flex flex-wrap items-center justify-end gap-2">
                <label v-if="quizHistory.length" class="flex min-w-0 items-center gap-2 text-xs text-text-muted">
                  <span class="shrink-0">历史答卷</span>
                  <select
                    v-model="selectedHistoryId"
                    @change="loadQuizHistory($event.target.value)"
                    class="h-8 max-w-[240px] rounded-md border border-border bg-white px-2 text-xs text-text-primary focus:border-primary focus:outline-none"
                  >
                    <option value="">当前答卷</option>
                    <option v-for="attempt in quizHistory" :key="attempt.id" :value="attempt.id">
                      {{ formatHistoryLabel(attempt) }}
                    </option>
                  </select>
                </label>
                <span v-if="quizSavedAt" class="text-xs text-emerald-700">已保存到磁盘</span>
                <button
                  v-if="quizResult"
                  @click="copyQuizReport"
                  class="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-xs font-medium text-text-secondary transition-colors hover:border-primary hover:text-primary cursor-pointer"
                  title="复制适合粘贴到语雀的 Markdown 测试报告"
                >
                  <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V5a2 2 0 012-2h7a2 2 0 012 2v10a2 2 0 01-2 2h-2M7 7h6a2 2 0 012 2v10a2 2 0 01-2 2H7a2 2 0 01-2-2V9a2 2 0 012-2z" />
                  </svg>
                  {{ quizCopied ? '已复制' : '复制测试报告' }}
                </button>
              </div>
              <div class="flex flex-wrap items-start justify-between gap-4 border-b border-border-light pb-4">
                <div>
                  <p class="text-xs font-medium text-text-muted">视频内容理解测试</p>
                  <h3 class="mt-1 text-lg font-semibold text-text-primary">{{ quizData.title }}</h3>
                  <p class="mt-1 text-xs text-text-muted">
                    {{ quizLoading ? `已生成 ${quizData.questions.length} / ${quizProgress.totalQuestions || 16} 题` : `${quizData.questions.length} 题` }}
                    · 满分 {{ quizData.max_score }} 分 · 已答 {{ answeredQuizCount }} 题
                  </p>
                </div>
                <div v-if="quizResult" class="text-right">
                  <div class="flex items-baseline justify-end gap-1">
                    <strong class="text-3xl font-semibold tabular-nums text-primary">{{ quizResult.total_score }}</strong>
                    <span class="text-sm text-text-muted">/ {{ quizResult.max_score }}</span>
                  </div>
                  <p class="mt-1 text-xs font-medium" :class="scoreToneClass(quizResult.percentage)">
                    {{ scoreSummary(quizResult.percentage) }}
                  </p>
                </div>
              </div>

              <div class="mt-4">
                <div class="flex items-center justify-between text-xs text-text-muted">
                  <span>{{ quizResult ? '阅卷完成' : '答题进度' }}</span>
                  <span class="tabular-nums">{{ quizResult ? quizResult.percentage : quizCompletionPercent }}%</span>
                </div>
                <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-primary/10">
                  <div
                    class="h-full rounded-full bg-primary transition-[width] duration-300"
                    :style="{ width: `${quizResult ? quizResult.percentage : quizCompletionPercent}%` }"
                  ></div>
                </div>
              </div>

              <div class="mt-2 max-h-[640px] divide-y divide-border-light overflow-y-auto pr-2 quiz-scroll-region">
                <section
                  v-for="(question, index) in quizData.questions"
                  :key="question.id"
                  class="py-5"
                >
                  <div class="flex items-start gap-3">
                    <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-light text-xs font-semibold text-primary">
                      {{ index + 1 }}
                    </span>
                    <div class="min-w-0 flex-1">
                      <div class="flex flex-wrap items-center justify-between gap-2">
                        <span class="text-xs font-medium text-text-muted">{{ questionTypeLabel(question.type) }}</span>
                        <span class="text-xs tabular-nums text-text-muted">{{ question.points }} 分</span>
                      </div>
                      <p class="mt-1.5 text-sm font-medium leading-6 text-text-primary">{{ question.question }}</p>

                      <div v-if="!['short_answer', 'analysis'].includes(question.type)" class="mt-3 space-y-2">
                        <label
                          v-for="option in question.options"
                          :key="option.key"
                          :class="optionClass(question, option.key)"
                          class="flex min-h-10 cursor-pointer items-start gap-3 rounded-md border px-3 py-2 text-sm transition-colors"
                        >
                          <input
                            :type="question.type === 'multiple' ? 'checkbox' : 'radio'"
                            :name="`quiz-${question.id}`"
                            :checked="isQuizOptionSelected(question.id, option.key)"
                            :disabled="Boolean(quizResult)"
                            @change="updateQuizOption(question, option.key)"
                            class="mt-0.5 h-4 w-4 shrink-0 accent-current"
                          />
                          <span class="font-medium text-text-secondary">{{ option.key }}</span>
                          <span class="leading-5 text-text-primary">{{ option.text }}</span>
                        </label>
                      </div>

                      <textarea
                        v-else
                        v-model="quizAnswers[question.id]"
                        :disabled="Boolean(quizResult)"
                        rows="4"
                        placeholder="请结合视频内容作答..."
                        class="mt-3 w-full resize-y rounded-md border border-border bg-white px-3 py-2.5 text-sm leading-6 text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:bg-bg-section"
                      ></textarea>

                      <div
                        v-if="quizResultById[String(question.id)]"
                        class="mt-3 border-l-2 py-1 pl-3"
                        :class="quizResultById[String(question.id)].correct ? 'border-emerald-500' : 'border-amber-500'"
                      >
                        <div class="flex items-center justify-between gap-3">
                          <span
                            class="text-xs font-semibold"
                            :class="quizResultById[String(question.id)].correct ? 'text-emerald-700' : 'text-amber-700'"
                          >
                            {{ quizResultById[String(question.id)].correct ? '掌握' : '需要复习' }}
                          </span>
                          <span class="text-xs tabular-nums text-text-muted">
                            {{ quizResultById[String(question.id)].awarded_points }} / {{ quizResultById[String(question.id)].max_points }} 分
                          </span>
                        </div>
                        <p class="mt-1.5 text-xs leading-5 text-text-secondary">{{ quizResultById[String(question.id)].feedback }}</p>
                        <p class="mt-1.5 text-xs leading-5 text-text-secondary">
                          <strong class="font-medium text-text-primary">参考答案：</strong>{{ quizReferenceAnswer(question) }}
                        </p>
                        <p v-if="question.explanation" class="mt-1 text-xs leading-5 text-text-muted">
                          <strong class="font-medium text-text-secondary">解析：</strong>{{ question.explanation }}
                        </p>
                      </div>
                    </div>
                  </div>
                </section>
              </div>

              <p v-if="quizResult?.grading_warning" class="border-t border-border-light py-3 text-xs text-amber-700">
                {{ quizResult.grading_warning }}
              </p>

              <div class="flex flex-wrap items-center justify-between gap-3 border-t border-border-light pt-4">
                <button
                  @click="regenerateQuiz"
                  :disabled="quizGrading || quizLoading"
                  class="text-sm font-medium text-text-secondary hover:text-primary disabled:opacity-50 cursor-pointer"
                >重新出题</button>
                <div class="flex items-center gap-3">
                  <button
                    v-if="quizResult"
                    @click="resetQuizAnswers"
                    class="h-10 rounded-md border border-border px-4 text-sm font-medium text-text-secondary hover:border-primary hover:text-primary cursor-pointer"
                  >重新作答</button>
                  <button
                    v-else
                    @click="submitQuiz"
                    :disabled="answeredQuizCount === 0 || quizGrading || quizLoading"
                    class="flex h-10 min-w-[112px] items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
                  >
                    <svg v-if="quizGrading" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z"></path>
                    </svg>
                    {{ quizGrading ? 'AI 阅卷中...' : '提交答卷' }}
                  </button>
                </div>
              </div>
            </div>

            <div v-else class="flex flex-col items-center justify-center py-16 text-center text-text-muted">
              <p class="text-sm">视频内容准备完成后，将自动生成理解测试。</p>
            </div>
          </div>

          <!-- AI 问答 Tab -->
          <div v-show="activeTab === 'qa'">
            <div class="space-y-4">
              <div v-if="chatMessages.length" class="flex items-center justify-end gap-2">
                <button
                  @click="clearChatHistory"
                  :disabled="chatLoading || clearingChat"
                  class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-slate-100 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
                  title="清空问答历史，重新开始提问"
                >
                  <svg class="h-3.5 w-3.5" :class="{ 'animate-spin': clearingChat }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7h6m-1-3H10a1 1 0 00-1 1v2h8V5a1 1 0 00-1-1z" />
                  </svg>
                  {{ clearingChat ? '清空中...' : '清空问答' }}
                </button>
                <button
                  @click="copyChatTranscript"
                  class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary-light cursor-pointer"
                  title="复制问答记录"
                >
                  <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V5a2 2 0 012-2h7a2 2 0 012 2v10a2 2 0 01-2 2h-2M7 7h6a2 2 0 012 2v10a2 2 0 01-2 2H7a2 2 0 01-2-2V9a2 2 0 012-2z" />
                  </svg>
                  {{ chatCopied ? '已复制' : '复制问答' }}
                </button>
              </div>
              <!-- 对话列表 -->
              <div
                ref="chatContainer"
                class="space-y-4 max-h-[400px] overflow-y-auto pr-1"
              >
                <div v-if="chatMessages.length === 0" class="flex flex-col items-center justify-center py-12 text-text-muted">
                  <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                  <p class="text-sm mb-1">向 AI 提问关于这个视频的任何问题</p>
                  <p class="text-xs">例如："这个视频的核心观点是什么？"</p>
                </div>
                <div
                  v-for="(msg, idx) in chatMessages"
                  :key="idx"
                  :class="[
                    'flex',
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  ]"
                >
                  <div
                    :class="[
                      'max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed',
                      msg.role === 'user'
                        ? 'bg-primary text-white rounded-br-md'
                        : 'bg-bg-section text-text-primary rounded-bl-md border border-border-light'
                    ]"
                  >
                    <div v-if="msg.role === 'assistant'" class="chat-prose prose prose-slate prose-sm max-w-none" v-html="renderMarkdown(msg.content)"></div>
                    <span v-else>{{ msg.content }}</span>
                    <div
                      v-if="msg.role === 'assistant' && msg.loading && !msg.content && msg.status"
                      class="text-xs text-text-muted"
                    >{{ msg.status }}</div>
                    <span
                      v-if="msg.role === 'assistant' && msg.loading"
                      class="inline-block w-1.5 h-4 bg-primary/60 rounded-sm animate-pulse ml-0.5 align-text-bottom"
                    ></span>
                  </div>
                </div>
              </div>

              <!-- 输入区域 -->
              <div class="flex gap-2 pt-3 border-t border-border-light">
                <input
                  v-model="chatInput"
                  @keydown.enter.prevent="sendQuestion"
                  type="text"
                  placeholder="输入你的问题..."
                  class="flex-1 h-11 px-4 rounded-xl border border-border bg-white text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                  :disabled="chatLoading"
                />
                <button
                  @click="sendQuestion"
                  :disabled="!chatInput.trim() || chatLoading"
                  class="h-11 px-5 rounded-xl bg-primary hover:bg-primary-dark text-white text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1.5"
                >
                  <svg v-if="chatLoading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                  发送
                </button>
              </div>
            </div>
          </div>

          <div v-show="activeTab === 'notes'">
            <div v-if="!libraryVideoId" class="flex flex-col items-center justify-center py-14 text-center text-text-muted"><p class="text-sm">视频进入课程资料库后即可记录时间点笔记</p></div>
            <template v-else>
              <form @submit.prevent="saveCurrentVideoNote" class="rounded-md border border-border bg-gray-50/70 p-4">
                <div class="flex flex-wrap items-center gap-2"><label class="text-xs text-text-muted">视频时间点</label><input v-model.number="videoNoteTime" type="number" min="0" class="h-9 w-28 rounded-md border border-border bg-white px-3 text-sm" /><span class="text-xs text-text-muted">秒 · {{ formatTime(videoNoteTime || 0) }}</span></div>
                <textarea v-model.trim="videoNoteContent" rows="4" placeholder="记录关键观点、疑问或你自己的理解..." class="mt-3 w-full resize-y rounded-md border border-border bg-white px-3 py-2 text-sm leading-6 focus:border-primary focus:outline-none"></textarea>
                <div class="mt-3 flex justify-end"><button :disabled="savingVideoNote || !videoNoteContent" class="h-9 rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-50 cursor-pointer">{{ savingVideoNote ? '保存中...' : '保存时间点笔记' }}</button></div>
              </form>
              <div v-if="!videoNotes.length" class="py-10 text-center text-sm text-text-muted">当前视频还没有笔记</div>
              <div v-else class="mt-4 divide-y divide-border-light rounded-md border border-border"><article v-for="note in videoNotes" :key="note.id" class="p-4"><span class="text-xs font-medium text-primary">{{ formatTime(note.time_seconds) }}</span><p class="mt-1.5 whitespace-pre-wrap text-sm leading-6 text-text-primary">{{ note.content }}</p></article></div>
            </template>
          </div>
        </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import { Transformer } from 'markmap-lib'
import { Markmap } from 'markmap-view'
import {
  summarizeVideo,
  chatWithVideo,
  clearVideoChat,
  generateVideoQuizStream,
  gradeVideoQuiz,
  getQuizState,
  saveQuizState,
} from '../api/summarize.js'
import { createCourseNote, getVideoNotes } from '../api/library.js'

const props = defineProps({
  videoUrl: { type: String, required: true },
  videoTitle: { type: String, default: '' },
  user: { type: Object, default: null },
  force: { type: Boolean, default: false },
  libraryVideoId: { type: Number, default: null },
})
const emit = defineEmits(['loading-change', 'need-login', 'need-vip'])

const tabs = [
  { key: 'summary', label: '总结摘要', icon: '📝' },
  { key: 'subtitle', label: '字幕文本', icon: '📄' },
  { key: 'mindmap', label: '思维导图', icon: '🧠' },
  { key: 'quiz', label: '理解测试', icon: '✓' },
  { key: 'qa', label: 'AI 问答', icon: '💬' },
  { key: 'notes', label: '时间点笔记', icon: '✎' },
]

const activeTab = ref('summary')
const loading = ref(false)
const loadingMessage = ref('正在提取视频字幕...')
const progressPercent = ref(0)
const regeneratingPart = ref('')
const clearingChat = ref(false)
const videoNotes = ref([])
const videoNoteTime = ref(0)
const videoNoteContent = ref('')
const savingVideoNote = ref(false)

const summaryText = ref('')
const subtitleData = ref({ segments: [], has_subtitle: false })
const subtitleExpanded = ref(false)
const subtitleListRef = ref(null)
const highlightedSubtitleIndex = ref(-1)
let subtitleHighlightTimer = null
const mindmapMarkdown = ref('')
const mindmapSvg = ref(null)
const mindmapContainer = ref(null)
let markmapInstance = null

const chatMessages = ref([])
const chatInput = ref('')
const chatLoading = ref(false)
const chatContainer = ref(null)

const quizData = ref(null)
const quizAnswers = ref({})
const quizResult = ref(null)
const quizLoading = ref(false)
const quizGrading = ref(false)
const quizError = ref('')
const quizHistory = ref([])
const activeQuizAttemptId = ref('')
const selectedHistoryId = ref('')
const quizHistoryInitialized = ref(false)
const quizSavedAt = ref(null)
const quizCopied = ref(false)
const quizProgress = ref({
  message: '',
  batchIndex: 0,
  totalBatches: 5,
  completedQuestions: 0,
  totalQuestions: 16,
  percent: 0,
})
const summaryCopied = ref(false)
const mindmapCopied = ref(false)
const chatCopied = ref(false)
let quizSaveTimer = null

const answeredQuizCount = computed(() => {
  if (!quizData.value) return 0
  return quizData.value.questions.filter((question) => {
    const answer = quizAnswers.value[question.id]
    return Array.isArray(answer) ? answer.length > 0 : String(answer || '').trim().length > 0
  }).length
})

const quizResultById = computed(() => {
  const map = {}
  for (const result of quizResult.value?.results || []) {
    map[String(result.id)] = result
  }
  return map
})

const quizCompletionPercent = computed(() => {
  const total = quizData.value?.questions?.length || 0
  return total ? Math.round(answeredQuizCount.value * 100 / total) : 0
})

const quizGenerationPercent = computed(() => {
  const percent = Number(quizProgress.value.percent)
  if (Number.isFinite(percent)) return Math.max(0, Math.min(100, Math.round(percent)))
  const total = quizProgress.value.totalQuestions || 16
  return Math.round((quizProgress.value.completedQuestions || 0) * 100 / total)
})

const renderedSummary = ref('')

// 思维导图全屏状态
const isFullscreen = ref(false)

// 字幕下载下拉菜单
const showSubtitleDropdown = ref(false)
const subtitleDropdownRef = ref(null)
const subtitleFormats = [
  { key: 'srt', label: 'SRT 字幕', ext: 'srt' },
  { key: 'vtt', label: 'VTT 字幕', ext: 'vtt' },
  { key: 'txt', label: '纯文本', ext: 'txt' },
]

// 配置 marked
marked.setOptions({
  breaks: true,
  gfm: true,
})

watch(loading, (val) => {
  emit('loading-change', val)
})

watch(summaryText, (val) => {
  renderedSummary.value = renderMarkdown(val)
})

watch(mindmapMarkdown, async (val) => {
  if (!val) return
  const cleaned = sanitizeMindmapMarkdown(val)
  if (cleaned !== val) {
    mindmapMarkdown.value = cleaned
    return
  }
  if (activeTab.value === 'mindmap') {
    await nextTick()
    renderMindmap(cleaned)
  }
})

watch(activeTab, async (tab) => {
  if (tab === 'mindmap' && mindmapMarkdown.value) {
    await nextTick()
    renderMindmap(mindmapMarkdown.value)
    // 隐藏态渲染时尺寸为 0，切回后补一次自适应
    requestAnimationFrame(() => {
      try { markmapInstance?.fit?.() } catch {}
    })
  }
})

watch(quizAnswers, () => {
  persistQuizState()
}, { deep: true })

function renderMarkdown(text) {
  if (!text) return ''
  const withTimestampButtons = String(text).replace(
    /\[(\d{2}):([0-5]\d):([0-5]\d)\]/g,
    (_, hours, minutes, seconds) => {
      const totalSeconds = Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds)
      return `<button type="button" class="summary-timestamp" data-summary-seconds="${totalSeconds}" title="定位到对应字幕">[${hours}:${minutes}:${seconds}]</button>`
    },
  )
  return marked.parse(withTimestampButtons)
}

async function handleSummaryClick(event) {
  const button = event.target.closest?.('[data-summary-seconds]')
  if (!button) return
  const seconds = Number(button.dataset.summarySeconds)
  const segments = subtitleData.value.segments || []
  if (!Number.isFinite(seconds) || !segments.length) return

  let nearestIndex = 0
  let nearestDistance = Number.POSITIVE_INFINITY
  segments.forEach((segment, index) => {
    const distance = Math.abs(Number(segment.start || 0) - seconds)
    if (distance < nearestDistance) {
      nearestDistance = distance
      nearestIndex = index
    }
  })

  activeTab.value = 'subtitle'
  subtitleExpanded.value = true
  highlightedSubtitleIndex.value = nearestIndex
  if (subtitleHighlightTimer) window.clearTimeout(subtitleHighlightTimer)
  subtitleHighlightTimer = window.setTimeout(() => {
    highlightedSubtitleIndex.value = -1
  }, 4000)

  await nextTick()
  const row = subtitleListRef.value?.querySelector(`[data-subtitle-index="${nearestIndex}"]`)
  row?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function sanitizeMindmapMarkdown(text) {
  let cleaned = String(text || '').trim()
  if (!cleaned) return ''

  const fullFence = cleaned.match(/^```(?:markdown|md|markmap)?\s*\n([\s\S]*?)\n?```\s*$/i)
  if (fullFence) {
    cleaned = fullFence[1].trim()
  } else {
    cleaned = cleaned.replace(/^```(?:markdown|md|markmap)?\s*\n?/i, '')
    cleaned = cleaned.replace(/\n?```\s*$/i, '').trim()
    if (cleaned.includes('```')) {
      const parts = cleaned.split(/```(?:markdown|md|markmap)?/i)
      const candidates = parts.map(part => part.replace(/^`+|`+$/g, '').trim()).filter(part => part.includes('#'))
      if (candidates.length) {
        cleaned = candidates.sort((a, b) => b.length - a.length)[0]
      }
    }
  }

  const lines = cleaned.split(/\r?\n/)
  const start = lines.findIndex(line => /^#{1,6}\s+\S/.test(line.trim()))
  if (start > 0) cleaned = lines.slice(start).join('\n').trim()
  return cleaned
}

function renderMindmap(md) {
  if (!mindmapSvg.value) return
  const cleaned = sanitizeMindmapMarkdown(md)
  if (!cleaned) return
  try {
    mindmapSvg.value.innerHTML = ''
    const transformer = new Transformer()
    const { root } = transformer.transform(cleaned)
    markmapInstance = Markmap.create(mindmapSvg.value, {
      autoFit: true,
      duration: 300,
      maxWidth: 320,
    }, root)
    requestAnimationFrame(() => {
      try { markmapInstance?.fit?.() } catch {}
    })
  } catch (e) {
    console.warn('思维导图渲染失败:', e)
  }
}

function formatTime(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

function subtitleTypeLabel(type) {
  if (type === 'manual') return '人工字幕'
  if (type === 'transcription') return 'AI 语音转写'
  return '自动字幕'
}

function switchTab(tabKey) {
  activeTab.value = tabKey
  if (tabKey === 'notes') loadCurrentVideoNotes()
  if (tabKey === 'quiz' && !quizData.value && !quizLoading.value) {
    loadQuiz()
  }
  if (tabKey === 'mindmap' && mindmapMarkdown.value) {
    nextTick(() => {
      renderMindmap(mindmapMarkdown.value)
      requestAnimationFrame(() => {
        try { markmapInstance?.fit?.() } catch {}
      })
    })
  }
}

async function loadCurrentVideoNotes() {
  if (!props.libraryVideoId) return
  try {
    videoNotes.value = await getVideoNotes(props.libraryVideoId)
  } catch (err) {
    console.warn('读取视频笔记失败:', err)
  }
}

async function saveCurrentVideoNote() {
  if (!props.libraryVideoId || !videoNoteContent.value || savingVideoNote.value) return
  savingVideoNote.value = true
  try {
    await createCourseNote(
      props.libraryVideoId,
      videoNoteContent.value,
      videoNoteTime.value || 0,
    )
    videoNoteContent.value = ''
    await loadCurrentVideoNotes()
  } catch (err) {
    alert('保存笔记失败：' + (err.response?.data?.detail || err.message || '请稍后重试'))
  } finally {
    savingVideoNote.value = false
  }
}

async function loadQuiz(forceGenerate = false) {
  if (quizLoading.value) return
  if (!forceGenerate && await restoreQuizState()) return
  const text = subtitleData.value.full_text || ''
  if (!text && loading.value) {
    quizError.value = '正在提取视频内容，完成后会自动生成理解测试。'
    return
  }

  quizLoading.value = true
  quizError.value = ''
  quizData.value = null
  quizAnswers.value = {}
  quizResult.value = null
  quizProgress.value = {
    message: '正在准备第一批题目...',
    batchIndex: 0,
    totalBatches: 5,
    completedQuestions: 0,
    totalQuestions: 16,
    percent: 0,
  }
  try {
    let completedQuiz = null
    let streamError = ''
    await generateVideoQuizStream(props.videoUrl, text, 'zh', forceGenerate, {
      quiz_progress: (data) => {
        try {
          const parsed = JSON.parse(data)
          quizProgress.value = {
            message: parsed.message || quizProgress.value.message,
            batchIndex: parsed.batch_index ?? quizProgress.value.batchIndex,
            totalBatches: parsed.total_batches ?? quizProgress.value.totalBatches,
            completedQuestions: parsed.completed_questions ?? quizProgress.value.completedQuestions,
            totalQuestions: parsed.total_questions ?? quizProgress.value.totalQuestions,
            percent: parsed.percent ?? quizProgress.value.percent,
          }
        } catch { /* ignore malformed progress event */ }
      },
      quiz_batch: (data) => {
        try {
          const parsed = JSON.parse(data)
          const questionsById = new Map(
            (quizData.value?.questions || []).map(question => [String(question.id), question]),
          )
          for (const question of parsed.questions || []) {
            questionsById.set(String(question.id), question)
          }
          quizData.value = {
            title: parsed.title || quizData.value?.title || '视频内容理解测试',
            questions: [...questionsById.values()].sort((a, b) => Number(a.id) - Number(b.id)),
            max_score: 100,
          }
          quizProgress.value = {
            message: `第 ${parsed.batch_index}/${parsed.total_batches} 批${parsed.type_label || '题目'}已生成`,
            batchIndex: parsed.batch_index,
            totalBatches: parsed.total_batches,
            completedQuestions: parsed.completed_questions,
            totalQuestions: parsed.total_questions,
            percent: parsed.percent,
          }
        } catch {
          streamError = '收到的题目数据格式不正确'
        }
      },
      quiz_complete: (data) => {
        try {
          const parsed = JSON.parse(data)
          completedQuiz = parsed.quiz
          quizData.value = parsed.quiz
          quizProgress.value = {
            ...quizProgress.value,
            message: parsed.cache_hit ? '已读取历史题卷' : '全部题目生成完成',
            completedQuestions: parsed.quiz?.questions?.length || 16,
            percent: 100,
          }
        } catch {
          streamError = '完整题卷数据格式不正确'
        }
      },
      error: (data) => {
        try { streamError = JSON.parse(data).message || '生成理解测试失败' }
        catch { streamError = data || '生成理解测试失败' }
      },
    })
    if (streamError) throw new Error(streamError)
    if (!completedQuiz?.questions?.length) throw new Error('题卷生成未完成，请重新尝试')
    quizData.value = completedQuiz
    quizResult.value = null
    activeQuizAttemptId.value = createAttemptId()
    selectedHistoryId.value = ''
    persistQuizState()
  } catch (err) {
    quizError.value = err.message || '生成理解测试失败'
  } finally {
    quizLoading.value = false
  }
}

function questionTypeLabel(type) {
  const labels = {
    single: '单选题',
    multiple: '多选题',
    true_false: '判断题',
    short_answer: '简答题',
    analysis: '分析题',
  }
  return labels[type] || '测试题'
}

function isQuizOptionSelected(questionId, optionKey) {
  const answer = quizAnswers.value[questionId]
  return Array.isArray(answer) ? answer.includes(optionKey) : answer === optionKey
}

function updateQuizOption(question, optionKey) {
  if (quizResult.value) return
  if (question.type === 'multiple') {
    const current = Array.isArray(quizAnswers.value[question.id])
      ? [...quizAnswers.value[question.id]]
      : []
    const index = current.indexOf(optionKey)
    if (index >= 0) current.splice(index, 1)
    else current.push(optionKey)
    quizAnswers.value[question.id] = current
  } else {
    quizAnswers.value[question.id] = optionKey
  }
}

function optionClass(question, optionKey) {
  const selected = isQuizOptionSelected(question.id, optionKey)
  if (!quizResult.value) {
    return selected
      ? 'border-primary bg-primary-light/60'
      : 'border-border-light bg-white hover:border-primary/50 hover:bg-bg-section'
  }

  const correct = (question.answer || []).includes(optionKey)
  if (correct) return 'border-emerald-300 bg-emerald-50'
  if (selected) return 'border-rose-300 bg-rose-50'
  return 'border-border-light bg-white opacity-70'
}

function quizReferenceAnswer(question) {
  if (['short_answer', 'analysis'].includes(question.type)) {
    return question.reference_answer || question.explanation || '请参考视频内容。'
  }
  const keys = question.answer || []
  return keys.map((key) => {
    const option = (question.options || []).find((item) => item.key === key)
    return option ? `${key}. ${option.text}` : key
  }).join('；')
}

async function submitQuiz() {
  if (!quizData.value || quizGrading.value || answeredQuizCount.value === 0) return
  quizGrading.value = true
  try {
    quizResult.value = await gradeVideoQuiz(quizData.value, quizAnswers.value)
    saveCompletedQuizAttempt()
  } catch (err) {
    alert(err.message || '理解测试阅卷失败')
  } finally {
    quizGrading.value = false
  }
}

function resetQuizAnswers() {
  quizAnswers.value = {}
  quizResult.value = null
  activeQuizAttemptId.value = createAttemptId()
  selectedHistoryId.value = ''
  persistQuizState()
}

async function regenerateQuiz() {
  quizData.value = null
  quizAnswers.value = {}
  quizResult.value = null
  activeQuizAttemptId.value = ''
  selectedHistoryId.value = ''
  await loadQuiz(true)
}

function quizStorageKey() {
  return `saveany.quiz.v2:${props.videoUrl}`
}

function createAttemptId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function applyQuizState(saved) {
  quizHistory.value = Array.isArray(saved.history) ? saved.history.slice(0, 10) : []
  if (!saved.current?.quiz?.questions?.length) return false
  quizData.value = saved.current.quiz
  quizAnswers.value = saved.current.answers || {}
  quizResult.value = saved.current.result || null
  activeQuizAttemptId.value = saved.current.attemptId || createAttemptId()
  selectedHistoryId.value = saved.current.result ? activeQuizAttemptId.value : ''
  quizError.value = ''
  return true
}

async function restoreQuizState() {
  if (quizHistoryInitialized.value) return Boolean(quizData.value)
  quizHistoryInitialized.value = true
  let restored = false
  try {
    const saved = JSON.parse(localStorage.getItem(quizStorageKey()) || '{}')
    restored = applyQuizState(saved)
  } catch (err) {
    console.warn('读取理解测试历史失败:', err)
  }

  try {
    const diskState = await getQuizState(props.videoUrl)
    if (diskState?.current?.quiz?.questions?.length) {
      restored = applyQuizState(diskState)
      quizSavedAt.value = new Date()
    } else if (Array.isArray(diskState?.history) && diskState.history.length) {
      quizHistory.value = diskState.history.slice(0, 10)
    } else if (restored) {
      persistQuizState()
    }
  } catch (err) {
    console.warn('读取磁盘答题进度失败，已使用浏览器备份:', err)
  }
  return restored
}

function buildQuizState() {
  return {
    current: {
      attemptId: activeQuizAttemptId.value,
      quiz: quizData.value,
      answers: quizAnswers.value,
      result: quizResult.value,
    },
    history: quizHistory.value.slice(0, 10),
  }
}

function persistQuizState() {
  if (!quizData.value || !activeQuizAttemptId.value) return
  const state = buildQuizState()
  try {
    localStorage.setItem(quizStorageKey(), JSON.stringify(state))
  } catch (err) {
    console.warn('保存理解测试历史失败:', err)
  }

  window.clearTimeout(quizSaveTimer)
  quizSaveTimer = window.setTimeout(async () => {
    try {
      await saveQuizState(props.videoUrl, state)
      quizSavedAt.value = new Date()
    } catch (err) {
      console.warn('答题进度写入磁盘失败:', err)
    }
  }, 500)
}

function saveCompletedQuizAttempt() {
  if (!quizData.value || !quizResult.value) return
  if (!activeQuizAttemptId.value) activeQuizAttemptId.value = createAttemptId()
  const entry = {
    id: activeQuizAttemptId.value,
    completedAt: new Date().toISOString(),
    quiz: quizData.value,
    answers: JSON.parse(JSON.stringify(quizAnswers.value)),
    result: quizResult.value,
  }
  quizHistory.value = [
    entry,
    ...quizHistory.value.filter((item) => item.id !== entry.id),
  ].slice(0, 10)
  selectedHistoryId.value = entry.id
  persistQuizState()
}

function loadQuizHistory(attemptId) {
  const attempt = quizHistory.value.find((item) => item.id === attemptId)
  if (!attempt) return
  quizData.value = attempt.quiz
  quizAnswers.value = JSON.parse(JSON.stringify(attempt.answers || {}))
  quizResult.value = attempt.result
  activeQuizAttemptId.value = attempt.id
  selectedHistoryId.value = attempt.id
  quizError.value = ''
  persistQuizState()
}

function formatHistoryLabel(attempt) {
  const date = new Date(attempt.completedAt)
  const time = Number.isNaN(date.getTime()) ? '历史记录' : date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
  return `${time} · ${attempt.result?.total_score ?? 0} 分`
}

async function copyText(text) {
  if (!text) return
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  textarea.remove()
}

function showCopiedState(stateRef) {
  stateRef.value = true
  window.setTimeout(() => {
    stateRef.value = false
  }, 1800)
}

function formatQuizAnswer(question, answer) {
  if (['short_answer', 'analysis'].includes(question.type)) {
    return String(answer || '').trim() || '未作答'
  }
  const keys = Array.isArray(answer) ? answer : (answer ? [answer] : [])
  if (!keys.length) return '未作答'
  return keys.map((key) => {
    const option = (question.options || []).find((item) => item.key === key)
    return option ? `${key}. ${option.text}` : key
  }).join('；')
}

async function copyQuizReport() {
  if (!quizData.value || !quizResult.value) return
  const completedAttempt = quizHistory.value.find((item) => item.id === activeQuizAttemptId.value)
  const completedAt = completedAttempt?.completedAt || new Date().toISOString()
  const date = new Date(completedAt).toLocaleString('zh-CN')
  const lines = [
    `# ${quizData.value.title || '视频内容理解测试'}`,
    '',
    `- 视频：${props.videoTitle || '未命名视频'}`,
    `- 链接：${props.videoUrl}`,
    `- 完成时间：${date}`,
    `- 成绩：${quizResult.value.total_score} / ${quizResult.value.max_score}（${quizResult.value.percentage}%）`,
    `- 评价：${scoreSummary(quizResult.value.percentage)}`,
    '',
    '## 答题详情',
  ]

  quizData.value.questions.forEach((question, index) => {
    const result = quizResultById.value[String(question.id)] || {}
    lines.push(
      '',
      `### ${index + 1}. ${question.question}`,
      '',
      `- 题型：${questionTypeLabel(question.type)}`,
      `- 分值：${result.awarded_points ?? 0} / ${result.max_points ?? question.points} 分`,
    )
    if (question.options?.length) {
      lines.push('- 选项：')
      question.options.forEach((option) => lines.push(`  - ${option.key}. ${option.text}`))
    }
    lines.push(
      `- 我的答案：${formatQuizAnswer(question, quizAnswers.value[question.id])}`,
      `- 阅卷点评：${result.feedback || '暂无点评'}`,
      `- 参考答案：${quizReferenceAnswer(question)}`,
    )
    if (question.explanation) lines.push(`- 解析：${question.explanation}`)
  })

  if (quizResult.value.grading_warning) {
    lines.push('', `> 阅卷提示：${quizResult.value.grading_warning}`)
  }
  try {
    await copyText(lines.join('\n'))
    showCopiedState(quizCopied)
  } catch (err) {
    alert('复制测试报告失败：' + (err.message || '请检查浏览器剪贴板权限'))
  }
}

async function copySummary() {
  try {
    await copyText(summaryText.value)
    showCopiedState(summaryCopied)
  } catch (err) {
    alert('复制摘要失败：' + (err.message || '请检查浏览器剪贴板权限'))
  }
}

async function copyMindmap() {
  try {
    await copyText(mindmapMarkdown.value)
    showCopiedState(mindmapCopied)
  } catch (err) {
    alert('复制思维导图失败：' + (err.message || '请检查浏览器剪贴板权限'))
  }
}

async function copyChatTranscript() {
  const messages = chatMessages.value.filter((message) => message.content)
  if (!messages.length) return
  const lines = [
    `# ${props.videoTitle || '视频'}问答记录`,
    '',
    `- 视频链接：${props.videoUrl}`,
  ]
  messages.forEach((message) => {
    lines.push('', message.role === 'user' ? '## 问题' : '## AI 回答', '', message.content)
  })
  try {
    await copyText(lines.join('\n'))
    showCopiedState(chatCopied)
  } catch (err) {
    alert('复制问答记录失败：' + (err.message || '请检查浏览器剪贴板权限'))
  }
}

function scoreSummary(percentage) {
  if (percentage >= 90) return '优秀，核心内容掌握扎实'
  if (percentage >= 75) return '良好，少量知识点需要巩固'
  if (percentage >= 60) return '及格，建议结合解析复习'
  return '需要复习，再看一遍重点内容'
}

function scoreToneClass(percentage) {
  if (percentage >= 75) return 'text-emerald-700'
  if (percentage >= 60) return 'text-amber-700'
  return 'text-rose-700'
}

// ===== 思维导图全屏 =====
function toggleFullscreen() {
  if (!mindmapContainer.value) return

  if (!isFullscreen.value) {
    if (mindmapContainer.value.requestFullscreen) {
      mindmapContainer.value.requestFullscreen()
    } else if (mindmapContainer.value.webkitRequestFullscreen) {
      mindmapContainer.value.webkitRequestFullscreen()
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen()
    } else if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen()
    }
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
  nextTick(() => {
    if (markmapInstance) {
      markmapInstance.fit()
    }
  })
}

// ===== 构建可导出的纯 SVG（将 foreignObject 替换为 text） =====
function buildExportableSvg() {
  if (!mindmapSvg.value) return null

  const cloned = mindmapSvg.value.cloneNode(true)

  cloned.querySelectorAll('[transform]').forEach(el => {
    const t = el.getAttribute('transform')
    if (t && t.includes('NaN')) {
      el.setAttribute('transform', 'translate(0,0) scale(1)')
    }
  })

  cloned.querySelectorAll('foreignObject').forEach(fo => {
    const textContent = fo.textContent?.trim() || ''
    if (!textContent) { fo.remove(); return }

    const x = parseFloat(fo.getAttribute('x')) || 0
    const y = parseFloat(fo.getAttribute('y')) || 0
    const h = parseFloat(fo.getAttribute('height')) || 20

    const textEl = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    textEl.setAttribute('x', String(x + 4))
    textEl.setAttribute('y', String(y + h / 2 + 5))
    textEl.setAttribute('font-size', '14')
    textEl.setAttribute('font-family', 'sans-serif')
    textEl.setAttribute('fill', '#333')
    textEl.setAttribute('dominant-baseline', 'middle')
    textEl.textContent = textContent

    fo.parentNode.replaceChild(textEl, fo)
  })

  return cloned
}

function serializeSvg(svgEl) {
  const serializer = new XMLSerializer()
  let svgString = serializer.serializeToString(svgEl)

  if (!svgString.includes('xmlns=')) {
    svgString = svgString.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"')
  }

  const styles = document.querySelectorAll('style')
  let markmapCss = ''
  styles.forEach(s => {
    if (s.textContent.includes('.markmap')) {
      markmapCss += s.textContent
    }
  })
  if (markmapCss) {
    svgString = svgString.replace('>', `><defs><style>${markmapCss}</style></defs>`)
  }

  return svgString
}

// ===== 获取思维导图完整内容边界（不受用户缩放/平移影响） =====
function getContentBBox() {
  const svgEl = mindmapSvg.value
  const gRoot = svgEl.querySelector('g')
  if (gRoot) {
    try {
      const bbox = gRoot.getBBox()
      if (bbox.width > 0 && bbox.height > 0) {
        const transform = gRoot.getAttribute('transform') || ''
        const translateMatch = transform.match(/translate\(\s*([-\d.e]+)\s*[,\s]\s*([-\d.e]+)\s*\)/)
        const scaleMatch = transform.match(/scale\(\s*([-\d.e]+)/)
        const tx = translateMatch ? parseFloat(translateMatch[1]) : 0
        const ty = translateMatch ? parseFloat(translateMatch[2]) : 0
        const sc = scaleMatch ? parseFloat(scaleMatch[1]) : 1
        return {
          x: bbox.x * sc + tx,
          y: bbox.y * sc + ty,
          width: bbox.width * sc,
          height: bbox.height * sc,
        }
      }
    } catch {}
  }
  try {
    const bbox = svgEl.getBBox()
    if (bbox.width > 0 && bbox.height > 0) return bbox
  } catch {}
  return { x: 0, y: 0, width: 800, height: 600 }
}

// ===== 为导出 SVG 设置完整内容的 viewBox =====
function setFullViewBox(svgClone) {
  const dims = getContentBBox()
  const padding = 60
  const vx = dims.x - padding
  const vy = dims.y - padding
  const vw = dims.width + padding * 2
  const vh = dims.height + padding * 2
  svgClone.setAttribute('viewBox', `${vx} ${vy} ${vw} ${vh}`)
  svgClone.setAttribute('width', String(vw))
  svgClone.setAttribute('height', String(vh))
  return { vw, vh }
}

// ===== 思维导图下载 PNG（4K 超清，完整内容） =====
async function downloadMindmapPng() {
  if (!mindmapSvg.value) return

  const exportSvg = buildExportableSvg()
  if (!exportSvg) return

  const { vw, vh } = setFullViewBox(exportSvg)
  const scale = Math.max(4, Math.ceil(3840 / vw))

  let svgString = serializeSvg(exportSvg)

  const canvas = document.createElement('canvas')
  canvas.width = vw * scale
  canvas.height = vh * scale
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  const img = new Image()
  const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)

  return new Promise((resolve) => {
    img.onload = () => {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      canvas.toBlob((pngBlob) => {
        if (pngBlob) {
          triggerDownload(pngBlob, getSafeFilename() + ' - 思维导图.png')
        }
        resolve()
      }, 'image/png')
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      alert('PNG 导出失败，请使用 SVG 下载')
      resolve()
    }
    img.src = url
  })
}

// ===== 思维导图下载 SVG（完整内容，不受视口影响） =====
function downloadMindmapSvg() {
  if (!mindmapSvg.value) return

  const cloned = mindmapSvg.value.cloneNode(true)
  cloned.querySelectorAll('[transform]').forEach(el => {
    const t = el.getAttribute('transform')
    if (t && t.includes('NaN')) {
      el.setAttribute('transform', 'translate(0,0) scale(1)')
    }
  })

  setFullViewBox(cloned)

  const svgString = serializeSvg(cloned)
  const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
  triggerDownload(blob, getSafeFilename() + ' - 思维导图.svg')
}

// ===== 字幕文件下载 =====
function downloadSubtitle(format) {
  showSubtitleDropdown.value = false
  const segments = subtitleData.value.segments
  if (!segments || segments.length === 0) return

  let content = ''
  let ext = format
  const filename = getSafeFilename()

  if (format === 'srt') {
    content = segmentsToSrt(segments)
  } else if (format === 'vtt') {
    content = segmentsToVtt(segments)
  } else {
    content = segmentsToTxt(segments)
  }

  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  triggerDownload(blob, `${filename} - 字幕.${ext}`)
}

function segmentsToSrt(segments) {
  return segments.map((seg, i) => {
    const start = formatSrtTime(seg.start)
    const end = formatSrtTime(seg.end)
    return `${i + 1}\n${start} --> ${end}\n${seg.text}\n`
  }).join('\n')
}

function segmentsToVtt(segments) {
  const header = 'WEBVTT\n\n'
  const body = segments.map((seg) => {
    const start = formatVttTime(seg.start)
    const end = formatVttTime(seg.end)
    return `${start} --> ${end}\n${seg.text}\n`
  }).join('\n')
  return header + body
}

function segmentsToTxt(segments) {
  return segments.map((seg) => seg.text).join('\n')
}

function formatSrtTime(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const ms = Math.round((seconds % 1) * 1000)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms).padStart(3, '0')}`
}

function formatVttTime(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const ms = Math.round((seconds % 1) * 1000)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

// ===== 通用工具函数 =====
function getSafeFilename() {
  return (props.videoTitle || '视频').replace(/[\\/*?:"<>|]/g, '_').substring(0, 80)
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function handleClickOutside(e) {
  if (subtitleDropdownRef.value && !subtitleDropdownRef.value.contains(e.target)) {
    showSubtitleDropdown.value = false
  }
}

const quotaInfo = ref(null)

async function regenerateSummary() {
  if (loading.value || regeneratingPart.value) return
  if (!window.confirm('将忽略缓存并重新生成总结，是否继续？')) return
  activeTab.value = 'summary'
  await startSummarize(false, { parts: ['summary'], preserveOther: true })
}

async function regenerateMindmap() {
  if (loading.value || regeneratingPart.value) return
  if (!window.confirm('将忽略缓存并重新生成思维导图，是否继续？')) return
  activeTab.value = 'mindmap'
  await startSummarize(false, { parts: ['mindmap'], preserveOther: true })
}

async function clearChatHistory() {
  if (chatLoading.value || clearingChat.value) return
  if (!window.confirm('确定清空当前视频的问答历史吗？')) return
  clearingChat.value = true
  try {
    await clearVideoChat(props.videoUrl)
    chatMessages.value = []
  } catch (err) {
    alert(err.message || '清空问答失败')
  } finally {
    clearingChat.value = false
  }
}

async function startSummarize(force = false, options = {}) {
  const parts = Array.isArray(options.parts) ? options.parts.filter(Boolean) : []
  const preserveOther = Boolean(options.preserveOther)
  const onlySummary = parts.length === 1 && parts[0] === 'summary'
  const onlyMindmap = parts.length === 1 && parts[0] === 'mindmap'

  loading.value = true
  regeneratingPart.value = onlySummary ? 'summary' : onlyMindmap ? 'mindmap' : (force || parts.length ? 'all' : '')
  if (!preserveOther || force || parts.includes('summary') || !parts.length) {
    if (!onlyMindmap) summaryText.value = ''
  }
  if (!preserveOther || force || parts.includes('mindmap') || !parts.length) {
    if (!onlySummary) mindmapMarkdown.value = ''
  }
  if (onlySummary) summaryText.value = ''
  if (onlyMindmap) mindmapMarkdown.value = ''

  quotaInfo.value = null
  loadingMessage.value = onlyMindmap
    ? '正在重新生成思维导图...'
    : onlySummary
      ? '正在重新生成总结...'
      : force
        ? '正在重新生成总结与思维导图...'
        : '正在提取视频字幕...'
  progressPercent.value = 0

  try {
    await summarizeVideo(props.videoUrl, 'zh', {
      history: (data) => {
        try {
          const parsed = JSON.parse(data)
          if (Array.isArray(parsed.messages)) chatMessages.value = parsed.messages
        } catch (e) { /* ignore parse error */ }
      },
      progress: (data) => {
        try {
          const parsed = JSON.parse(data)
          loadingMessage.value = parsed.message || loadingMessage.value
          if (Number.isFinite(parsed.percent)) {
            progressPercent.value = Math.max(0, Math.min(100, Math.round(parsed.percent)))
          } else if (parsed.percent === null) {
            progressPercent.value = null
          }
        } catch (e) { /* ignore parse error */ }
      },
      subtitle: (data) => {
        try {
          subtitleData.value = JSON.parse(data)
          if (subtitleData.value.has_subtitle && subtitleData.value.full_text) {
            if (!onlyMindmap && !onlySummary) {
              loadingMessage.value = 'AI 正在分析视频内容...'
            }
            progressPercent.value = null
            if (activeTab.value === 'quiz' && !quizData.value && !quizLoading.value) {
              quizError.value = ''
              loadQuiz()
            }
          }
        } catch (e) { /* ignore parse error */ }
      },
      summary: (data) => {
        if (onlyMindmap) return
        try { summaryText.value += JSON.parse(data) } catch { summaryText.value += data }
      },
      mindmap: (data) => {
        if (onlySummary) return
        try {
          const parsed = JSON.parse(data)
          mindmapMarkdown.value = sanitizeMindmapMarkdown(parsed.markdown || '')
        } catch (e) { /* ignore parse error */ }
      },
      quota: (data) => {
        try { quotaInfo.value = JSON.parse(data) } catch {}
      },
      done: () => {
        loading.value = false
        regeneratingPart.value = ''
        progressPercent.value = null
      },
      error: (data) => {
        loading.value = false
        regeneratingPart.value = ''
        progressPercent.value = null
        try {
          const parsed = JSON.parse(data)
          if (parsed.need_login) {
            emit('need-login')
            return
          }
          if (parsed.need_vip) {
            emit('need-vip')
            return
          }
          alert(parsed.message || '总结失败')
        } catch (e) {
          alert('总结失败: ' + data)
        }
      },
    }, {
      title: props.videoTitle,
      force,
      parts,
    })
  } catch (err) {
    loading.value = false
    regeneratingPart.value = ''
    progressPercent.value = null
    alert('总结请求失败: ' + err.message)
  }
}

async function sendQuestion() {
  const question = chatInput.value.trim()
  if (!question || chatLoading.value) return

  chatInput.value = ''
  chatMessages.value.push({ role: 'user', content: question })

  const aiMessage = { role: 'assistant', content: '', loading: true, status: '正在准备视频内容...' }
  chatMessages.value.push(aiMessage)
  chatLoading.value = true

  await nextTick()
  scrollChatToBottom()

  try {
    await chatWithVideo(
      props.videoUrl,
      question,
      subtitleData.value.full_text || '',
      {
        answer: (data) => {
          try { aiMessage.content += JSON.parse(data) } catch { aiMessage.content += data }
          aiMessage.status = ''
          scrollChatToBottom()
        },
        progress: (data) => {
          try {
            const parsed = JSON.parse(data)
            aiMessage.status = parsed.message || aiMessage.status
          } catch (e) { /* ignore parse error */ }
          scrollChatToBottom()
        },
        done: () => {
          aiMessage.loading = false
          aiMessage.status = ''
          chatLoading.value = false
        },
        error: (data) => {
          aiMessage.loading = false
          chatLoading.value = false
          try {
            const parsed = JSON.parse(data)
            aiMessage.content = '❌ ' + (parsed.message || '回答失败')
          } catch (e) {
            aiMessage.content = '❌ 回答失败'
          }
        },
      }
    )
  } catch (err) {
    aiMessage.loading = false
    chatLoading.value = false
    aiMessage.content = '❌ 请求失败: ' + err.message
  }
}

function scrollChatToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

onMounted(() => {
  startSummarize(props.force)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('webkitfullscreenchange', onFullscreenChange)
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  if (subtitleHighlightTimer) window.clearTimeout(subtitleHighlightTimer)
  if (quizSaveTimer && quizData.value && activeQuizAttemptId.value) {
    window.clearTimeout(quizSaveTimer)
    void saveQuizState(props.videoUrl, buildQuizState()).catch((err) => {
      console.warn('退出页面前保存答题进度失败:', err)
    })
  }
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', onFullscreenChange)
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
/* 总结摘要 Markdown 排版定制 */
.summary-prose :deep(h1) {
  font-size: 1.25rem;
  font-weight: 700;
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  color: var(--color-text-primary);
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--color-primary-light);
}

.quiz-scroll-region {
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: rgb(148 163 184 / 0.65) transparent;
}

.quiz-scroll-region::-webkit-scrollbar {
  width: 6px;
}

.quiz-scroll-region::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgb(148 163 184 / 0.65);
}
.summary-prose :deep(h2) {
  font-size: 1.125rem;
  font-weight: 700;
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  color: var(--color-text-primary);
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--color-border-light);
}
.summary-prose :deep(h3) {
  font-size: 1rem;
  font-weight: 600;
  margin-top: 1.25rem;
  margin-bottom: 0.5rem;
  color: var(--color-text-primary);
}
.summary-prose :deep(p) {
  margin-bottom: 0.75rem;
  line-height: 1.8;
  color: var(--color-text-primary);
}
.summary-prose :deep(ul), .summary-prose :deep(ol) {
  margin-bottom: 0.75rem;
  padding-left: 1.5rem;
}
.summary-prose :deep(li) {
  margin-bottom: 0.35rem;
  line-height: 1.8;
}
.summary-prose :deep(li::marker) {
  color: var(--color-primary);
}
.summary-prose :deep(strong) {
  color: var(--color-text-primary);
  font-weight: 600;
}
.summary-prose :deep(hr) {
  margin: 1.5rem 0;
  border-color: var(--color-border-light);
}
.summary-prose :deep(blockquote) {
  border-left: 3px solid var(--color-primary);
  padding-left: 1rem;
  color: var(--color-text-secondary);
  font-style: normal;
  margin: 1rem 0;
  background: var(--color-bg-section);
  border-radius: 0 8px 8px 0;
  padding: 0.75rem 1rem;
}
.summary-prose :deep(code) {
  background: var(--color-bg-section);
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  font-size: 0.85em;
  color: var(--color-primary-dark);
  font-weight: 500;
}
.summary-prose :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 1rem;
  overflow-x: auto;
  margin: 1rem 0;
}
.summary-prose :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
  font-weight: normal;
}
.summary-prose :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0;
  font-size: 0.875rem;
}
.summary-prose :deep(th) {
  background: var(--color-bg-section);
  padding: 0.5rem 0.75rem;
  text-align: left;
  font-weight: 600;
  border-bottom: 2px solid var(--color-border);
}
.summary-prose :deep(td) {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--color-border-light);
}
.summary-prose :deep(a) {
  color: var(--color-primary);
  text-decoration: none;
}
.summary-prose :deep(a:hover) {
  text-decoration: underline;
}
.summary-prose :deep(.summary-timestamp) {
  display: inline-flex;
  align-items: center;
  margin: 0 0.15rem;
  padding: 0.1rem 0.42rem;
  border: 1px solid rgb(37 99 235 / 0.22);
  border-radius: 999px;
  background: rgb(239 246 255);
  color: var(--color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.4;
  cursor: pointer;
  vertical-align: baseline;
  transition: background-color 150ms ease, border-color 150ms ease;
}
.summary-prose :deep(.summary-timestamp:hover) {
  border-color: var(--color-primary);
  background: rgb(219 234 254);
}

/* AI 问答 Markdown 排版（更紧凑） */
.chat-prose :deep(p) {
  margin-bottom: 0.5rem;
  line-height: 1.7;
}
.chat-prose :deep(p:last-child) {
  margin-bottom: 0;
}
.chat-prose :deep(ul), .chat-prose :deep(ol) {
  margin-bottom: 0.5rem;
  padding-left: 1.25rem;
}
.chat-prose :deep(li) {
  margin-bottom: 0.2rem;
  line-height: 1.7;
}
.chat-prose :deep(li::marker) {
  color: var(--color-primary);
}
.chat-prose :deep(code) {
  background: rgba(0,0,0,0.06);
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  font-size: 0.85em;
}
.chat-prose :deep(blockquote) {
  border-left: 2px solid var(--color-primary);
  padding-left: 0.75rem;
  color: var(--color-text-secondary);
  margin: 0.5rem 0;
}
.chat-prose :deep(strong) {
  font-weight: 600;
}

/* 思维导图：确保 markmap 的 foreignObject 文字正常显示 */
.mindmap-wrapper :deep(.markmap-foreign) {
  display: inline-block !important;
}
.mindmap-wrapper :deep(foreignObject) {
  overflow: visible !important;
}
.mindmap-wrapper :deep(foreignObject div) {
  font: 300 16px/20px sans-serif;
  color: #333;
}

/* 思维导图全屏样式 */
.mindmap-fullscreen {
  position: fixed !important;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 40;
  border-radius: 0 !important;
  border: none !important;
  background: #ffffff;
}
</style>
