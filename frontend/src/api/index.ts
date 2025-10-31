import axios from 'axios'
import type { AxiosInstance, AxiosError } from 'axios'
import { ElMessage } from 'element-plus'
import { getUserId } from '@/utils/user'

// 创建 axios 实例
const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000, // 30秒超时（考虑到文件解析可能需要较长时间）
})

// 请求拦截器：自动添加用户ID
api.interceptors.request.use(
  (config) => {
    // 自动添加用户ID到请求头
    if (!config.headers['X-User-Id']) {
      config.headers['X-User-Id'] = getUserId()
    }
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器：统一错误处理
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error: AxiosError<any>) => {
    // 统一错误处理
    const errorMessage = getErrorMessage(error)
    ElMessage.error(errorMessage)
    return Promise.reject(error)
  }
)

// 错误消息映射
function getErrorMessage(error: AxiosError<any>): string {
  if (!error.response) {
    if (error.code === 'ECONNABORTED') {
      return '请求超时，请稍后重试'
    }
    return '网络连接失败，请检查网络后重试'
  }

  const status = error.response.status
  const detail = error.response.data?.detail

  // 优先使用后端返回的详细错误信息
  if (detail) {
    return typeof detail === 'string' ? detail : JSON.stringify(detail)
  }

  // 根据状态码返回友好提示
  const statusMessages: Record<number, string> = {
    400: '请求参数错误',
    401: '未授权，请重新登录',
    403: '没有权限访问',
    404: '请求的资源不存在',
    500: '服务器错误，请稍后重试',
    502: '网关错误，请稍后重试',
    503: '服务暂时不可用，请稍后重试',
  }

  return statusMessages[status] || `请求失败 (${status})`
}

export default api
