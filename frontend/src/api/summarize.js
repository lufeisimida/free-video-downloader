/**
 * AI 视频总结 API 封装
 * 使用原生 fetch + ReadableStream 处理 SSE 流式响应
 */

import { getToken } from './auth'

export async function handleSSEStream(response, callbacks) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = ''
  let dataLines = []
  let hasData = false

  function dispatch() {
    if (hasData && currentEvent) {
      const handler = callbacks[currentEvent]
      if (handler) handler(dataLines.join('\n'))
    }
    dataLines = []
    hasData = false
    currentEvent = ''
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line === '') {
        dispatch()
        continue
      }

      if (line.startsWith(':')) continue

      const colonIdx = line.indexOf(':')
      if (colonIdx < 0) continue

      const field = line.slice(0, colonIdx)
      let val = line.slice(colonIdx + 1)
      if (val.startsWith(' ')) val = val.slice(1)

      if (field === 'event') {
        currentEvent = val
      } else if (field === 'data') {
        hasData = true
        dataLines.push(val)
      }
    }
  }
  dispatch()
}

function authHeaders() {
  const token = getToken()
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

export async function summarizeVideo(url, language = 'zh', callbacks = {}, options = {}) {
  const response = await fetch('/api/summarize', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      url,
      language,
      title: options.title || '',
      force: Boolean(options.force),
      parts: Array.isArray(options.parts) ? options.parts : undefined,
    }),
  })

  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`)
  }

  await handleSSEStream(response, callbacks)
}

export async function chatWithVideo(url, question, subtitleText = '', callbacks = {}) {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ url, question, subtitle_text: subtitleText }),
  })

  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`)
  }

  await handleSSEStream(response, callbacks)
}

export async function clearVideoChat(url) {
  const response = await fetch('/api/chat/clear', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ url }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `清空问答失败: ${response.status}`)
  }
  const payload = await response.json()
  return payload.data || payload
}

async function parseJsonResponse(response, fallbackMessage) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || fallbackMessage || `请求失败: ${response.status}`)
  }
  return data
}

export async function generateVideoQuiz(url, subtitleText = '', language = 'zh', force = false) {
  const response = await fetch('/api/quiz/generate', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ url, subtitle_text: subtitleText, language, force }),
  })
  return parseJsonResponse(response, '生成理解测试失败')
}

export async function generateVideoQuizStream(
  url,
  subtitleText = '',
  language = 'zh',
  force = false,
  callbacks = {},
) {
  const response = await fetch('/api/quiz/generate-stream', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ url, subtitle_text: subtitleText, language, force }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `生成理解测试失败: ${response.status}`)
  }
  await handleSSEStream(response, callbacks)
}

export async function gradeVideoQuiz(quiz, answers) {
  const response = await fetch('/api/quiz/grade', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ quiz, answers }),
  })
  return parseJsonResponse(response, '理解测试阅卷失败')
}

export async function getQuizState(url) {
  const response = await fetch('/api/quiz/state/get', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ url }),
  })
  return parseJsonResponse(response, '读取答题进度失败')
}

export async function saveQuizState(url, state) {
  const response = await fetch('/api/quiz/state/save', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ url, state }),
  })
  return parseJsonResponse(response, '保存答题进度失败')
}
