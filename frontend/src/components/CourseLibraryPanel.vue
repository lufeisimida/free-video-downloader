<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-[110] bg-black/35 backdrop-blur-sm" @click.self="$emit('close')">
      <section class="absolute inset-x-0 bottom-0 top-4 mx-auto flex max-w-7xl flex-col overflow-hidden rounded-t-lg border border-border bg-white shadow-2xl sm:inset-x-6 sm:bottom-6 sm:top-6 sm:rounded-lg">
        <header class="flex h-16 shrink-0 items-center justify-between border-b border-border px-5 sm:px-6">
          <div class="min-w-0">
            <h2 class="text-base font-semibold text-text-primary">课程学习中心</h2>
            <p class="mt-0.5 text-xs text-text-muted">{{ library.videos.length }} 个解析记录 · {{ library.folders.length }} 个课程目录</p>
          </div>
          <button @click="$emit('close')" class="flex h-9 w-9 items-center justify-center rounded-md text-text-muted hover:bg-gray-100 hover:text-text-primary cursor-pointer" title="关闭">
            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </header>

        <div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-text-muted">
          <span class="mr-3 h-5 w-5 animate-spin rounded-full border-2 border-primary/20 border-t-primary"></span>正在读取资料库...
        </div>

        <div v-else class="flex min-h-0 flex-1 flex-col md:flex-row">
          <aside class="flex max-h-60 w-full shrink-0 flex-col border-b border-border bg-gray-50/70 md:max-h-none md:w-72 md:border-b-0 md:border-r">
            <div class="border-b border-border-light p-3">
              <button @click="beginCreateFolder(null)" class="flex h-9 w-full items-center justify-center gap-2 rounded-md border border-border bg-white text-sm font-medium text-text-secondary hover:border-primary hover:text-primary cursor-pointer">
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" /></svg>新建课程目录
              </button>
              <form v-if="folderForm.visible" @submit.prevent="submitFolder" class="mt-2 flex gap-2">
                <input v-model.trim="folderForm.name" ref="folderInput" maxlength="80" placeholder="目录名称" class="h-9 min-w-0 flex-1 rounded-md border border-border bg-white px-3 text-sm focus:border-primary focus:outline-none" />
                <button type="submit" :disabled="!folderForm.name || saving" class="h-9 rounded-md bg-primary px-3 text-xs font-medium text-white disabled:opacity-50 cursor-pointer">保存</button>
              </form>
            </div>

            <nav class="min-h-0 flex-1 overflow-y-auto p-2" aria-label="课程目录树">
              <button @click="selectFolder('all')" :class="treeRowClass('all')" class="mb-0.5 flex h-9 w-full items-center gap-2 rounded-md px-2 text-left text-sm cursor-pointer">
                <svg class="h-4 w-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M4 5h6l2 2h8v12H4V5z" /></svg>
                <span class="min-w-0 flex-1 truncate">全部视频</span><span class="text-xs tabular-nums opacity-60">{{ library.videos.length }}</span>
              </button>
              <button @click="selectFolder('unfiled')" :class="treeRowClass('unfiled')" class="mb-1 flex h-9 w-full items-center gap-2 rounded-md px-2 text-left text-sm cursor-pointer">
                <svg class="h-4 w-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M4 7h16v12H4V7zm3-3h10v3H7V4z" /></svg>
                <span class="min-w-0 flex-1 truncate">未归档</span><span class="text-xs tabular-nums opacity-60">{{ unfiledCount }}</span>
              </button>
              <div v-for="row in folderRows" :key="row.id" class="group relative mb-0.5">
                <button @click="selectFolder(row.id)" :class="treeRowClass(row.id)" class="flex h-9 w-full items-center rounded-md pr-20 text-left text-sm cursor-pointer" :style="{ paddingLeft: `${8 + row.depth * 16}px` }">
                  <span @click.stop="toggleFolder(row.id)" class="mr-1 flex h-6 w-5 shrink-0 items-center justify-center" :class="row.hasChildren ? '' : 'invisible'">
                    <svg class="h-3.5 w-3.5 transition-transform" :class="expandedFolders.has(row.id) ? 'rotate-90' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg>
                  </span>
                  <svg class="mr-2 h-4 w-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M3 6h7l2 2h9v11H3V6z" /></svg>
                  <span class="min-w-0 flex-1 truncate">{{ row.name }}</span><span class="text-xs tabular-nums opacity-60">{{ directVideoCount(row.id) }}</span>
                </button>
                <div class="absolute right-1 top-1 flex md:hidden items-center gap-0.5 rounded bg-white/95 shadow-sm md:group-hover:flex">
                  <button @click.stop="beginCreateFolder(row.id)" class="flex h-7 w-7 items-center justify-center text-text-muted hover:text-primary cursor-pointer" title="新建子目录">+</button>
                  <button @click.stop="renameFolder(row)" class="flex h-7 w-7 items-center justify-center text-text-muted hover:text-primary cursor-pointer" title="重命名"><svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.2 5.2l3.6 3.6M4 20l4.4-1 10-10a2.5 2.5 0 00-3.5-3.5l-10 10L4 20z" /></svg></button>
                  <button @click.stop="removeFolder(row)" class="flex h-7 w-7 items-center justify-center text-text-muted hover:text-rose-600 cursor-pointer" title="删除目录"><svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7h16M9 7V4h6v3m-8 0l1 13h8l1-13" /></svg></button>
                </div>
              </div>
            </nav>
          </aside>

          <main class="flex min-h-0 min-w-0 flex-1 flex-col">
            <template v-if="!quizOpen">
              <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border-light px-5 py-3.5">
                <div class="min-w-0">
                  <h3 class="truncate text-base font-semibold text-text-primary">{{ selectedFolderTitle }}</h3>
                  <p class="mt-0.5 text-xs text-text-muted">{{ typeof selectedFolderId === 'number' ? recursiveVideoCount : filteredVideos.length }} 个视频</p>
                </div>
                <div v-if="typeof selectedFolderId === 'number'" class="flex flex-wrap items-center justify-end gap-2">
                  <select v-model="quizSettings.phase" class="h-9 rounded-md border border-border bg-white px-2 text-xs text-text-secondary focus:border-primary focus:outline-none" title="测试阶段">
                    <option value="pre">学习前测</option><option value="practice">日常练习</option><option value="post">学习后测</option>
                  </select>
                  <select v-model="quizSettings.mode" class="h-9 rounded-md border border-border bg-white px-2 text-xs text-text-secondary focus:border-primary focus:outline-none" title="组卷模式">
                    <option value="quick">快速 8 题</option><option value="standard">标准 16 题</option><option value="exam">考试 20 题</option><option value="adaptive">自适应薄弱点</option><option value="wrong">到期错题</option>
                  </select>
                  <button @click="openLatestQuiz" class="hidden h-9 rounded-md border border-border px-3 text-xs font-medium text-text-secondary hover:border-primary hover:text-primary sm:block cursor-pointer">最近试卷</button>
                  <button @click="startGeneralQuiz" :disabled="recursiveVideoCount === 0" class="h-9 rounded-md bg-primary px-4 text-sm font-medium text-white hover:bg-primary-dark disabled:opacity-50 cursor-pointer">开始测试</button>
                </div>
              </div>

              <div v-if="typeof selectedFolderId === 'number'" class="flex shrink-0 gap-1 overflow-x-auto border-b border-border-light px-5" role="tablist">
                <button v-for="tab in learningTabs" :key="tab.id" @click="switchView(tab.id)" class="h-11 shrink-0 border-b-2 px-3 text-sm font-medium cursor-pointer" :class="activeView === tab.id ? 'border-primary text-primary' : 'border-transparent text-text-muted hover:text-text-primary'">{{ tab.label }}<span v-if="tab.count" class="ml-1.5 rounded bg-gray-100 px-1.5 py-0.5 text-[11px] tabular-nums">{{ tab.count }}</span></button>
              </div>

              <div v-if="error" class="border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-800">{{ error }}</div>
              <div v-if="learningLoading" class="flex flex-1 items-center justify-center text-sm text-text-muted"><span class="mr-3 h-5 w-5 animate-spin rounded-full border-2 border-primary/20 border-t-primary"></span>正在读取学习记录...</div>

              <div v-else-if="activeView === 'today' && typeof selectedFolderId === 'number'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
                <div class="flex flex-wrap items-end justify-between gap-4 border-b border-border-light pb-5">
                  <div><p class="text-xs font-semibold text-primary">TODAY / {{ todayPlan.date }}</p><h4 class="mt-1 text-xl font-semibold text-text-primary">今天只做这些</h4><p class="mt-1 text-sm text-text-muted">{{ todayPlan.planned_minutes || 0 }} 分钟 · {{ todayPlan.completed_count || 0 }}/{{ todayPlan.tasks?.length || 0 }} 已完成</p></div>
                  <div class="flex items-center gap-2"><label class="text-xs text-text-muted">学习时长</label><select v-model.number="todayMinutes" @change="loadLearning('today')" class="h-9 rounded-md border border-border bg-white px-3 text-sm"><option :value="15">15 分钟</option><option :value="30">30 分钟</option><option :value="60">60 分钟</option><option :value="90">90 分钟</option></select><span class="rounded-md px-2 py-1 text-xs font-medium" :class="riskClass">{{ riskLabel }}</span><button @click="startContinuousSession" class="h-9 rounded-md bg-primary px-4 text-sm font-medium text-white cursor-pointer">连续学习</button></div>
                </div>
                <div v-if="!todayPlan.tasks?.length" class="py-12 text-center text-sm text-text-muted">今天暂无任务</div>
                <div v-else class="mt-5 divide-y divide-border-light rounded-md border border-border">
                  <article v-for="(task, index) in todayPlan.tasks" :key="task.key" class="flex items-center gap-4 p-4" :class="task.completed ? 'bg-gray-50/70 opacity-70' : 'bg-white'">
                    <button @click="toggleTodayTask(task)" class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 cursor-pointer" :class="task.completed ? 'border-emerald-500 bg-emerald-500 text-white' : 'border-border text-transparent hover:border-primary'">✓</button>
                    <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary-light text-xs font-semibold text-primary">{{ index + 1 }}</div>
                    <div class="min-w-0 flex-1"><p class="truncate text-sm font-semibold text-text-primary" :class="{ 'line-through': task.completed }">{{ task.title }}</p><p class="mt-1 truncate text-xs text-text-muted">{{ task.description }}</p></div>
                    <span class="shrink-0 text-xs tabular-nums text-text-muted">{{ task.minutes }} 分钟</span>
                    <button @click="runTodayTask(task)" class="h-8 shrink-0 rounded-md border border-border px-3 text-xs font-medium text-text-secondary hover:border-primary hover:text-primary cursor-pointer">开始</button>
                  </article>
                </div>
              </div>

              <template v-else-if="activeView === 'videos' || typeof selectedFolderId !== 'number'">
                <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border-light px-5 py-3"><label class="relative block w-full max-w-xs"><svg class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-5-5m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg><input v-model.trim="search" placeholder="搜索视频历史" class="h-9 w-full rounded-md border border-border pl-9 pr-3 text-sm focus:border-primary focus:outline-none" /></label><button v-if="typeof selectedFolderId === 'number'" @click="importOpen = !importOpen" class="h-9 rounded-md border border-border px-3 text-xs font-medium text-text-secondary hover:border-primary hover:text-primary cursor-pointer">批量导入</button></div>
                <form v-if="importOpen && typeof selectedFolderId === 'number'" @submit.prevent="submitBatchImport" class="border-b border-border-light bg-gray-50/70 px-5 py-4"><div class="grid gap-3 sm:grid-cols-[1fr_auto]"><textarea v-model="importUrls" rows="3" placeholder="每行一个视频或播放列表链接" class="w-full resize-y rounded-md border border-border bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none"></textarea><div class="flex flex-row gap-2 sm:flex-col"><button type="submit" :disabled="importing || !importUrls.trim()" class="h-9 rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-50 cursor-pointer">{{ importing ? '导入中...' : '导入当前目录' }}</button><button type="button" @click="localBatchInput?.click()" class="h-9 rounded-md border border-border bg-white px-4 text-xs text-text-secondary cursor-pointer">上传多个本地视频</button><input ref="localBatchInput" type="file" multiple accept="video/*" class="hidden" @change="uploadLocalBatch" /></div></div></form>
                <section v-if="playingVideo" class="border-b border-border bg-black px-4 py-4 sm:px-6"><div class="mx-auto max-w-4xl"><div class="mb-2 flex items-center justify-between gap-3 text-white"><p class="truncate text-sm font-medium">{{ playingVideo.title }}</p><button @click="closePlayer" class="text-xs text-white/70 hover:text-white cursor-pointer">关闭播放器</button></div><video ref="videoPlayer" :src="playbackUrl" controls autoplay class="aspect-video w-full bg-black" @loadedmetadata="restorePlaybackPosition" @timeupdate="trackPlaybackProgress" @ended="finishPlayback"></video><div class="mt-2 flex items-center gap-2"><input v-model.trim="playerNote" placeholder="记录当前时间点的笔记" class="h-9 min-w-0 flex-1 rounded-md border border-white/20 bg-white/10 px-3 text-sm text-white placeholder:text-white/50" /><button @click="savePlayerNote" :disabled="!playerNote" class="h-9 rounded-md bg-white px-3 text-xs font-medium text-gray-900 disabled:opacity-50 cursor-pointer">添加笔记</button></div></div></section>
                <div v-if="!filteredVideos.length" class="flex flex-1 flex-col items-center justify-center px-6 text-center text-text-muted"><svg class="mb-3 h-10 w-10 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 6h6l2 2h8v11H4V6z" /></svg><p class="text-sm">这里还没有解析过的视频</p></div>
                <div v-else class="min-h-0 flex-1 overflow-auto">
                  <!-- 移动端卡片列表 -->
                  <ul class="divide-y divide-border-light md:hidden">
                    <li v-for="video in filteredVideos" :key="'m-' + video.id" class="px-4 py-3">
                      <button @click="openVideo(video)" class="block w-full text-left cursor-pointer">
                        <p class="text-sm font-medium text-text-primary hover:text-primary line-clamp-2">{{ video.title }}</p>
                        <p class="mt-1 truncate text-xs text-text-muted">{{ video.platform || '视频' }}<span v-if="video.uploader"> · {{ video.uploader }}</span><span v-if="video.duration_string"> · {{ video.duration_string }}</span></p>
                      </button>
                      <div class="mt-2 flex flex-wrap items-center gap-2">
                        <select :value="video.folder_id ?? ''" @change="moveVideo(video, $event.target.value)" class="h-8 min-w-0 flex-1 rounded-md border border-border bg-white px-2 text-xs text-text-secondary focus:border-primary focus:outline-none"><option value="">未归档</option><option v-for="folder in folderRows" :key="folder.id" :value="folder.id">{{ '—'.repeat(folder.depth) }} {{ folder.name }}</option></select>
                        <select :value="progressFor(video.id).completion_percent" @change="setVideoProgress(video, $event.target.value)" class="h-8 rounded-md border border-border bg-white px-2 text-xs text-text-secondary"><option :value="0">未学习</option><option :value="25">25%</option><option :value="50">50%</option><option :value="75">75%</option><option :value="100">已完成</option></select>
                      </div>
                      <div class="mt-2 flex items-center justify-between">
                        <span class="text-[11px]" :class="video.has_subtitle ? 'text-emerald-700' : 'text-amber-700'">{{ video.has_subtitle ? '字幕已就绪' : '等待字幕' }} · {{ formatDate(video.parsed_at) }}</span>
                        <span class="flex items-center gap-3"><button @click="renameVideo(video)" class="text-xs text-text-muted hover:text-primary cursor-pointer">重命名</button><button @click="playVideo(video)" class="text-xs font-medium text-primary cursor-pointer">播放</button><button @click="removeVideo(video)" class="text-xs text-text-muted hover:text-rose-600 cursor-pointer">移除</button></span>
                      </div>
                    </li>
                  </ul>
                  <!-- 桌面端表格 -->
                  <table class="hidden w-full min-w-[760px] table-fixed text-left md:table">
                    <thead class="sticky top-0 z-10 bg-gray-50 text-xs font-medium text-text-muted"><tr><th class="w-[44%] px-5 py-3">视频</th><th class="w-[18%] px-3 py-3">目录</th><th class="w-[14%] px-3 py-3">内容状态</th><th class="w-[14%] px-3 py-3">解析时间</th><th class="w-[10%] px-3 py-3 text-right">操作</th></tr></thead>
                    <tbody class="divide-y divide-border-light">
                      <tr v-for="video in filteredVideos" :key="video.id" class="hover:bg-gray-50/70">
                        <td class="px-5 py-3"><button @click="openVideo(video)" class="block w-full text-left cursor-pointer"><p class="truncate text-sm font-medium text-text-primary hover:text-primary">{{ video.title }}</p><p class="mt-1 truncate text-xs text-text-muted">{{ video.platform || '视频' }}<span v-if="video.uploader"> · {{ video.uploader }}</span><span v-if="video.duration_string"> · {{ video.duration_string }}</span></p></button></td>
                        <td class="px-3 py-3"><select :value="video.folder_id ?? ''" @change="moveVideo(video, $event.target.value)" class="h-8 w-full rounded-md border border-border bg-white px-2 text-xs text-text-secondary focus:border-primary focus:outline-none"><option value="">未归档</option><option v-for="folder in folderRows" :key="folder.id" :value="folder.id">{{ '—'.repeat(folder.depth) }} {{ folder.name }}</option></select></td>
                        <td class="px-3 py-3"><select :value="progressFor(video.id).completion_percent" @change="setVideoProgress(video, $event.target.value)" class="h-8 w-full rounded-md border border-border bg-white px-2 text-xs text-text-secondary"><option :value="0">未学习</option><option :value="25">学习 25%</option><option :value="50">学习 50%</option><option :value="75">学习 75%</option><option :value="100">已完成</option></select><p class="mt-1 text-[11px]" :class="video.has_subtitle ? 'text-emerald-700' : 'text-amber-700'">{{ video.has_subtitle ? '字幕已就绪' : '等待字幕' }}</p></td>
                        <td class="px-3 py-3 text-xs text-text-muted">{{ formatDate(video.parsed_at) }}</td>
                        <td class="px-3 py-3 text-right"><button @click="renameVideo(video)" class="mr-2 text-xs text-text-muted hover:text-primary cursor-pointer">重命名</button><button @click="playVideo(video)" class="mr-2 text-xs font-medium text-primary cursor-pointer">播放</button><button @click="removeVideo(video)" class="text-xs text-text-muted hover:text-rose-600 cursor-pointer">移除</button></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>

              <div v-else-if="activeView === 'dashboard'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
                <div class="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-4">
                  <div class="bg-white p-4"><p class="text-xs text-text-muted">平均得分</p><p class="mt-1 text-2xl font-semibold text-text-primary">{{ dashboard.average_score || 0 }}<span class="text-sm font-normal text-text-muted">%</span></p></div>
                  <div class="bg-white p-4"><p class="text-xs text-text-muted">已完成测试</p><p class="mt-1 text-2xl font-semibold text-text-primary">{{ dashboard.attempt_count || 0 }}</p></div>
                  <div class="bg-white p-4"><p class="text-xs text-text-muted">到期错题</p><p class="mt-1 text-2xl font-semibold text-amber-700">{{ dashboard.due_wrong_count || 0 }}</p></div>
                  <div class="bg-white p-4"><p class="text-xs text-text-muted">待复习闪卡</p><p class="mt-1 text-2xl font-semibold text-primary">{{ dashboard.due_flashcard_count || 0 }}</p></div>
                </div>
                <div class="mt-5 grid gap-6 lg:grid-cols-[1fr_1.35fr]">
                  <section>
                    <h4 class="text-sm font-semibold text-text-primary">前测 / 后测</h4>
                    <div class="mt-3 grid grid-cols-3 gap-2 rounded-md border border-border p-4 text-center"><div><p class="text-xs text-text-muted">前测</p><p class="mt-1 text-lg font-semibold">{{ scoreText(dashboard.pre_score) }}</p></div><div><p class="text-xs text-text-muted">提升</p><p class="mt-1 text-lg font-semibold" :class="(dashboard.improvement || 0) >= 0 ? 'text-emerald-700' : 'text-rose-600'">{{ improvementText }}</p></div><div><p class="text-xs text-text-muted">后测</p><p class="mt-1 text-lg font-semibold">{{ scoreText(dashboard.post_score) }}</p></div></div>
                    <p class="mt-5 text-xs text-text-muted">视频解析进度</p><div class="mt-2 h-2 overflow-hidden rounded-full bg-gray-100"><div class="h-full bg-emerald-500" :style="{ width: `${videoProgress}%` }"></div></div><p class="mt-1.5 text-xs text-text-muted">{{ dashboard.parsed_video_count || 0 }} / {{ dashboard.video_count || 0 }} 个视频已完成字幕</p>
                  </section>
                  <section>
                    <div class="flex items-center justify-between"><h4 class="text-sm font-semibold text-text-primary">知识点掌握度</h4><span class="text-xs text-text-muted">按薄弱程度排序</span></div>
                    <div v-if="!dashboard.mastery?.length" class="mt-3 rounded-md border border-dashed border-border p-6 text-center text-sm text-text-muted">完成一次测试后开始计算掌握度</div>
                    <div v-else class="mt-3 space-y-3"><div v-for="item in dashboard.mastery" :key="item.knowledge_point"><div class="flex items-center justify-between gap-3 text-xs"><button @click="startSpecializedTraining(item.knowledge_point)" class="truncate font-medium text-text-secondary hover:text-primary cursor-pointer" title="开始专项训练">{{ item.knowledge_point }}</button><span class="tabular-nums text-text-muted">{{ item.mastery_score }}%</span></div><div class="mt-1.5 h-2 overflow-hidden rounded-full bg-gray-100"><div class="h-full" :class="masteryColor(item.mastery_score)" :style="{ width: `${item.mastery_score}%` }"></div></div></div></div>
                  </section>
                </div>
                <section class="mt-6">
                  <div class="flex items-center justify-between"><h4 class="text-sm font-semibold text-text-primary">最近测试</h4><span class="text-xs text-text-muted">题库共 {{ dashboard.question_count || 0 }} 题</span></div>
                  <div v-if="!dashboard.history?.length" class="mt-3 rounded-md border border-dashed border-border p-6 text-center text-sm text-text-muted">暂无测试记录</div>
                  <div v-else class="mt-3 divide-y divide-border-light rounded-md border border-border"><div v-for="attempt in dashboard.history.slice(0, 8)" :key="attempt.id" class="flex items-center gap-3 px-4 py-3"><span class="w-16 shrink-0 text-xs text-text-muted">{{ phaseName(attempt.phase) }}</span><div class="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-gray-100"><div class="h-full bg-primary" :style="{ width: `${attempt.score}%` }"></div></div><strong class="w-12 text-right text-xs tabular-nums text-text-secondary">{{ attempt.score }}%</strong><span class="hidden w-24 text-right text-xs text-text-muted sm:block">{{ formatDate(attempt.created_at) }}</span></div></div>
                </section>
              </div>

              <div v-else-if="activeView === 'search'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
                <form @submit.prevent="submitCourseSearch" class="flex flex-wrap gap-2"><label class="relative min-w-[240px] flex-1"><svg class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-5-5m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg><input v-model.trim="courseQuery" placeholder="搜索或询问这门课程" class="h-11 w-full rounded-md border border-border pl-10 pr-3 text-sm focus:border-primary focus:outline-none" /></label><button type="submit" :disabled="courseSearching || courseQuery.length < 2" class="h-11 rounded-md border border-border px-5 text-sm font-medium text-text-secondary disabled:opacity-50 cursor-pointer">语义检索</button><button type="button" @click="submitCourseQuestion" :disabled="courseSearching || courseQuery.length < 2" class="h-11 rounded-md bg-primary px-5 text-sm font-medium text-white disabled:opacity-50 cursor-pointer">向课程提问</button></form>
                <p class="mt-2 text-xs text-text-muted">结果保留来源视频和时间点，可直接回到原始内容核对。</p>
                <section v-if="courseAnswer" class="mt-5 border-l-4 border-primary bg-primary/[0.04] p-4"><p class="whitespace-pre-wrap text-sm leading-7 text-text-primary">{{ courseAnswer.answer }}</p><div class="mt-4 space-y-2"><div v-for="(source, index) in courseAnswer.citations" :key="index" class="text-xs leading-5 text-text-muted"><strong class="text-text-secondary">证据 {{ index + 1 }} · {{ source.source_title }}</strong><span v-if="source.time_seconds"> · {{ formatDuration(source.time_seconds) }}</span><p>{{ source.quote }}</p></div></div></section>
                <div v-if="courseSearchDone && !courseResults.length" class="mt-8 rounded-md border border-dashed border-border p-10 text-center text-sm text-text-muted">没有找到相关课程内容</div>
                <div v-else class="mt-5 divide-y divide-border-light rounded-md border border-border"><article v-for="(item, index) in courseResults" :key="index" class="p-4"><div class="flex items-center justify-between gap-3"><span class="text-xs font-medium text-primary">{{ item.type === 'question' ? item.knowledge_point || '题库' : '课程字幕' }}</span><span class="text-xs tabular-nums text-text-muted">匹配 {{ Math.round(item.score * 100) }}%</span></div><p class="mt-2 text-sm leading-6 text-text-primary">{{ item.text }}</p><p v-if="item.answer" class="mt-2 text-xs leading-5 text-text-muted">{{ item.answer }}</p><div class="mt-2"><EvidenceLink :item="{ source_video_url: item.video_url, source_video_title: item.video_title, evidence_time_seconds: item.time_seconds }" /></div></article></div>
              </div>

              <div v-else-if="activeView === 'automation'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6"><div class="flex flex-wrap items-center justify-between gap-3"><div><h4 class="text-sm font-semibold text-text-primary">后台自动处理</h4><p class="mt-1 text-xs text-text-muted">按字幕、语义索引、知识点和题库顺序处理目录内全部视频。</p></div><button @click="startPipeline" :disabled="pipelineStarting" class="h-9 rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-50 cursor-pointer">{{ pipelineStarting ? '正在创建...' : '处理整门课程' }}</button></div><div v-if="!processingJobs.length" class="mt-5 rounded-md border border-dashed border-border p-10 text-center text-sm text-text-muted">还没有自动处理任务</div><div v-else class="mt-5 space-y-3"><article v-for="job in processingJobs" :key="job.id" class="rounded-md border border-border p-4"><div class="flex items-center justify-between gap-3"><div><p class="text-sm font-semibold text-text-primary">任务 #{{ job.id }} · {{ pipelineStatus(job.status) }}</p><p class="mt-1 text-xs text-text-muted">阶段：{{ pipelineStage(job.stage) }} · {{ job.completed_items }}/{{ job.total_items }} 个视频</p></div><button v-if="job.status === 'failed'" @click="retryPipeline(job)" class="h-8 rounded-md border border-border px-3 text-xs cursor-pointer">重试</button></div><div class="mt-3 h-2 overflow-hidden rounded-full bg-gray-100"><div class="h-full bg-primary transition-[width]" :style="{ width: `${job.progress}%` }"></div></div><p v-if="job.error" class="mt-2 text-xs text-amber-700">{{ job.error }}</p></article></div></div>

              <div v-else-if="activeView === 'materials'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6"><div class="grid gap-4 lg:grid-cols-2"><section class="rounded-md border border-border p-4"><h4 class="text-sm font-semibold text-text-primary">上传学习资料</h4><p class="mt-1 text-xs text-text-muted">支持 PDF、PPTX、TXT、Markdown、CSV 和字幕文件。</p><button @click="materialInput?.click()" :disabled="materialLoading" class="mt-4 h-9 rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-50 cursor-pointer">选择资料</button><input ref="materialInput" type="file" accept=".pdf,.pptx,.txt,.md,.csv,.srt,.vtt" class="hidden" @change="uploadMaterial" /></section><form @submit.prevent="importWebMaterial" class="rounded-md border border-border p-4"><h4 class="text-sm font-semibold text-text-primary">导入网页</h4><p class="mt-1 text-xs text-text-muted">网页正文会进入课程语义索引和 AI 问答证据库。</p><div class="mt-4 flex gap-2"><input v-model.trim="materialWebUrl" type="url" required placeholder="https://..." class="h-9 min-w-0 flex-1 rounded-md border border-border px-3 text-sm" /><button :disabled="materialLoading" class="h-9 rounded-md border border-border px-3 text-xs font-medium cursor-pointer">导入</button></div></form></div><div v-if="!courseMaterials.length" class="mt-5 rounded-md border border-dashed border-border p-10 text-center text-sm text-text-muted">尚未导入学习资料</div><div v-else class="mt-5 divide-y divide-border-light rounded-md border border-border"><article v-for="item in courseMaterials" :key="item.id" class="flex items-center gap-3 p-4"><span class="rounded bg-gray-100 px-2 py-1 text-[11px] font-semibold uppercase text-text-muted">{{ item.material_type }}</span><div class="min-w-0 flex-1"><p class="truncate text-sm font-medium text-text-primary">{{ item.name }}</p><p class="mt-1 text-xs text-text-muted">{{ item.character_count }} 字 · {{ formatDate(item.created_at) }} · {{ materialStatus(item.status) }}</p><p v-if="item.error" class="mt-1 text-xs text-rose-600">{{ item.error }}</p></div><button @click="processMaterial(item)" :disabled="item.status === 'processing'" class="text-xs font-medium text-primary disabled:opacity-40 cursor-pointer">{{ item.status === 'processing' ? '处理中' : '生成题卡' }}</button><button @click="removeMaterial(item)" class="text-xs text-text-muted hover:text-rose-600 cursor-pointer">删除</button></article></div></div>

              <div v-else-if="activeView === 'quality'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6"><div class="flex flex-wrap items-center justify-between gap-3"><div><h4 class="text-sm font-semibold text-text-primary">知识与题目质量</h4><p class="mt-1 text-xs text-text-muted">自动合并近似知识点，并检查证据、答案和重复题。</p></div><div class="flex gap-2"><button @click="runKnowledgeDedup" class="h-9 rounded-md border border-border px-3 text-xs font-medium cursor-pointer">合并重复知识点</button><button @click="runQualityCheck" class="h-9 rounded-md bg-primary px-3 text-xs font-medium text-white cursor-pointer">重新质检</button></div></div><div class="mt-5 grid grid-cols-3 gap-px overflow-hidden rounded-md border border-border bg-border"><div class="bg-white p-4"><p class="text-xs text-text-muted">已通过</p><p class="mt-1 text-xl font-semibold text-emerald-700">{{ qualityCounts.approved }}</p></div><div class="bg-white p-4"><p class="text-xs text-text-muted">待复核</p><p class="mt-1 text-xl font-semibold text-amber-700">{{ qualityCounts.review }}</p></div><div class="bg-white p-4"><p class="text-xs text-text-muted">不合格</p><p class="mt-1 text-xl font-semibold text-rose-600">{{ qualityCounts.rejected }}</p></div></div><div class="mt-5 divide-y divide-border-light rounded-md border border-border"><article v-for="item in questionQuality" :key="item.question_bank_id" class="p-4"><div class="flex items-center justify-between gap-3"><span class="text-xs font-medium" :class="qualityClass(item.status)">{{ qualityLabel(item.status) }} · {{ item.quality_score }} 分</span><span class="text-xs text-text-muted">{{ item.knowledge_point }}</span></div><p class="mt-2 text-sm text-text-primary">{{ item.question.question }}</p><p v-if="item.issues.length" class="mt-2 text-xs text-amber-700">{{ item.issues.join('；') }}</p></article></div></div>

              <div v-else-if="activeView === 'settings'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6"><div class="grid gap-6 lg:grid-cols-[320px_1fr]"><form @submit.prevent="saveReminders" class="rounded-md border border-border p-5"><h4 class="text-sm font-semibold text-text-primary">学习提醒</h4><label class="mt-4 flex items-center gap-2 text-sm"><input v-model="reminderForm.enabled" type="checkbox" class="h-4 w-4" />启用每日提醒</label><label class="mt-4 block text-xs text-text-muted">提醒时间<input v-model="reminderForm.reminder_time" type="time" class="mt-1.5 h-10 w-full rounded-md border border-border px-3 text-sm" /></label><label class="mt-4 flex items-center gap-2 text-sm"><input v-model="reminderForm.browser_enabled" type="checkbox" class="h-4 w-4" />浏览器通知</label><label class="mt-3 flex items-center gap-2 text-sm"><input v-model="reminderForm.email_enabled" type="checkbox" class="h-4 w-4" />邮件通知</label><label class="mt-3 flex items-center gap-2 text-sm"><input v-model="reminderForm.wecom_enabled" type="checkbox" class="h-4 w-4" />企业微信通知</label><button class="mt-5 h-10 w-full rounded-md bg-primary text-sm font-medium text-white cursor-pointer">保存提醒</button></form><section><div><p class="text-xs font-semibold text-primary">MODEL USAGE / 30 DAYS</p><h4 class="mt-1 text-xl font-semibold text-text-primary">模型任务与费用</h4></div><div class="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-4"><div class="bg-white p-4"><p class="text-xs text-text-muted">请求</p><p class="mt-1 text-xl font-semibold">{{ modelUsage.totals?.requests || 0 }}</p></div><div class="bg-white p-4"><p class="text-xs text-text-muted">输入 Token</p><p class="mt-1 text-xl font-semibold">{{ modelUsage.totals?.input_tokens || 0 }}</p></div><div class="bg-white p-4"><p class="text-xs text-text-muted">输出 Token</p><p class="mt-1 text-xl font-semibold">{{ modelUsage.totals?.output_tokens || 0 }}</p></div><div class="bg-white p-4"><p class="text-xs text-text-muted">预估费用</p><p class="mt-1 text-xl font-semibold">${{ Number(modelUsage.totals?.estimated_cost || 0).toFixed(4) }}</p></div></div><div class="mt-5 space-y-2"><div v-for="day in modelUsage.daily" :key="day.day" class="flex items-center gap-3 text-xs"><span class="w-24 text-text-muted">{{ day.day }}</span><div class="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-gray-100"><div class="h-full bg-primary" :style="{ width: usageWidth(day.requests) }"></div></div><span class="w-16 text-right tabular-nums text-text-secondary">{{ day.requests }} 次</span></div></div></section></div></div>

              <div v-else-if="activeView === 'flashcards'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
                <div class="mb-4 flex items-center justify-between gap-3"><p class="text-sm text-text-secondary">点击卡片查看答案，再标记记住或忘记。</p><span class="text-xs text-text-muted">1 / 3 / 7 / 14 天复习</span></div>
                <div v-if="!flashcards.length" class="rounded-md border border-dashed border-border p-10 text-center text-sm text-text-muted">生成一套课程试卷后，题目会自动转为闪卡</div>
                <div v-else class="grid gap-3 lg:grid-cols-2">
                  <article v-for="card in flashcards" :key="card.id" class="rounded-md border border-border bg-white p-4">
                    <div class="flex items-center justify-between gap-3"><span class="text-xs font-medium text-primary">{{ card.knowledge_point }}</span><span class="text-xs text-text-muted">第 {{ card.stage + 1 }} 阶段</span></div>
                    <button @click="toggleCard(card.id)" class="mt-3 min-h-20 w-full text-left text-sm font-medium leading-6 text-text-primary cursor-pointer">{{ revealedCards.has(card.id) ? card.back : card.front }}</button>
                    <div class="mt-3 flex items-center justify-between border-t border-border-light pt-3"><EvidenceLink :item="card" /><div v-if="revealedCards.has(card.id)" class="flex gap-2"><button @click="submitCardReview(card, false)" class="h-8 rounded-md border border-border px-3 text-xs text-text-secondary hover:border-rose-300 hover:text-rose-600 cursor-pointer">忘记</button><button @click="submitCardReview(card, true)" class="h-8 rounded-md bg-primary px-3 text-xs font-medium text-white cursor-pointer">记住</button></div></div>
                  </article>
                </div>
              </div>

              <div v-else-if="activeView === 'graph'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
                <div class="flex items-center justify-between gap-3"><div><h4 class="text-sm font-semibold text-text-primary">课程知识路径</h4><p class="mt-1 text-xs text-text-muted">从前置知识向后学习，点击薄弱节点开始专项训练。</p></div><span class="text-xs text-text-muted">{{ knowledgeGraph.nodes?.length || 0 }} 个知识点</span></div>
                <div v-if="!knowledgeGraph.nodes?.length" class="mt-5 rounded-md border border-dashed border-border p-10 text-center text-sm text-text-muted">生成试卷并完成答题后自动形成知识图谱</div>
                <div v-else class="mt-5 overflow-x-auto pb-3"><div class="flex min-w-max items-center gap-2"><template v-for="(node, index) in knowledgeGraph.nodes" :key="node.id"><button @click="startSpecializedTraining(node.id)" class="w-40 rounded-md border bg-white p-4 text-left hover:border-primary cursor-pointer" :class="node.mastery_score < 60 ? 'border-amber-300' : 'border-border'"><span class="block truncate text-sm font-semibold text-text-primary">{{ node.label }}</span><span class="mt-2 block text-xs text-text-muted">掌握 {{ node.mastery_score }}%</span><span class="mt-2 block h-1.5 overflow-hidden rounded-full bg-gray-100"><span class="block h-full" :class="masteryColor(node.mastery_score)" :style="{ width: node.mastery_score + '%' }"></span></span></button><svg v-if="index < knowledgeGraph.nodes.length - 1" class="h-5 w-5 shrink-0 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M5 12h14m-4-4l4 4-4 4" /></svg></template></div></div>
              </div>

              <div v-else-if="activeView === 'notes'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
                <div class="flex flex-wrap items-center justify-between gap-3"><div><h4 class="text-sm font-semibold text-text-primary">时间点笔记</h4><p class="mt-1 text-xs text-text-muted">笔记绑定视频与时间点，可转为闪卡。</p></div><button @click="organizeNotes" :disabled="organizingNotes || !courseNotes.length" class="h-9 rounded-md border border-border px-3 text-xs font-medium text-text-secondary hover:border-primary hover:text-primary disabled:opacity-50 cursor-pointer">{{ organizingNotes ? 'AI 整理中...' : 'AI 整理笔记' }}</button></div>
                <form @submit.prevent="submitNote" class="mt-4 grid gap-2 rounded-md border border-border bg-gray-50/70 p-4 sm:grid-cols-[180px_100px_1fr_auto]"><select v-model.number="noteForm.videoId" class="h-9 rounded-md border border-border bg-white px-2 text-xs"><option :value="null">选择视频</option><option v-for="video in courseProgress" :key="video.video_id" :value="video.video_id">{{ video.title }}</option></select><input v-model.number="noteForm.timeSeconds" type="number" min="0" placeholder="秒数" class="h-9 rounded-md border border-border bg-white px-2 text-sm" /><input v-model.trim="noteForm.content" placeholder="记录关键观点、疑问或自己的理解" class="h-9 min-w-0 rounded-md border border-border bg-white px-3 text-sm" /><button :disabled="!noteForm.videoId || !noteForm.content" class="h-9 rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-50 cursor-pointer">添加</button></form>
                <div v-if="organizedNotes" class="mt-4 whitespace-pre-wrap rounded-md border-l-4 border-primary bg-primary/[0.04] p-4 text-sm leading-6 text-text-secondary">{{ organizedNotes }}</div>
                <div v-if="!courseNotes.length" class="mt-5 rounded-md border border-dashed border-border p-10 text-center text-sm text-text-muted">还没有课程笔记</div>
                <div v-else class="mt-5 divide-y divide-border-light rounded-md border border-border"><article v-for="note in courseNotes" :key="note.id" class="p-4"><div class="flex items-center justify-between gap-3"><button @click="jumpToEvidence({ source_video_url: note.video_url, source_video_title: note.video_title, evidence_time_seconds: note.time_seconds })" class="truncate text-xs font-medium text-primary hover:underline cursor-pointer">{{ note.video_title }} · {{ formatDuration(note.time_seconds) }}</button><div class="flex gap-3"><button @click="convertNoteToCard(note)" class="text-xs text-text-muted hover:text-primary cursor-pointer">转闪卡</button><button @click="removeNote(note)" class="text-xs text-text-muted hover:text-rose-600 cursor-pointer">删除</button></div></div><p class="mt-2 whitespace-pre-wrap text-sm leading-6 text-text-primary">{{ note.content }}</p></article></div>
              </div>

              <div v-else-if="activeView === 'goal'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
                <div class="grid gap-6 lg:grid-cols-[320px_1fr]"><form @submit.prevent="submitGoal" class="rounded-md border border-border p-5"><h4 class="text-sm font-semibold text-text-primary">学习目标</h4><label class="mt-4 block text-xs text-text-muted">考试日期<input v-model="goalForm.examDate" type="date" class="mt-1.5 h-10 w-full rounded-md border border-border px-3 text-sm" /></label><label class="mt-4 block text-xs text-text-muted">目标分数<input v-model.number="goalForm.targetScore" type="number" min="1" max="100" class="mt-1.5 h-10 w-full rounded-md border border-border px-3 text-sm" /></label><label class="mt-4 block text-xs text-text-muted">每日学习分钟<input v-model.number="goalForm.dailyMinutes" type="number" min="5" max="480" class="mt-1.5 h-10 w-full rounded-md border border-border px-3 text-sm" /></label><button class="mt-5 h-10 w-full rounded-md bg-primary text-sm font-medium text-white cursor-pointer">保存并重新预测</button></form><section><p class="text-xs font-semibold text-primary">LEARNING FORECAST</p><h4 class="mt-1 text-xl font-semibold text-text-primary">按当前节奏预计 {{ goalPrediction.predicted_score || 0 }} 分</h4><div class="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-4"><div class="bg-white p-4"><p class="text-xs text-text-muted">当前水平</p><p class="mt-1 text-xl font-semibold">{{ goalPrediction.current_score || 0 }}</p></div><div class="bg-white p-4"><p class="text-xs text-text-muted">目标</p><p class="mt-1 text-xl font-semibold">{{ goalPrediction.target_score || 0 }}</p></div><div class="bg-white p-4"><p class="text-xs text-text-muted">剩余天数</p><p class="mt-1 text-xl font-semibold">{{ goalPrediction.days_left ?? '—' }}</p></div><div class="bg-white p-4"><p class="text-xs text-text-muted">建议每日</p><p class="mt-1 text-xl font-semibold">{{ goalPrediction.required_daily_minutes || 0 }}<span class="text-xs font-normal text-text-muted"> 分钟</span></p></div></div><div class="mt-5 rounded-md border p-4" :class="goalPrediction.on_track ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'"><p class="text-sm font-semibold" :class="goalPrediction.on_track ? 'text-emerald-800' : 'text-amber-800'">{{ goalPrediction.on_track ? '当前计划可以达到目标' : '当前投入不足以稳定达到目标' }}</p><p class="mt-1 text-xs leading-5" :class="goalPrediction.on_track ? 'text-emerald-700' : 'text-amber-700'">预测会根据测验成绩、知识点掌握度和剩余学习时间持续更新。</p></div></section></div>
              </div>

              <div v-else-if="activeView === 'question-bank'" class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
                <div class="mb-4 flex items-center justify-between gap-3"><p class="text-sm text-text-secondary">生成过的题目会持续保存，并用于快速和自适应组卷。</p><span class="text-xs text-text-muted">共 {{ questionBank.length }} 题</span></div>
                <div v-if="!questionBank.length" class="rounded-md border border-dashed border-border p-10 text-center text-sm text-text-muted">完成首次 AI 组卷后建立课程题库</div>
                <div v-else class="divide-y divide-border-light rounded-md border border-border">
                  <article v-for="item in questionBank" :key="item.id" class="p-4"><div class="flex flex-wrap items-center justify-between gap-2"><span class="text-xs font-medium text-primary">{{ item.knowledge_point }}</span><span class="text-xs text-text-muted">使用 {{ item.times_used }} 次 · 正确 {{ item.correct_count }} 次</span></div><p class="mt-2 text-sm font-medium leading-6 text-text-primary">{{ item.question.question }}</p><p class="mt-2 text-xs leading-5 text-text-muted">参考：{{ referenceAnswer(item.question) }}</p><div class="mt-2"><EvidenceLink :item="item" /></div></article>
                </div>
              </div>

              <div v-else class="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
                <div class="mb-4 flex items-center justify-between gap-3"><p class="text-sm text-text-secondary">答错后自动加入，按 1 / 3 / 7 / 14 天安排复习。</p><button v-if="wrongQuestions.some(isDue)" @click="startWrongReview" class="h-9 rounded-md bg-primary px-4 text-sm font-medium text-white cursor-pointer">复习到期错题</button></div>
                <div v-if="!wrongQuestions.length" class="rounded-md border border-dashed border-border p-10 text-center text-sm text-text-muted">暂无错题记录</div>
                <div v-else class="divide-y divide-border-light rounded-md border border-border">
                  <article v-for="item in wrongQuestions" :key="item.id" class="p-4"><div class="flex flex-wrap items-center justify-between gap-2"><span class="text-xs font-medium text-primary">{{ item.knowledge_point }}</span><span class="text-xs" :class="isDue(item) ? 'text-amber-700' : 'text-text-muted'">{{ dueLabel(item) }}</span></div><p class="mt-2 text-sm font-medium leading-6 text-text-primary">{{ item.question.question }}</p><p class="mt-2 text-xs leading-5 text-text-muted">参考：{{ referenceAnswer(item.question) }}</p><div v-if="diagnosisFor(item)" class="mt-3 rounded-md bg-amber-50 p-3"><p class="text-xs font-semibold text-amber-800">{{ diagnosisFor(item).category }}：{{ diagnosisFor(item).diagnosis }}</p><p class="mt-1 text-xs text-amber-700">建议：{{ diagnosisFor(item).action }}</p></div><div class="mt-2 flex items-center justify-between"><EvidenceLink :item="item" /><button @click="refreshDiagnosis(item)" class="text-xs text-text-muted hover:text-primary cursor-pointer">AI 深度诊断</button></div></article>
                </div>
              </div>
            </template>

            <template v-else>
              <div class="flex items-center justify-between gap-3 border-b border-border px-5 py-4"><div class="min-w-0"><p class="text-xs font-medium text-primary">{{ phaseLabel }} · {{ modeLabel }}</p><h3 class="mt-0.5 truncate text-base font-semibold text-text-primary">{{ quizData?.title || selectedFolderTitle }}</h3></div><button @click="closeQuiz" class="h-9 rounded-md border border-border px-3 text-sm text-text-secondary hover:border-primary hover:text-primary cursor-pointer">返回课程</button></div>
              <div v-if="quizLoading" class="border-b border-primary/15 bg-primary/[0.04] px-5 py-3"><div class="flex items-center justify-between gap-3 text-xs"><span class="font-medium text-primary">{{ quizProgress.message }}</span><span class="tabular-nums text-text-muted">{{ quizProgress.completedQuestions }} / {{ quizProgress.totalQuestions }} 题</span></div><div class="mt-2 h-1.5 overflow-hidden rounded-full bg-primary/10"><div class="h-full rounded-full bg-primary transition-[width] duration-500" :style="{ width: `${quizProgress.percent}%` }"></div></div></div>
              <div v-if="quizError" class="border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-800">{{ quizError }}</div>
              <div v-if="!quizData" class="flex flex-1 items-center justify-center text-sm text-text-muted"><span v-if="quizLoading" class="mr-3 h-5 w-5 animate-spin rounded-full border-2 border-primary/20 border-t-primary"></span>{{ quizLoading ? '正在生成第一批题目...' : '暂无已生成试卷' }}</div>
              <div v-else class="min-h-0 flex-1 overflow-y-auto px-5 sm:px-8">
                <div class="flex flex-wrap items-end justify-between gap-3 border-b border-border-light py-4"><p class="text-xs text-text-muted">{{ quizData.questions.length }} 题 · 满分 {{ quizData.max_score }} 分 · 来源 {{ quizData.source_videos?.length || quizProgress.sourceCount }} 个视频</p><div v-if="quizResult" class="text-right"><strong class="text-2xl text-primary">{{ quizResult.total_score }}</strong><span class="text-sm text-text-muted"> / {{ quizResult.max_score }}</span></div></div>
                <section v-for="(question, index) in quizData.questions" :key="question.id" class="border-b border-border-light py-5">
                  <div class="flex items-start gap-3"><span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-light text-xs font-semibold text-primary">{{ index + 1 }}</span><div class="min-w-0 flex-1"><div class="flex justify-between gap-2 text-xs text-text-muted"><span>{{ questionTypeLabel(question.type) }} · {{ question.knowledge_point || '课程综合' }}</span><span>{{ question.points }} 分</span></div><p class="mt-1.5 text-sm font-medium leading-6 text-text-primary">{{ question.question }}</p>
                    <div v-if="!['short_answer', 'analysis'].includes(question.type)" class="mt-3 space-y-2"><label v-for="option in question.options" :key="option.key" :class="optionClass(question, option.key)" class="flex min-h-10 cursor-pointer items-start gap-3 rounded-md border px-3 py-2 text-sm"><input :type="question.type === 'multiple' ? 'checkbox' : 'radio'" :name="`course-quiz-${question.id}`" :checked="isSelected(question.id, option.key)" :disabled="Boolean(quizResult)" @change="selectOption(question, option.key)" class="mt-0.5 h-4 w-4 accent-current" /><span class="font-medium text-text-secondary">{{ option.key }}</span><span>{{ option.text }}</span></label></div>
                    <textarea v-else v-model="quizAnswers[question.id]" :disabled="Boolean(quizResult)" rows="4" placeholder="请结合课程内容作答..." class="mt-3 w-full resize-y rounded-md border border-border px-3 py-2 text-sm leading-6 focus:border-primary focus:outline-none"></textarea>
                    <div v-if="resultById[String(question.id)]" class="mt-3 border-l-2 pl-3" :class="resultById[String(question.id)].correct ? 'border-emerald-500' : 'border-amber-500'"><p class="text-xs font-semibold" :class="resultById[String(question.id)].correct ? 'text-emerald-700' : 'text-amber-700'">{{ resultById[String(question.id)].awarded_points }} / {{ resultById[String(question.id)].max_points }} 分</p><p class="mt-1 text-xs leading-5 text-text-secondary">{{ resultById[String(question.id)].feedback }}</p><p class="mt-1 text-xs leading-5 text-text-muted"><strong>参考：</strong>{{ referenceAnswer(question) }}</p><blockquote v-if="question.evidence_quote" class="mt-2 rounded-r-md bg-gray-50 px-3 py-2 text-xs leading-5 text-text-secondary">“{{ question.evidence_quote }}”</blockquote><div class="mt-2"><EvidenceLink :item="question" /></div></div>
                  </div></div>
                </section>
              </div>
              <footer v-if="quizData" class="flex shrink-0 items-center justify-between gap-3 border-t border-border px-5 py-4"><button @click="startCourseQuiz(true)" :disabled="quizLoading || quizGrading" class="text-sm font-medium text-text-secondary hover:text-primary disabled:opacity-50 cursor-pointer">重新组卷</button><button @click="submitQuiz" :disabled="quizLoading || quizGrading || answeredCount === 0 || Boolean(quizResult)" class="h-10 min-w-28 rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-50 cursor-pointer">{{ quizGrading ? 'AI 阅卷中...' : quizResult ? '阅卷完成' : '提交答卷' }}</button></footer>
            </template>
          </main>
        </div>
      </section>
      <section v-if="continuousOpen" class="absolute inset-x-3 bottom-3 top-3 z-20 mx-auto flex max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-white shadow-2xl sm:inset-x-10 sm:bottom-10 sm:top-10"><header class="flex h-16 shrink-0 items-center justify-between border-b border-border px-5"><div><p class="text-xs font-semibold text-primary">连续学习 · {{ continuousIndex + 1 }}/{{ continuousItems.length }}</p><h3 class="mt-1 text-sm font-semibold text-text-primary">{{ continuousCurrent?.title || '今日任务已完成' }}</h3></div><button @click="stopContinuousSession" class="h-9 rounded-md border border-border px-3 text-xs text-text-secondary cursor-pointer">退出</button></header><div class="flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto p-6 text-center"><template v-if="continuousCurrent"><span class="rounded bg-gray-100 px-2 py-1 text-xs font-medium text-text-muted">{{ continuousTypeLabel(continuousCurrent.type) }}</span><p class="mt-5 max-w-xl text-lg font-semibold leading-8 text-text-primary">{{ continuousCurrent.title }}</p><button v-if="['flashcard','wrong'].includes(continuousCurrent.type)" @click="continuousReveal = !continuousReveal" class="mt-6 min-h-12 rounded-md border border-border px-5 text-sm font-medium text-text-secondary cursor-pointer">{{ continuousReveal ? continuousReference : '显示参考答案' }}</button><div v-if="continuousReveal && ['flashcard','wrong'].includes(continuousCurrent.type)" class="mt-6 w-full max-w-xl border-t border-border-light pt-5"><div class="flex items-center justify-center gap-2"><button @click="toggleVoiceRecording" :disabled="voiceScoring" class="h-10 rounded-md border px-4 text-sm font-medium cursor-pointer" :class="voiceRecording ? 'border-rose-300 text-rose-600' : 'border-border text-text-secondary'">{{ voiceRecording ? '停止并评分' : '语音复述' }}</button><span v-if="voiceScoring" class="text-xs text-text-muted">正在识别...</span></div><div v-if="voiceResult" class="mt-4 rounded-md bg-gray-50 p-4 text-left"><p class="text-sm font-semibold" :class="voiceResult.score >= 80 ? 'text-emerald-700' : 'text-amber-700'">复述得分 {{ voiceResult.score }}</p><p class="mt-2 text-xs leading-5 text-text-secondary">{{ voiceResult.transcript }}</p><p class="mt-2 text-xs text-text-muted">{{ voiceResult.feedback }}</p></div></div></template><div v-else><p class="text-xl font-semibold text-text-primary">今日连续学习已完成</p><p class="mt-2 text-sm text-text-muted">复习、薄弱点训练和视频任务已走完一轮。</p></div></div><footer class="flex h-16 shrink-0 items-center justify-between border-t border-border px-5"><button @click="previousContinuous" :disabled="continuousIndex === 0" class="h-9 rounded-md border border-border px-4 text-sm disabled:opacity-40 cursor-pointer">上一项</button><button @click="nextContinuous" class="h-9 rounded-md bg-primary px-5 text-sm font-medium text-white cursor-pointer">{{ continuousCurrent ? '完成并继续' : '关闭' }}</button></footer></section>
    </div>
  </Teleport>

  <!-- 重命名视频弹窗 -->
  <Teleport to="body">
    <div v-if="renameTarget" class="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 backdrop-blur-sm px-4" @click.self="closeRename">
      <div class="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div class="flex items-center justify-between border-b border-border-light px-5 py-4">
          <h3 class="text-base font-semibold text-text-primary">重命名视频</h3>
          <button @click="closeRename" class="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted hover:bg-gray-100 hover:text-text-primary cursor-pointer" title="关闭">
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div class="p-5">
          <label class="block text-sm font-medium text-text-secondary mb-1.5">视频名称</label>
          <textarea
            ref="renameInput"
            v-model="renameValue"
            rows="3"
            maxlength="300"
            @keydown.enter.prevent="confirmRename"
            class="w-full resize-y rounded-xl border border-border px-3 py-2.5 text-sm text-text-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            placeholder="输入新的视频名称"
          ></textarea>
          <p class="mt-1 text-xs text-text-muted">按 Enter 保存，Shift+Enter 换行</p>
        </div>
        <div class="flex justify-end gap-2 border-t border-border-light px-5 py-3.5">
          <button @click="closeRename" :disabled="renameSaving" class="h-9 rounded-lg border border-border px-4 text-sm font-medium text-text-secondary hover:bg-gray-50 disabled:opacity-50 cursor-pointer">取消</button>
          <button @click="confirmRename" :disabled="renameSaving || !renameValue.trim()" class="h-9 rounded-lg bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-dark disabled:opacity-50 cursor-pointer">{{ renameSaving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, reactive, ref, watch } from 'vue'
import {
  askCourse, batchImportCourses, checkQuestionQuality, completeTodayTask,
  createCourseNote, createLibraryFolder, deduplicateKnowledge, deleteCourseMaterial,
  deleteCourseNote, deleteLibraryFolder, deleteLibraryVideo, diagnoseMistake,
  generateCourseQuiz, getCourseNotes, getCourseProgress, getFlashcards,
  getContinuousLearning, getCourseMaterials, getModelUsage, getProcessingJobs,
  getKnowledgeGraph, getLatestCourseQuiz, getLearningDashboard, getLearningGoal,
  getLibrary, getMistakeDiagnoses, getQuestionBank, getQuestionQuality,
  getReminderSettings, getTodayPlan, getVideoPlayback, getWrongQuestions, markReminderShown,
  gradeVoiceRecall, importCourseWebPage,
  moveLibraryVideo, noteToFlashcard, organizeCourseNotes, processCourseMaterial, recordCourseAttempt,
  renameLibraryVideo,
  retryProcessingJob, reviewFlashcard, saveLearningGoal, saveReminderSettings,
  semanticSearchCourse, startProcessingPipeline, updateLibraryFolder,
  updateVideoProgress, uploadCourseMaterial,
} from '../api/library'
import { gradeVideoQuiz } from '../api/summarize'
import { uploadLocalVideo } from '../api/video'

const props = defineProps({ visible: Boolean, refreshKey: { type: Number, default: 0 } })
const emit = defineEmits(['close', 'open-video', 'changed'])
const library = reactive({ folders: [], videos: [] })
const loading = ref(false)
const learningLoading = ref(false)
const saving = ref(false)
const error = ref('')
const search = ref('')
const selectedFolderId = ref('all')
const expandedFolders = ref(new Set())
const folderInput = ref(null)
const folderForm = reactive({ visible: false, name: '', parentId: null })
const activeView = ref('videos')
const dashboard = ref({})
const flashcards = ref([])
const wrongQuestions = ref([])
const questionBank = ref([])
const todayPlan = ref({ tasks: [] })
const todayMinutes = ref(30)
const courseProgress = ref([])
const courseQuery = ref('')
const courseResults = ref([])
const courseSearching = ref(false)
const courseSearchDone = ref(false)
const courseAnswer = ref(null)
const knowledgeGraph = ref({ nodes: [], edges: [] })
const courseNotes = ref([])
const organizedNotes = ref('')
const organizingNotes = ref(false)
const noteForm = reactive({ videoId: null, timeSeconds: 0, content: '' })
const goalPrediction = ref({})
const goalForm = reactive({ examDate: '', targetScore: 80, dailyMinutes: 30 })
const mistakeDiagnoses = ref([])
const importOpen = ref(false)
const importUrls = ref('')
const importing = ref(false)
const localBatchInput = ref(null)
const playingVideo = ref(null)
const playbackUrl = ref('')
const videoPlayer = ref(null)
const playerNote = ref('')
const pendingSeekSeconds = ref(null)
const resumeContinuousAfterPlayer = ref(false)
let lastProgressSync = 0
const processingJobs = ref([])
const pipelineStarting = ref(false)
let pipelinePollTimer = null
const courseMaterials = ref([])
const materialInput = ref(null)
const materialWebUrl = ref('')
const materialLoading = ref(false)
const questionQuality = ref([])
const reminderForm = reactive({ enabled: false, reminder_time: '20:00', browser_enabled: true, email_enabled: false, wecom_enabled: false })
const modelUsage = ref({ daily: [], totals: {} })
const continuousOpen = ref(false)
const continuousItems = ref([])
const continuousIndex = ref(0)
const continuousReveal = ref(false)
const voiceRecording = ref(false)
const voiceScoring = ref(false)
const voiceResult = ref(null)
let voiceRecorder = null
let voiceStream = null
let voiceChunks = []
const specializedKnowledgePoint = ref('')
const revealedCards = ref(new Set())
const quizSettings = reactive({ mode: 'standard', phase: 'practice' })
const quizOpen = ref(false)
const quizLoading = ref(false)
const quizGrading = ref(false)
const quizError = ref('')
const quizData = ref(null)
const quizId = ref(null)
const quizAnswers = ref({})
const quizResult = ref(null)
const quizFromContinuous = ref(false)
const quizProgress = reactive({ message: '', completedQuestions: 0, totalQuestions: 16, percent: 0, sourceCount: 0 })

const EvidenceLink = defineComponent({
  props: { item: { type: Object, required: true } },
  setup(componentProps) {
    return () => {
      const item = componentProps.item
      if (!item.source_video_url && !item.source_video_title) return null
      const seconds = Math.max(0, Math.floor(Number(item.evidence_time_seconds) || 0))
      return h('button', {
        type: 'button',
        class: 'text-xs font-medium text-primary hover:underline cursor-pointer',
        onClick: () => jumpToEvidence(item),
      }, `来源：${item.source_video_title || '课程视频'}${seconds ? ` · ${formatDuration(seconds)}` : ''}`)
    }
  },
})

function flattenFolders() {
  const byParent = new Map()
  for (const folder of library.folders) { const key = folder.parent_id ?? null; if (!byParent.has(key)) byParent.set(key, []); byParent.get(key).push(folder) }
  const rows = []
  const walk = (parentId, depth) => { for (const folder of byParent.get(parentId) || []) { const children = byParent.get(folder.id) || []; rows.push({ ...folder, depth, hasChildren: children.length > 0 }); if (expandedFolders.value.has(folder.id)) walk(folder.id, depth + 1) } }
  walk(null, 0)
  return rows
}

const folderRows = computed(flattenFolders)
const unfiledCount = computed(() => library.videos.filter(video => video.folder_id == null).length)
const selectedFolder = computed(() => library.folders.find(folder => folder.id === selectedFolderId.value))
const selectedFolderTitle = computed(() => selectedFolderId.value === 'all' ? '全部解析历史' : selectedFolderId.value === 'unfiled' ? '未归档视频' : selectedFolder.value?.name || '课程目录')
const descendantIds = computed(() => { if (typeof selectedFolderId.value !== 'number') return new Set(); const ids = new Set([selectedFolderId.value]); let changed = true; while (changed) { changed = false; for (const folder of library.folders) if (ids.has(folder.parent_id) && !ids.has(folder.id)) { ids.add(folder.id); changed = true } } return ids })
const recursiveVideoCount = computed(() => library.videos.filter(video => descendantIds.value.has(video.folder_id)).length)
const filteredVideos = computed(() => { let videos = library.videos; if (selectedFolderId.value === 'unfiled') videos = videos.filter(video => video.folder_id == null); else if (typeof selectedFolderId.value === 'number') videos = videos.filter(video => video.folder_id === selectedFolderId.value); const term = search.value.toLocaleLowerCase(); return term ? videos.filter(video => `${video.title} ${video.uploader} ${video.platform}`.toLocaleLowerCase().includes(term)) : videos })
const answeredCount = computed(() => !quizData.value ? 0 : quizData.value.questions.filter(question => { const answer = quizAnswers.value[question.id]; return Array.isArray(answer) ? answer.length : String(answer || '').trim() }).length)
const resultById = computed(() => Object.fromEntries((quizResult.value?.results || []).map(item => [String(item.id), item])))
const videoProgress = computed(() => dashboard.value.video_count ? Math.round((dashboard.value.parsed_video_count || 0) * 100 / dashboard.value.video_count) : 0)
const improvementText = computed(() => dashboard.value.improvement == null ? '—' : `${dashboard.value.improvement > 0 ? '+' : ''}${dashboard.value.improvement}%`)
const learningTabs = computed(() => [
  { id: 'today', label: '今日' }, { id: 'videos', label: '视频' },
  { id: 'automation', label: '自动处理' }, { id: 'dashboard', label: '掌握度' },
  { id: 'search', label: '课程问答' }, { id: 'materials', label: '资料' },
  { id: 'flashcards', label: '闪卡', count: dashboard.value.due_flashcard_count || 0 },
  { id: 'wrong', label: '错题本', count: dashboard.value.due_wrong_count || 0 },
  { id: 'graph', label: '知识图谱' }, { id: 'notes', label: '笔记' },
  { id: 'quality', label: '质量' }, { id: 'goal', label: '目标' },
  { id: 'settings', label: '设置' }, { id: 'question-bank', label: '题库', count: dashboard.value.question_count || 0 },
])
const continuousCurrent = computed(() => continuousItems.value[continuousIndex.value] || null)
const continuousReference = computed(() => {
  const current = continuousCurrent.value
  if (!current) return ''
  if (current.type === 'flashcard') return current.data?.back || ''
  return referenceAnswer(current.data?.question || {})
})
const qualityCounts = computed(() => questionQuality.value.reduce((result, item) => {
  result[item.status] = (result[item.status] || 0) + 1
  return result
}, { approved: 0, review: 0, rejected: 0 }))
const riskLabel = computed(() => ({ high: '高遗忘风险', medium: '有内容待巩固', low: '记忆状态稳定' })[todayPlan.value.forgetting_risk] || '正在计算')
const riskClass = computed(() => ({ high: 'bg-rose-50 text-rose-700', medium: 'bg-amber-50 text-amber-700', low: 'bg-emerald-50 text-emerald-700' })[todayPlan.value.forgetting_risk] || 'bg-gray-100 text-text-muted')
const modeLabel = computed(() => ({ quick: '快速测试', standard: '标准测试', exam: '模拟考试', adaptive: '自适应测试', wrong: '错题复习' })[quizSettings.mode])
const phaseLabel = computed(() => ({ pre: '学习前测', practice: '日常练习', post: '学习后测' })[quizSettings.phase])

async function loadLibrary() { if (!props.visible) return; loading.value = true; error.value = ''; try { const data = await getLibrary(); library.folders = data.folders || []; library.videos = data.videos || []; expandedFolders.value = new Set(library.folders.map(folder => folder.id)) } catch (err) { error.value = apiError(err, '读取资料库失败') } finally { loading.value = false } }
watch(() => [props.visible, props.refreshKey], ([shown]) => {
  if (shown) loadLibrary()
  else {
    closePlayer()
    stopContinuousSession()
    if (pipelinePollTimer) clearTimeout(pipelinePollTimer)
  }
}, { immediate: true })

function treeRowClass(id) { return selectedFolderId.value === id ? 'bg-primary-light text-primary font-medium' : 'text-text-secondary hover:bg-white hover:text-text-primary' }
function selectFolder(id) {
  selectedFolderId.value = id
  activeView.value = typeof id === 'number' ? 'today' : 'videos'
  search.value = ''
  error.value = ''
  dashboard.value = {}
  flashcards.value = []
  wrongQuestions.value = []
  questionBank.value = []
  if (typeof id === 'number') loadLearning('today')
}
function toggleFolder(id) { const next = new Set(expandedFolders.value); next.has(id) ? next.delete(id) : next.add(id); expandedFolders.value = next }
function directVideoCount(id) { return library.videos.filter(video => video.folder_id === id).length }
function beginCreateFolder(parentId) { folderForm.visible = true; folderForm.parentId = parentId; folderForm.name = ''; nextTick(() => folderInput.value?.focus()) }
async function submitFolder() { if (!folderForm.name || saving.value) return; saving.value = true; try { await createLibraryFolder(folderForm.name, folderForm.parentId); folderForm.visible = false; await loadLibrary(); emit('changed') } catch (err) { error.value = apiError(err, '创建目录失败') } finally { saving.value = false } }
async function renameFolder(folder) { const name = window.prompt('新的目录名称', folder.name)?.trim(); if (!name || name === folder.name) return; try { await updateLibraryFolder(folder.id, { name }); await loadLibrary(); emit('changed') } catch (err) { error.value = apiError(err, '重命名失败') } }
async function removeFolder(folder) { if (!window.confirm(`删除目录“${folder.name}”？其中的视频和子目录会自动上移，不会被删除。`)) return; try { await deleteLibraryFolder(folder.id); if (selectedFolderId.value === folder.id) selectedFolderId.value = folder.parent_id ?? 'all'; await loadLibrary(); emit('changed') } catch (err) { error.value = apiError(err, '删除目录失败') } }
async function moveVideo(video, folderId) { try { await moveLibraryVideo(video.id, folderId === '' ? null : Number(folderId)); await loadLibrary(); emit('changed') } catch (err) { error.value = apiError(err, '移动视频失败') } }
async function removeVideo(video) { if (!window.confirm(`从解析历史中移除“${video.title}”？已生成的字幕和总结缓存不会删除。`)) return; try { await deleteLibraryVideo(video.id); await loadLibrary(); emit('changed') } catch (err) { error.value = apiError(err, '移除失败') } }
const renameTarget = ref(null)
const renameValue = ref('')
const renameSaving = ref(false)
const renameInput = ref(null)
function renameVideo(video) { renameTarget.value = video; renameValue.value = video.title || ''; nextTick(() => renameInput.value?.focus()) }
function closeRename() { if (renameSaving.value) return; renameTarget.value = null; renameValue.value = '' }
async function confirmRename() {
  const video = renameTarget.value
  if (!video) return
  const title = renameValue.value.trim()
  if (!title) return
  if (title === video.title) { closeRename(); return }
  renameSaving.value = true
  try {
    await renameLibraryVideo(video.id, title)
    await loadLibrary()
    emit('changed')
    renameTarget.value = null
    renameValue.value = ''
  } catch (err) {
    error.value = apiError(err, '重命名失败')
  } finally {
    renameSaving.value = false
  }
}
function openVideo(video) { emit('open-video', video.url); emit('close') }

async function switchView(view) {
  activeView.value = view
  await loadLearning(view)
}
async function loadDashboard() { if (typeof selectedFolderId.value !== 'number') return; try { dashboard.value = await getLearningDashboard(selectedFolderId.value) } catch (err) { error.value = apiError(err, '读取学习看板失败') } }
async function loadLearning(view = activeView.value) {
  if (typeof selectedFolderId.value !== 'number') return
  learningLoading.value = true
  error.value = ''
  try {
    const folderId = selectedFolderId.value
    if (view === 'today') {
      [todayPlan.value, dashboard.value] = await Promise.all([
        getTodayPlan(folderId, todayMinutes.value), getLearningDashboard(folderId),
      ])
    } else if (view === 'videos') {
      courseProgress.value = await getCourseProgress(folderId)
    } else if (view === 'automation') {
      processingJobs.value = await getProcessingJobs(folderId)
      schedulePipelinePoll()
    } else if (view === 'dashboard') {
      dashboard.value = await getLearningDashboard(folderId)
    } else if (view === 'flashcards') {
      [flashcards.value, dashboard.value] = await Promise.all([getFlashcards(folderId), getLearningDashboard(folderId)])
    } else if (view === 'wrong') {
      [wrongQuestions.value, mistakeDiagnoses.value, dashboard.value] = await Promise.all([getWrongQuestions(folderId), getMistakeDiagnoses(folderId), getLearningDashboard(folderId)])
    } else if (view === 'question-bank') {
      [questionBank.value, dashboard.value] = await Promise.all([getQuestionBank(folderId), getLearningDashboard(folderId)])
    } else if (view === 'graph') {
      knowledgeGraph.value = await getKnowledgeGraph(folderId)
    } else if (view === 'materials') {
      courseMaterials.value = await getCourseMaterials(folderId)
    } else if (view === 'notes') {
      [courseNotes.value, courseProgress.value] = await Promise.all([getCourseNotes(folderId), getCourseProgress(folderId)])
    } else if (view === 'goal') {
      goalPrediction.value = await getLearningGoal(folderId)
      syncGoalForm()
    } else if (view === 'quality') {
      questionQuality.value = await getQuestionQuality(folderId)
    } else if (view === 'settings') {
      const [reminders, usage] = await Promise.all([getReminderSettings(), getModelUsage(30)])
      Object.assign(reminderForm, {
        enabled: Boolean(reminders.enabled), reminder_time: reminders.reminder_time || '20:00',
        browser_enabled: Boolean(reminders.browser_enabled), email_enabled: Boolean(reminders.email_enabled),
        wecom_enabled: Boolean(reminders.wecom_enabled),
      })
      modelUsage.value = usage
    }
  } catch (err) {
    error.value = apiError(err, '读取学习记录失败')
  } finally {
    learningLoading.value = false
  }
}
function toggleCard(id) { const next = new Set(revealedCards.value); next.has(id) ? next.delete(id) : next.add(id); revealedCards.value = next }
async function submitCardReview(card, remembered) { try { await reviewFlashcard(card.id, remembered); revealedCards.value.delete(card.id); await loadLearning('flashcards') } catch (err) { error.value = apiError(err, '保存复习结果失败') } }
function startWrongReview() { specializedKnowledgePoint.value = ''; quizSettings.mode = 'wrong'; quizSettings.phase = 'practice'; startCourseQuiz(false) }
function startGeneralQuiz() { specializedKnowledgePoint.value = ''; startCourseQuiz(false) }

async function toggleTodayTask(task) {
  try {
    await completeTodayTask(selectedFolderId.value, task.key, !task.completed)
    task.completed = !task.completed
    todayPlan.value.completed_count = todayPlan.value.tasks.filter(item => item.completed).length
  } catch (err) { error.value = apiError(err, '保存任务状态失败') }
}

function runTodayTask(task) {
  if (task.type === 'wrong') return startWrongReview()
  if (task.type === 'flashcard') return switchView('flashcards')
  if (task.type === 'adaptive') return startSpecializedTraining(task.knowledge_point || '')
  if (task.type === 'video') {
    const video = library.videos.find(item => item.id === task.video_id)
    if (video) openVideo(video)
  }
}

async function submitCourseSearch() {
  if (courseQuery.value.length < 2 || courseSearching.value) return
  courseSearching.value = true
  courseSearchDone.value = false
  try {
    const data = await semanticSearchCourse(selectedFolderId.value, courseQuery.value)
    courseResults.value = (data.results || []).map(item => ({
      ...item, type: item.source_type, text: item.content,
      video_title: item.source_title, video_url: item.source_url, time_seconds: item.start_seconds,
    }))
    courseAnswer.value = null
    courseSearchDone.value = true
  } catch (err) { error.value = apiError(err, '课程搜索失败') }
  finally { courseSearching.value = false }
}

async function submitCourseQuestion() {
  if (courseQuery.value.length < 2 || courseSearching.value) return
  courseSearching.value = true
  try {
    courseAnswer.value = await askCourse(selectedFolderId.value, courseQuery.value)
    courseResults.value = []
    courseSearchDone.value = false
  } catch (err) { error.value = apiError(err, '课程问答失败') }
  finally { courseSearching.value = false }
}

async function playVideo(video, seekSeconds = null, resumeContinuous = false) {
  try {
    const playback = await getVideoPlayback(video.id)
    playingVideo.value = video
    playbackUrl.value = playback.url
    pendingSeekSeconds.value = Number.isFinite(Number(seekSeconds)) ? Math.max(0, Number(seekSeconds)) : null
    resumeContinuousAfterPlayer.value = resumeContinuous
    playerNote.value = ''
    lastProgressSync = 0
  } catch (err) { error.value = apiError(err, '获取播放地址失败') }
}

function jumpToEvidence(item) {
  const video = library.videos.find(candidate =>
    (item.source_video_url && candidate.url === item.source_video_url)
    || (item.source_video_title && candidate.title === item.source_video_title)
    || (item.video_url && candidate.url === item.video_url)
    || (item.video_title && candidate.title === item.video_title))
  if (!video) {
    error.value = '对应视频不在当前资料库中，无法使用内置播放器定位'
    return
  }
  playVideo(video, item.evidence_time_seconds ?? item.time_seconds ?? 0)
}

function closePlayer() {
  if (videoPlayer.value) videoPlayer.value.pause()
  syncPlayback(false)
  playingVideo.value = null
  playbackUrl.value = ''
  pendingSeekSeconds.value = null
  if (resumeContinuousAfterPlayer.value) {
    resumeContinuousAfterPlayer.value = false
    continuousOpen.value = true
    nextContinuous()
  }
}

function restorePlaybackPosition() {
  if (!videoPlayer.value) return
  const progress = progressFor(playingVideo.value?.id)
  const target = pendingSeekSeconds.value ?? progress.progress_seconds
  if (target) videoPlayer.value.currentTime = target
  pendingSeekSeconds.value = null
  videoPlayer.value.play().catch(() => {})
}

async function syncPlayback(completed = false) {
  const player = videoPlayer.value
  const video = playingVideo.value
  if (!player || !video || !Number.isFinite(player.duration)) return
  const percent = completed ? 100 : Math.min(99.9, player.currentTime * 100 / player.duration)
  try {
    await updateVideoProgress(video.id, {
      progress_seconds: completed ? player.duration : player.currentTime,
      duration_seconds: player.duration, completion_percent: percent,
      status: completed ? 'completed' : 'in_progress',
    })
    const item = progressFor(video.id)
    Object.assign(item, { progress_seconds: player.currentTime, duration_seconds: player.duration, completion_percent: percent, status: completed ? 'completed' : 'in_progress' })
  } catch {}
}

function trackPlaybackProgress() {
  const now = Date.now()
  if (now - lastProgressSync >= 12000) {
    lastProgressSync = now
    syncPlayback(false)
  }
}

function finishPlayback() { syncPlayback(true) }

async function savePlayerNote() {
  if (!playingVideo.value || !playerNote.value) return
  try {
    await createCourseNote(playingVideo.value.id, playerNote.value, videoPlayer.value?.currentTime || 0)
    playerNote.value = ''
  } catch (err) { error.value = apiError(err, '保存播放笔记失败') }
}

async function startPipeline() {
  if (pipelineStarting.value) return
  pipelineStarting.value = true
  try {
    await startProcessingPipeline(selectedFolderId.value)
    processingJobs.value = await getProcessingJobs(selectedFolderId.value)
    schedulePipelinePoll()
  } catch (err) { error.value = apiError(err, '创建处理任务失败') }
  finally { pipelineStarting.value = false }
}

function schedulePipelinePoll() {
  if (pipelinePollTimer) clearTimeout(pipelinePollTimer)
  if (activeView.value !== 'automation' || !processingJobs.value.some(job => ['queued', 'running'].includes(job.status))) return
  pipelinePollTimer = setTimeout(async () => {
    try { processingJobs.value = await getProcessingJobs(selectedFolderId.value) } catch {}
    schedulePipelinePoll()
  }, 2000)
}

async function retryPipeline(job) {
  try { await retryProcessingJob(job.id); processingJobs.value = await getProcessingJobs(selectedFolderId.value); schedulePipelinePoll() }
  catch (err) { error.value = apiError(err, '重试任务失败') }
}

function pipelineStatus(status) { return ({ queued: '等待中', running: '处理中', completed: '已完成', failed: '失败' })[status] || status }
function pipelineStage(stage) { return ({ queued: '排队', parsing: '读取视频', subtitle: '字幕', indexing: '语义索引', knowledge: '知识点', question_bank: '题库', completed: '完成', failed: '失败' })[stage] || stage }

async function uploadMaterial(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || materialLoading.value) return
  materialLoading.value = true
  try { await uploadCourseMaterial(selectedFolderId.value, file); courseMaterials.value = await getCourseMaterials(selectedFolderId.value) }
  catch (err) { error.value = apiError(err, '资料导入失败') }
  finally { materialLoading.value = false }
}

