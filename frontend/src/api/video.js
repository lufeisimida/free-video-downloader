import axios from 'axios'
import { getToken } from './auth'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export async function parseVideo(url) {
  const { data } = await api.post('/parse', { url })
  return data
}

export async function uploadLocalVideo(file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/upload-local-video', formData, {
    timeout: 600000,
    onUploadProgress: (event) => {
      if (!onProgress || !event.total) return
      onProgress(Math.round(event.loaded * 100 / event.total))
    },
  })
  return data
}

export async function getDirectUrl(url, formatId) {
  const { data } = await api.post('/direct-url', { url, format_id: formatId })
  return data
}

export async function fetchThumbnail(url) {
  const response = await api.get('/proxy/thumbnail', {
    params: { url },
    responseType: 'blob',
    timeout: 30000,
  })
  return response.data
}

export function getDownloadUrl() {
  return '/api/download'
}

export async function downloadViaServer(url, formatId) {
  const response = await api.post(
    '/download',
    { url, format_id: formatId },
    { responseType: 'blob', timeout: 600000 }
  )
  return response
}
