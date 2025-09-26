<script setup lang="ts">
import { HomeFilled, Upload, Document, Setting } from '@element-plus/icons-vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

const menuItems = [
  { icon: HomeFilled, path: '/', tooltip: '首页' },
  { icon: Document, path: '/files', tooltip: '文件管理' },
  { icon: Upload, path: '/upload', tooltip: '上传' }
]

const activeMenu = () => {
  const path = route.path
  // 特殊处理首页
  if (path === '/') return '/'
  // 其他页面需要完全匹配路径
  return menuItems.find(item => path === item.path)?.path || path
}

// 检查是否是设置页面
const isSettingsPage = () => route.path === '/settings'
</script>

<template>
  <div class="mineru-layout">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="logo-area">
        <img src="/logo.png" alt="logo" class="logo" />
      </div>
      <nav class="nav-menu">
        <div v-for="item in menuItems" :key="item.path" class="nav-item" :class="{active: activeMenu() === item.path}" @click="router.push(item.path)" :title="item.tooltip">
          <el-icon :size="24"><component :is="item.icon" /></el-icon>
        </div>
      </nav>
      <div class="sidebar-bottom">
        <el-icon class="sidebar-icon" :class="{active: isSettingsPage()}" @click="router.push('/settings')" title="设置"><Setting /></el-icon>
        <a href="https://github.com/lpdswing/Mineru-Web" target="_blank" rel="noopener noreferrer" class="github-link" title="GitHub">
          <img src="/github-logo.svg" alt="GitHub" width="22" height="22" />
        </a>
        <div class="version-info">
          mineru-2.5.4
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="main-area">
      <template v-if="route.name === 'FilePreview'">
        <router-view />
      </template>
      <template v-else>
        <main class="content-area">
          <div :class="['content-card', { 'content-full': route.path !== '/' }]">
            <router-view />
          </div>
        </main>
      </template>
    </div>
  </div>
</template>

<style scoped>
.mineru-layout {
  display: flex;
  height: 100vh; /* 固定高度，防止被内容撑开出现滚动条 */
  overflow: hidden; /* 禁止自身滚动，让子元素独立滚动 */
  background: #f7f8fa;
  box-sizing: border-box;
}
.sidebar {
  width: 5vw;
  background: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 2px 0 8px 0 rgba(0,0,0,0.03);
  z-index: 10;
  box-sizing: border-box;
  height: 100%; /* 撑满父容器高度 */
  overflow-y: auto; /* 如果内容可能超出，允许独立滚动 */
}
.logo-area {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}
.logo {
  width: 36px;
  height: 36px;
}
.nav-menu {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 24px;
}
.nav-item {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.2s;
}
.nav-item.active, .nav-item:hover {
  background: #f0f4ff;
}
.sidebar-bottom {
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-items: center;
  margin-bottom: 24px;
}
.sidebar-icon {
  font-size: 22px;
  color: #b1b3b8;
  cursor: pointer;
  transition: color 0.2s;
}
.sidebar-icon:hover, .sidebar-icon.active {
  color: #409eff;
}
.github-link {
  margin-top: -8px;
  opacity: 0.65;
  transition: opacity 0.2s;
}
.github-link:hover {
  opacity: 1;
}
.version-info {
  text-align: center;
  font-size: 12px;
  color: #b1b3b8;
  margin-top: -12px;
  transform: scale(0.9);
}
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  box-sizing: border-box;
  height: 100vh; /* 撑满父容器高度 */
  /* overflow-y: auto; 允许主内容区独立垂直滚动 */
}
.content-area {
  flex: 1;
  /* {height: auto;} */
  width: 95vw;
  background: #f7f8fa;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 24px 0;
  box-sizing: border-box;
}
.content-card {
  width: 95vw;
  /* max-width: 1200px; */
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 4px 24px 0 rgba(0,0,0,0.04);
  padding: 20px 16px 24px 16px;
  margin: 0 24px;
  position: relative;
  transition: all 0.2s;
  box-sizing: border-box;
}
/* 非首页全屏内容区样式 */
.content-full {
  max-width: none;
  min-height: 0;
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  padding: 0;
  margin: 0;
  box-sizing: border-box;
}
@media (max-width: 900px) {
  .content-card {
    padding: 8px 2px;
    min-height: 0;
  }
}
</style>