async function importWebMaterial() {
  if (!materialWebUrl.value || materialLoading.value) return
  materialLoading.value = true
  try { await importCourseWebPage(selectedFolderId.value, materialWebUrl.value); materialWebUrl.value = ''; courseMaterials.value = await getCourseMaterials(selectedFolderId.value) }
  catch (err) { error.value = apiError(err, '网页导入失败') }
  finally { materialLoading.value = false }
}

async function processMaterial(item) {
  try {
    await processCourseMaterial(item.id)
    item.status = 'processing'
    window.setTimeout(async () => {
      try { courseMaterials.value = await getCourseMaterials(selectedFolderId.value) } catch {}
    }, 2500)
  } catch (err) { error.value = apiError(err, '生成资料题卡失败') }
}

function materialStatus(status) { return ({ ready: '可用', processing: '正在生成题库与闪卡', failed: '处理失败' })[status] || status }

async function removeMaterial(item) {
  if (!window.confirm(`删除资料“${item.name}”？`)) return
  try { await deleteCourseMaterial(item.id); courseMaterials.value = await getCourseMaterials(selectedFolderId.value) }
  catch (err) { error.value = apiError(err, '删除资料失败') }
}

async function runKnowledgeDedup() {
  try {
    const data = await deduplicateKnowledge(selectedFolderId.value)
    error.value = data.merged ? `已合并 ${data.merged} 个重复知识点` : '没有发现需要合并的知识点'
  } catch (err) { error.value = apiError(err, '知识点合并失败') }
}

