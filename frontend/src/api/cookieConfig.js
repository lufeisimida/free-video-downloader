import axios from 'axios'
import { getToken } from './auth'

function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function getCookieConfig() {
  const res = await axios.get('/api/cookie-config', { headers: authHeaders() })
  return res.data.data
}

export async function updateCookieConfig(cookies) {
  const res = await axios.put('/api/cookie-config', { cookies }, { headers: authHeaders() })
  return res.data.data
}

export async function clearCookieConfig() {
  const res = await axios.delete('/api/cookie-config', { headers: authHeaders() })
  return res.data.data
}

export async function testCookieConfig(url = '') {
  const res = await axios.post('/api/cookie-config/test', { url }, { headers: authHeaders() })
  return res.data.data
}
