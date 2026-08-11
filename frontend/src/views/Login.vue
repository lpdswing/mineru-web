<template>
  <main class="auth-page">
    <button
      class="appearance-toggle"
      type="button"
      :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
      :title="isDark ? '浅色模式' : '深色模式'"
      @click="toggleTheme"
    >
      <el-icon><Sunny v-if="isDark" /><Moon v-else /></el-icon>
    </button>
    <section class="auth-panel">
      <div class="brand-block">
        <img src="/logo.png" alt="MinerU" class="brand-logo" />
        <div>
          <p class="brand-kicker">MinerU</p>
          <h1>{{ isRegisterMode ? '创建账户' : '欢迎回来' }}</h1>
        </div>
      </div>

      <el-form class="auth-form" @submit.prevent="submit">
        <el-form-item>
          <el-input
            v-model="email"
            type="email"
            size="large"
            placeholder="邮箱"
            autocomplete="email"
          >
            <template #prefix>
              <el-icon><Message /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item>
          <el-input
            v-model="password"
            type="password"
            size="large"
            placeholder="密码"
            autocomplete="current-password"
            show-password
            @keyup.enter="submit"
          >
            <template #prefix>
              <el-icon><Lock /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-button
          class="submit-button"
          type="primary"
          size="large"
          :loading="submitting"
          @click="submit"
        >
          {{ isRegisterMode ? '注册并进入' : '登录' }}
        </el-button>
      </el-form>

      <button class="mode-toggle" type="button" @click="toggleMode">
        {{ isRegisterMode ? '已有账户，去登录' : '还没有账户，创建一个' }}
      </button>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, Message, Moon, Sunny } from '@element-plus/icons-vue'
import { loginWithEmail, registerWithEmail } from '@/utils/user'
import { useTheme } from '@/utils/theme'

const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const mode = ref<'login' | 'register'>('login')
const submitting = ref(false)
const isRegisterMode = computed(() => mode.value === 'register')
const { isDark, toggleTheme } = useTheme()

const toggleMode = () => {
  mode.value = isRegisterMode.value ? 'login' : 'register'
}

const submit = async () => {
  if (submitting.value) return
  const trimmedEmail = email.value.trim()
  if (!trimmedEmail || !password.value) {
    ElMessage.warning('请输入邮箱和密码')
    return
  }
  if (password.value.length < 6) {
    ElMessage.warning('密码至少需要 6 位')
    return
  }

  submitting.value = true
  try {
    if (isRegisterMode.value) {
      await registerWithEmail({ email: trimmedEmail, password: password.value })
      ElMessage.success('账户已创建')
    } else {
      await loginWithEmail({ email: trimmedEmail, password: password.value })
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.replace(redirect)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.auth-page {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(circle at 50% 0%, var(--auth-glow), transparent 34%),
    var(--bg-secondary);
}

.auth-panel {
  width: min(100%, 420px);
  background: color-mix(in srgb, var(--bg-primary) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color) 70%, transparent);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  padding: 32px;
  backdrop-filter: blur(18px);
}

.appearance-toggle {
  position: absolute;
  top: 24px;
  right: 24px;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 1px solid var(--border-color);
  border-radius: 50%;
  background: var(--bg-primary);
  color: var(--text-secondary);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: color var(--transition-fast), border-color var(--transition-fast), background var(--transition-fast);
}

.appearance-toggle:hover {
  border-color: var(--primary-light);
  background: var(--bg-hover);
  color: var(--primary-color);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 28px;
}

.brand-logo {
  width: 48px;
  height: 48px;
}

.brand-kicker {
  margin: 0 0 4px;
  font-size: 13px;
  color: var(--primary-color);
  font-weight: 600;
}

h1 {
  margin: 0;
  font-size: 28px;
  color: var(--text-primary);
  font-weight: 700;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.submit-button {
  width: 100%;
  margin-top: 8px;
}

.mode-toggle {
  width: 100%;
  margin-top: 18px;
  border: none;
  background: transparent;
  color: var(--primary-color);
  font-size: 14px;
  cursor: pointer;
  padding: 8px;
}

.mode-toggle:hover {
  color: var(--primary-hover);
}

@media (max-width: 520px) {
  .auth-panel {
    padding: 24px;
  }

  h1 {
    font-size: 24px;
  }
}
</style>