async function runQualityCheck() {
  try { questionQuality.value = await checkQuestionQuality(selectedFolderId.value) }
  catch (err) { error.value = apiError(err, '题目质检失败') }
}

function qualityLabel(status) { return ({ approved: '已通过', review: '待复核', rejected: '不合格' })[status] || status }
function qualityClass(status) { return ({ approved: 'text-emerald-700', review: 'text-amber-700', rejected: 'text-rose-600' })[status] || 'text-text-muted' }

async function saveReminders() {
  try {
    if (reminderForm.enabled && reminderForm.browser_enabled && 'Notification' in window && Notification.permission === 'default') await Notification.requestPermission()
    const saved = await saveReminderSettings(reminderForm)
    Object.assign(reminderForm, { ...saved, enabled: Boolean(saved.enabled), browser_enabled: Boolean(saved.browser_enabled), email_enabled: Boolean(saved.email_enabled), wecom_enabled: Boolean(saved.wecom_enabled) })
    maybeShowReminder(saved)
  } catch (err) { error.value = apiError(err, '保存提醒失败') }
}

async function maybeShowReminder(settings) {
  if (!settings.enabled || !settings.browser_enabled || !('Notification' in window) || Notification.permission !== 'granted') return
  const now = new Date()
  const [hour, minute] = String(settings.reminder_time || '20:00').split(':').map(Number)
  if (now.getHours() * 60 + now.getMinutes() < hour * 60 + minute || settings.last_notified_date === now.toISOString().slice(0, 10)) return
  new Notification('今日学习还未完成', { body: `当前课程有 ${todayPlan.value.due_review_count || 0} 项到期复习，打开连续学习即可开始。` })
  await markReminderShown().catch(() => {})
}

