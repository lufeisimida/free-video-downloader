import axios from 'axios'
import { getToken } from './auth'
import { handleSSEStream } from './summarize'


function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function getLibrary() {
  const response = await axios.get('/api/library', { headers: authHeaders() })
  return response.data.data
}

export async function createLibraryFolder(name, parentId = null) {
  const response = await axios.post(
    '/api/library/folders',
    { name, parent_id: parentId },
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function updateLibraryFolder(folderId, payload) {
  const response = await axios.patch(
    `/api/library/folders/${folderId}`,
    payload,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function deleteLibraryFolder(folderId) {
  const response = await axios.delete(`/api/library/folders/${folderId}`, { headers: authHeaders() })
  return response.data.data
}

export async function moveLibraryVideo(videoId, folderId = null) {
  const response = await axios.patch(
    `/api/library/videos/${videoId}`,
    { folder_id: folderId },
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function renameLibraryVideo(videoId, title) {
  const response = await axios.patch(
    `/api/library/videos/${videoId}/title`,
    { title },
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function deleteLibraryVideo(videoId) {
  await axios.delete(`/api/library/videos/${videoId}`, { headers: authHeaders() })
}

export async function getLatestCourseQuiz(folderId) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/quiz/latest`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function generateCourseQuiz(folderId, callbacks = {}, options = {}) {
  const payload = typeof options === 'boolean' ? { force: options } : options
  const response = await fetch(`/api/library/folders/${folderId}/quiz/generate-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ language: 'zh', force: false, mode: 'standard', phase: 'practice', ...payload }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || `课程组卷失败: ${response.status}`)
  }
  await handleSSEStream(response, callbacks)
}

export async function recordCourseAttempt(folderId, payload) {
  const response = await axios.post(
    `/api/library/folders/${folderId}/attempts`,
    payload,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getLearningDashboard(folderId) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/learning/dashboard`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getQuestionBank(folderId) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/learning/question-bank`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getWrongQuestions(folderId, dueOnly = false) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/learning/wrong-questions`,
    { params: { due_only: dueOnly }, headers: authHeaders() },
  )
  return response.data.data
}

export async function getFlashcards(folderId, dueOnly = false) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/learning/flashcards`,
    { params: { due_only: dueOnly }, headers: authHeaders() },
  )
  return response.data.data
}

export async function reviewFlashcard(cardId, remembered) {
  const response = await axios.post(
    `/api/library/learning/flashcards/${cardId}/review`,
    { remembered },
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getTodayPlan(folderId, minutes) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/learning/today`,
    { params: { minutes }, headers: authHeaders() },
  )
  return response.data.data
}

export async function completeTodayTask(folderId, taskKey, completed = true) {
  await axios.post(
    `/api/library/folders/${folderId}/learning/today/complete`,
    { task_key: taskKey, completed },
    { headers: authHeaders() },
  )
}

export async function searchCourse(folderId, query, limit = 12) {
  const response = await axios.post(
    `/api/library/folders/${folderId}/learning/search`,
    { query, limit },
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getCourseProgress(folderId) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/learning/progress`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function updateVideoProgress(videoId, payload) {
  const response = await axios.patch(
    `/api/library/learning/videos/${videoId}/progress`,
    payload,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getCourseNotes(folderId) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/learning/notes`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getVideoNotes(videoId) {
  const response = await axios.get(
    `/api/library/learning/videos/${videoId}/notes`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function createCourseNote(videoId, content, timeSeconds = 0) {
  const response = await axios.post(
    '/api/library/learning/notes',
    { video_id: videoId, content, time_seconds: timeSeconds },
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function deleteCourseNote(noteId) {
  await axios.delete(`/api/library/learning/notes/${noteId}`, { headers: authHeaders() })
}

export async function organizeCourseNotes(folderId) {
  const response = await axios.post(
    `/api/library/folders/${folderId}/learning/notes/organize`,
    {},
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function noteToFlashcard(noteId) {
  await axios.post(
    `/api/library/learning/notes/${noteId}/flashcard`,
    {},
    { headers: authHeaders() },
  )
}

export async function getLearningGoal(folderId) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/learning/goal`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function saveLearningGoal(folderId, payload) {
  const response = await axios.put(
    `/api/library/folders/${folderId}/learning/goal`,
    payload,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getKnowledgeGraph(folderId) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/learning/knowledge-graph`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getMistakeDiagnoses(folderId) {
  const response = await axios.get(
    `/api/library/folders/${folderId}/learning/diagnoses`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function diagnoseMistake(folderId, questionBankId, answer = '') {
  const response = await axios.post(
    `/api/library/folders/${folderId}/learning/diagnose`,
    { question_bank_id: questionBankId, answer },
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function batchImportCourses(payload) {
  const response = await axios.post(
    '/api/library/folders/batch-import',
    payload,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function startProcessingPipeline(folderId, payload = {}) {
  const response = await axios.post(
    `/api/library/efficiency/folders/${folderId}/pipeline`,
    { force: false, generate_questions: true, priority: 50, ...payload },
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getProcessingJobs(folderId) {
  const response = await axios.get(
    `/api/library/efficiency/folders/${folderId}/pipeline`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function retryProcessingJob(jobId) {
  const response = await axios.post(
    `/api/library/efficiency/jobs/${jobId}/retry`, {}, { headers: authHeaders() },
  )
  return response.data.data
}

export async function semanticSearchCourse(folderId, query, limit = 12) {
  const response = await axios.post(
    `/api/library/efficiency/folders/${folderId}/semantic-search`,
    { query, limit }, { headers: authHeaders() },
  )
  return response.data.data
}

export async function askCourse(folderId, query, limit = 6) {
  const response = await axios.post(
    `/api/library/efficiency/folders/${folderId}/ask`,
    { query, limit }, { headers: authHeaders() },
  )
  return response.data.data
}

export async function getContinuousLearning(folderId) {
  const response = await axios.get(
    `/api/library/efficiency/folders/${folderId}/continuous`,
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getReminderSettings() {
  const response = await axios.get('/api/library/efficiency/reminders', { headers: authHeaders() })
  return response.data.data
}

export async function saveReminderSettings(payload) {
  const response = await axios.put('/api/library/efficiency/reminders', payload, { headers: authHeaders() })
  return response.data.data
}

export async function getPendingReminders() {
  const response = await axios.get('/api/library/efficiency/reminders/pending', { headers: authHeaders() })
  return response.data.data
}

export async function markReminderShown(deliveryIds = []) {
  await axios.post(
    '/api/library/efficiency/reminders/notified',
    { delivery_ids: deliveryIds },
    { headers: authHeaders() },
  )
}

export async function getCourseMaterials(folderId) {
  const response = await axios.get(
    `/api/library/efficiency/folders/${folderId}/materials`, { headers: authHeaders() },
  )
  return response.data.data
}

export async function uploadCourseMaterial(folderId, file) {
  const form = new FormData()
  form.append('file', file)
  const response = await axios.post(
    `/api/library/efficiency/folders/${folderId}/materials/upload`, form,
    { headers: { ...authHeaders(), 'Content-Type': 'multipart/form-data' } },
  )
  return response.data.data
}

export async function importCourseWebPage(folderId, url) {
  const response = await axios.post(
    `/api/library/efficiency/folders/${folderId}/materials/web`, { url },
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function deleteCourseMaterial(materialId) {
  await axios.delete(`/api/library/efficiency/materials/${materialId}`, { headers: authHeaders() })
}

export async function processCourseMaterial(materialId, questionCount = 8) {
  const response = await axios.post(
    `/api/library/efficiency/materials/${materialId}/process`,
    { question_count: questionCount },
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function deduplicateKnowledge(folderId) {
  const response = await axios.post(
    `/api/library/efficiency/folders/${folderId}/knowledge/deduplicate`, {},
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function checkQuestionQuality(folderId) {
  const response = await axios.post(
    `/api/library/efficiency/folders/${folderId}/quality/check`, {},
    { headers: authHeaders() },
  )
  return response.data.data
}

export async function getQuestionQuality(folderId) {
  const response = await axios.get(
    `/api/library/efficiency/folders/${folderId}/quality`, { headers: authHeaders() },
  )
  return response.data.data
}

export async function getModelUsage(days = 30) {
  const response = await axios.get(
    '/api/library/efficiency/usage', { params: { days }, headers: authHeaders() },
  )
  return response.data.data
}

export async function getVideoPlayback(videoId) {
  const response = await axios.post(
    `/api/library/efficiency/videos/${videoId}/playback`, {}, { headers: authHeaders() },
  )
  return response.data.data
}

export async function gradeVoiceRecall(audioBlob, reference, question = '') {
  const form = new FormData()
  form.append('audio', audioBlob, 'recall.webm')
  form.append('reference', reference)
  form.append('question', question)
  const response = await axios.post(
    '/api/library/efficiency/voice/recall', form,
    { headers: { ...authHeaders(), 'Content-Type': 'multipart/form-data' } },
  )
  return response.data.data
}
