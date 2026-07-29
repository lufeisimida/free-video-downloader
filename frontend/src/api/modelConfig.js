import axios from 'axios'
import { getToken } from './auth'

function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function getModelConfig() {
  const res = await axios.get('/api/model-config', { headers: authHeaders() })
  return res.data.data
}

export async function createModelProfile(payload) {
  const res = await axios.post('/api/model-config/profiles', payload, { headers: authHeaders() })
  return res.data.data
}

export async function updateModelProfile(profileId, payload) {
  const res = await axios.put(`/api/model-config/profiles/${profileId}`, payload, { headers: authHeaders() })
  return res.data.data
}

export async function activateModelProfile(profileId) {
  const res = await axios.post(`/api/model-config/profiles/${profileId}/activate`, {}, { headers: authHeaders() })
  return res.data.data
}

export async function deleteModelProfile(profileId) {
  const res = await axios.delete(`/api/model-config/profiles/${profileId}`, { headers: authHeaders() })
  return res.data.data
}

export async function testModelConfig(payload = {}) {
  const res = await axios.post('/api/model-config/test', payload, { headers: authHeaders() })
  return res.data.data
}