function usageWidth(requests) {
  const max = Math.max(1, ...(modelUsage.value.daily || []).map(item => Number(item.requests) || 0))
  return `${Math.max(4, Number(requests) * 100 / max)}%`
}

async function startContinuousSession() {
  try {
    const data = await getContinuousLearning(selectedFolderId.value)
    continuousItems.value = data.items || []
    continuousIndex.value = 0
    continuousReveal.value = false
    voiceResult.value = null
    continuousOpen.value = true
  } catch (err) { error.value = apiError(err, '读取连续学习任务失败') }
}

function stopContinuousSession() {
  continuousOpen.value = false
  stopVoiceStream()
}

function nextContinuous() {
  const current = continuousCurrent.value
  if (!current) return stopContinuousSession()
  if (current.type === 'video') {
    const video = library.videos.find(item => item.id === current.data?.video_id)
    continuousOpen.value = false
    if (video) playVideo(video, current.data?.progress_seconds || 0, true)
    else advanceContinuous()
    return
  }
  if (current.type === 'quiz') {
    continuousOpen.value = false
    specializedKnowledgePoint.value = current.data?.knowledge_point || ''
    quizSettings.mode = current.data?.mode || 'adaptive'
    quizSettings.phase = current.data?.phase || 'practice'
    startCourseQuiz(false, true)
    return
  }
  advanceContinuous()
}

