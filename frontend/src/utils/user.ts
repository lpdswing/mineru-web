import { ref } from 'vue'
import { authApi, type AuthPayload, type CurrentUser } from '@/api/auth'

const currentUser = ref<CurrentUser | null>(null)
let currentUserLoaded = false

export function useCurrentUser() {
  return currentUser
}

export function getCurrentUser() {
  return currentUser.value
}

export function clearCurrentUser() {
  currentUser.value = null
  currentUserLoaded = true
}

export async function fetchCurrentUser() {
  const user = await authApi.me()
  currentUser.value = user
  currentUserLoaded = true
  return user
}

export async function ensureCurrentUser() {
  if (currentUserLoaded && currentUser.value) {
    return currentUser.value
  }
  return fetchCurrentUser()
}

export async function loginWithEmail(payload: AuthPayload) {
  const result = await authApi.login(payload)
  currentUser.value = result.user
  currentUserLoaded = true
  return result.user
}

export async function registerWithEmail(payload: AuthPayload) {
  const result = await authApi.register(payload)
  currentUser.value = result.user
  currentUserLoaded = true
  return result.user
}

export async function logoutUser() {
  try {
    await authApi.logout()
  } finally {
    clearCurrentUser()
  }
}
