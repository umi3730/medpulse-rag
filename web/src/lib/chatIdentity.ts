export interface ChatIdentity {
  user_id: string
  session_id: string
}

const USER_STORAGE_KEY = 'medical_graphrag_user_id'
const SESSION_STORAGE_KEY = 'medical_graphrag_session_id'

let memoryUserId = ''
let memorySessionId = ''

function createId(prefix: 'usr' | 'ses') {
  const randomPart = globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID().replaceAll('-', '')
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
  return `${prefix}_${randomPart}`
}

function readOrCreate(
  storage: Storage,
  key: string,
  prefix: 'usr' | 'ses',
  fallback: () => string,
) {
  try {
    const existing = storage.getItem(key)
    if (existing) return existing
    const created = createId(prefix)
    storage.setItem(key, created)
    return created
  } catch {
    return fallback()
  }
}

export function getChatIdentity(): ChatIdentity {
  const userId = readOrCreate(localStorage, USER_STORAGE_KEY, 'usr', () => {
    memoryUserId ||= createId('usr')
    return memoryUserId
  })
  const sessionId = readOrCreate(sessionStorage, SESSION_STORAGE_KEY, 'ses', () => {
    memorySessionId ||= createId('ses')
    return memorySessionId
  })
  return { user_id: userId, session_id: sessionId }
}

export function startNewChatSession(): ChatIdentity {
  const userId = getChatIdentity().user_id
  const sessionId = createId('ses')
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId)
  } catch {
    memorySessionId = sessionId
  }
  return { user_id: userId, session_id: sessionId }
}

export function activateChatSession(sessionId: string): ChatIdentity {
  const userId = getChatIdentity().user_id
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId)
  } catch {
    memorySessionId = sessionId
  }
  return { user_id: userId, session_id: sessionId }
}