function advanceContinuous() {
  continuousIndex.value += 1
  continuousReveal.value = false
  voiceResult.value = null
  if (continuousIndex.value >= continuousItems.value.length) stopContinuousSession()
}

function previousContinuous() { if (continuousIndex.value > 0) { continuousIndex.value -= 1; continuousReveal.value = false; voiceResult.value = null } }
function continuousTypeLabel(type) { return ({ flashcard: '闪卡复习', wrong: '错题回忆', video: '视频学习', quiz: '今日小测' })[type] || '学习任务' }

async function toggleVoiceRecording() {
  if (voiceRecording.value) return voiceRecorder?.stop()
  try {
    voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    voiceChunks = []
    voiceRecorder = new MediaRecorder(voiceStream)
    voiceRecorder.ondataavailable = event => { if (event.data.size) voiceChunks.push(event.data) }
    voiceRecorder.onstop = submitVoiceRecall
    voiceRecorder.start()
    voiceRecording.value = true
  } catch (err) { error.value = `无法使用麦克风: ${err.message}` }
}

async function submitVoiceRecall() {
  voiceRecording.value = false
  stopVoiceStream()
  if (!voiceChunks.length) return
  voiceScoring.value = true
  try {
    const blob = new Blob(voiceChunks, { type: voiceChunks[0]?.type || 'audio/webm' })
    voiceResult.value = await gradeVoiceRecall(blob, continuousReference.value, continuousCurrent.value?.title || '')
    if (voiceResult.value.score >= 80) setTimeout(nextContinuous, 1200)
  } catch (err) { error.value = apiError(err, '语音复述评分失败') }
  finally { voiceScoring.value = false }
}

