import api from './index'

export interface CurrentUser {
  id: number
  email: string
  created_at?: string | null
}

export interface AuthPayload {
  email: string
  password: string
}

export interface AuthResponse {
  user: CurrentUser
}

export const authApi = {
  register(payload: AuthPayload) {
    return api.post<AuthResponse>('/auth/register', payload).then(res => res.data)
  },

  login(payload: AuthPayload) {
    return api.post<AuthResponse>('/auth/login', payload).then(res => res.data)
  },

  logout() {
    return api.post('/auth/logout').then(res => res.data)
  },

  me() {
    return api.get<CurrentUser>('/auth/me').then(res => res.data)
  }
}