function stopVoiceStream() {
  voiceStream?.getTracks().forEach(track => track.stop())
  voiceStream = null
  voiceRecording.value = false
}

function progressFor(videoId) {
  return courseProgress.value.find(item => item.video_id === videoId) || { completion_percent: 0 }
}

async function setVideoProgress(video, value) {
  const percent = Number(value)
  try {
    await updateVideoProgress(video.id, {
      completion_percent: percent,
      status: percent >= 100 ? 'completed' : percent > 0 ? 'in_progress' : 'not_started',
    })
    courseProgress.value = await getCourseProgress(selectedFolderId.value)
  } catch (err) { error.value = apiError(err, '保存视频进度失败') }
}

async function submitBatchImport() {
  const urls = importUrls.value.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
  if (!urls.length || importing.value) return
  importing.value = true
  try {
    const data = await batchImportCourses({ urls, parent_id: selectedFolderId.value })
    importUrls.value = ''
    importOpen.value = false
    await loadLibrary()
    await loadLearning('videos')
    emit('changed')
    if (data.rejected?.length) error.value = data.rejected.length + ' 个链接格式无效，已跳过'
  } catch (err) { error.value = apiError(err, '批量导入失败') }
  finally { importing.value = false }
}

async function uploadLocalBatch(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length || importing.value) return
  importing.value = true
  try {
    const urls = []
    for (const file of files) {
      const result = await uploadLocalVideo(file)
      if (result.success && result.data?.url) urls.push(result.data.url)
    }
    if (urls.length) {
      await batchImportCourses({ urls, parent_id: selectedFolderId.value })
      await loadLibrary()
      await loadLearning('videos')
      emit('changed')
    }
  } catch (err) { error.value = apiError(err, '本地视频批量上传失败') }
  finally { importing.value = false }
}

async function submitNote() {
  if (!noteForm.videoId || !noteForm.content) return
  try {
    await createCourseNote(noteForm.videoId, noteForm.content, noteForm.timeSeconds || 0)
    noteForm.content = ''
    noteForm.timeSeconds = 0
    courseNotes.value = await getCourseNotes(selectedFolderId.value)
  } catch (err) { error.value = apiError(err, '保存笔记失败') }
}

async function removeNote(note) {
  if (!window.confirm('删除这条笔记？')) return
  try {
    await deleteCourseNote(note.id)
    courseNotes.value = await getCourseNotes(selectedFolderId.value)
  } catch (err) { error.value = apiError(err, '删除笔记失败') }
}

async function convertNoteToCard(note) {
  try { await noteToFlashcard(note.id) }
  catch (err) { error.value = apiError(err, '转为闪卡失败') }
}

async function organizeNotes() {
  if (organizingNotes.value) return
  organizingNotes.value = true
  try {
    const data = await organizeCourseNotes(selectedFolderId.value)
    organizedNotes.value = data.markdown || ''
  } catch (err) { error.value = apiError(err, 'AI 整理笔记失败') }
  finally { organizingNotes.value = false }
}

function syncGoalForm() {
  const goal = goalPrediction.value.goal || {}
  goalForm.examDate = goal.exam_date || ''
  goalForm.targetScore = goal.target_score ?? 80
  goalForm.dailyMinutes = goal.daily_minutes ?? 30
}

async function submitGoal() {
  try {
    goalPrediction.value = await saveLearningGoal(selectedFolderId.value, {
      exam_date: goalForm.examDate || null,
      target_score: goalForm.targetScore,
      daily_minutes: goalForm.dailyMinutes,
    })
    todayMinutes.value = goalForm.dailyMinutes
    syncGoalForm()
  } catch (err) { error.value = apiError(err, '保存学习目标失败') }
}

function diagnosisFor(item) {
  return mistakeDiagnoses.value.find(row => row.question_bank_id === item.question_bank_id)
}

async function refreshDiagnosis(item) {
  try {
    await diagnoseMistake(selectedFolderId.value, item.question_bank_id, '')
    mistakeDiagnoses.value = await getMistakeDiagnoses(selectedFolderId.value)
  } catch (err) { error.value = apiError(err, 'AI 错因诊断失败') }
}

function startSpecializedTraining(knowledgePoint) {
  quizSettings.mode = 'adaptive'
  quizSettings.phase = 'practice'
  specializedKnowledgePoint.value = knowledgePoint || ''
  startCourseQuiz(false)
}

function closeQuiz() {
  quizOpen.value = false
  quizError.value = ''
  loadDashboard()
  if (quizFromContinuous.value) {
    quizFromContinuous.value = false
    continuousOpen.value = true
    advanceContinuous()
  }
}
async function openLatestQuiz() { if (typeof selectedFolderId.value !== 'number') return; quizOpen.value = true; quizData.value = null; quizResult.value = null; quizAnswers.value = {}; quizError.value = ''; try { const saved = await getLatestCourseQuiz(selectedFolderId.value); if (saved?.quiz) { quizData.value = saved.quiz; quizId.value = saved.id; quizSettings.mode = saved.quiz.mode || 'standard'; quizSettings.phase = saved.quiz.phase || 'practice'; quizProgress.sourceCount = saved.source_count } else quizError.value = '该目录还没有历史试卷' } catch (err) { quizError.value = apiError(err, '读取最近试卷失败') } }
async function startCourseQuiz(force = false, fromContinuous = false) { if (typeof selectedFolderId.value !== 'number' || quizLoading.value) return; quizFromContinuous.value = fromContinuous; quizOpen.value = true; quizLoading.value = true; quizError.value = ''; quizData.value = null; quizId.value = null; quizResult.value = null; quizAnswers.value = {}; const totals = { quick: 8, standard: 16, exam: 20, adaptive: 12, wrong: dashboard.value.due_wrong_count || 16 }; Object.assign(quizProgress, { message: '正在汇总目录视频内容...', completedQuestions: 0, totalQuestions: totals[quizSettings.mode], percent: 0, sourceCount: 0 }); let streamError = ''; let completeQuiz = null; try { await generateCourseQuiz(selectedFolderId.value, {
    quiz_progress: data => { try { const p = JSON.parse(data); Object.assign(quizProgress, { message: p.message || quizProgress.message, completedQuestions: p.completed_questions ?? quizProgress.completedQuestions, totalQuestions: p.total_questions ?? quizProgress.totalQuestions, percent: p.percent ?? quizProgress.percent, sourceCount: p.source_count ?? quizProgress.sourceCount }) } catch {} },
    quiz_batch: data => { try { const p = JSON.parse(data); quizData.value = { title: p.title, max_score: 100, questions: [...(quizData.value?.questions || []), ...(p.questions || [])] }; Object.assign(quizProgress, { message: `第 ${p.batch_index}/${p.total_batches} 批${p.type_label}已生成`, completedQuestions: p.completed_questions, totalQuestions: p.total_questions, percent: p.percent, sourceCount: p.source_count }) } catch { streamError = '题目数据格式错误' } },
    quiz_complete: data => { try { const p = JSON.parse(data); completeQuiz = p.quiz; quizData.value = p.quiz; quizId.value = p.quiz_id; quizProgress.sourceCount = p.source_count; quizProgress.percent = 100 } catch { streamError = '完整试卷格式错误' } },
    error: data => { try { streamError = JSON.parse(data).message } catch { streamError = data } },
  }, { force, mode: quizSettings.mode, phase: quizSettings.phase, knowledge_point: specializedKnowledgePoint.value || undefined }); if (streamError) throw new Error(streamError); if (!completeQuiz) throw new Error('课程试卷生成未完成') } catch (err) { quizError.value = err.message || '课程组卷失败' } finally { quizLoading.value = false } }

function questionTypeLabel(type) { return ({ single: '单选题', multiple: '多选题', true_false: '判断题', short_answer: '简答题', analysis: '分析题' })[type] || '测试题' }
function isSelected(id, key) { const answer = quizAnswers.value[id]; return Array.isArray(answer) ? answer.includes(key) : answer === key }
function selectOption(question, key) { if (quizResult.value) return; if (question.type === 'multiple') { const values = Array.isArray(quizAnswers.value[question.id]) ? [...quizAnswers.value[question.id]] : []; const index = values.indexOf(key); index >= 0 ? values.splice(index, 1) : values.push(key); quizAnswers.value[question.id] = values } else quizAnswers.value[question.id] = key }
function optionClass(question, key) { const selected = isSelected(question.id, key); if (!quizResult.value) return selected ? 'border-primary bg-primary-light/60' : 'border-border-light hover:border-primary/50'; const correct = (question.answer || []).includes(key); if (correct) return 'border-emerald-300 bg-emerald-50'; if (selected) return 'border-rose-300 bg-rose-50'; return 'border-border-light opacity-70' }
function referenceAnswer(question) { if (['short_answer', 'analysis'].includes(question.type)) return question.reference_answer || question.explanation; return (question.answer || []).map(key => { const option = (question.options || []).find(item => item.key === key); return option ? `${key}. ${option.text}` : key }).join('；') }
async function submitQuiz() { if (!quizData.value || quizGrading.value || !answeredCount.value) return; quizGrading.value = true; try { quizResult.value = await gradeVideoQuiz(quizData.value, quizAnswers.value); const saved = await recordCourseAttempt(selectedFolderId.value, { quiz_id: quizId.value, quiz: quizData.value, answers: quizAnswers.value, grading: quizResult.value, mode: quizSettings.mode, phase: quizSettings.phase }); dashboard.value = saved.dashboard || dashboard.value } catch (err) { quizError.value = apiError(err, 'AI 阅卷或学习记录保存失败') } finally { quizGrading.value = false } }

function masteryColor(score) { return score >= 80 ? 'bg-emerald-500' : score >= 60 ? 'bg-sky-500' : 'bg-amber-500' }
function scoreText(score) { return score == null ? '—' : `${score}%` }
function phaseName(phase) { return ({ pre: '学习前测', practice: '日常练习', post: '学习后测' })[phase] || '测试' }
function isDue(item) { return item.due_at && new Date(item.due_at).getTime() <= Date.now() }
function dueLabel(item) { if (!item.due_at) return '已完成复习'; return isDue(item) ? '现在应复习' : `下次 ${formatDate(item.due_at)}` }
function formatDate(value) { if (!value) return ''; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', year: 'numeric' }) }
function formatDuration(seconds) { const value = Math.max(0, Math.floor(seconds)); const hours = Math.floor(value / 3600); const minutes = Math.floor((value % 3600) / 60); const secs = value % 60; return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}` : `${minutes}:${String(secs).padStart(2, '0')}` }
function apiError(err, fallback) { const detail = err.response?.data?.detail; return typeof detail === 'string' ? detail : err.message || fallback }
</script>
