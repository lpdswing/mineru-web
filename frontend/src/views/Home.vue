<template>
  <div class="home-root">
    <!-- Hero区域 -->
    <div class="hero-section">
      <div class="hero-badge">
        <span class="badge-dot"></span>
        <span>智能文档解析平台</span>
      </div>
      <h1 class="hero-title">
        <span class="title-gradient">MinerU</span>
      </h1>
      <p class="hero-desc">高效、精准的AI文档解析服务</p>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-section">
      <div class="stat-card" v-for="(stat, index) in statCards" :key="index">
        <div class="stat-icon" :style="{ background: stat.gradient }">
          <el-icon :size="22"><component :is="stat.icon" /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">
            {{ stat.value }}<span v-if="stat.unit" class="stat-unit">{{ stat.unit }}</span>
          </div>
          <div class="stat-label">{{ stat.label }}</div>
        </div>
      </div>
    </div>

    <!-- 快捷操作 -->
    <div class="actions-section">
      <div class="action-card" @click="$router.push('/upload')">
        <div class="action-icon primary">
          <el-icon :size="28"><Upload /></el-icon>
        </div>
        <div class="action-text">
          <span class="action-title">上传文档</span>
          <span class="action-hint">支持拖拽上传</span>
        </div>
      </div>
      <div class="action-card" @click="$router.push('/files')">
        <div class="action-icon success">
          <el-icon :size="28"><Document /></el-icon>
        </div>
        <div class="action-text">
          <span class="action-title">文件管理</span>
          <span class="action-hint">查看解析结果</span>
        </div>
      </div>
    </div>

    <!-- 支持格式 -->
    <div class="formats-section">
      <div class="formats-title">支持格式</div>
      <div class="formats-list">
        <span class="format-tag">PDF</span>
        <span class="format-tag">DOCX</span>
        <span class="format-tag">PPTX</span>
        <span class="format-tag">XLSX</span>
        <span class="format-tag">PNG</span>
        <span class="format-tag">JPG</span>
        <span class="format-tag">JPEG</span>
        <span class="format-tag">WEBP</span>
        <span class="format-tag">GIF</span>
        <span class="format-tag">BMP</span>
        <span class="format-tag">TIFF</span>
      </div>
      <div class="formats-limits">
        单个文档 ≤ 200MB · 单张图片 ≤ 10MB · 单次最多20个文件
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { Upload, Document, FolderOpened, Clock, DataLine } from '@element-plus/icons-vue'
import { useStatsStore } from '../store/stats'
import { storeToRefs } from 'pinia'

const statsStore = useStatsStore()
const { totalFiles, todayUploads, usedSpace } = storeToRefs(statsStore)

const statCards = computed(() => [
  {
    icon: FolderOpened,
    label: '文件总数',
    value: totalFiles.value,
    gradient: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)'
  },
  {
    icon: Clock,
    label: '今日上传',
    value: todayUploads.value,
    gradient: 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
  },
  {
    icon: DataLine,
    label: '已用空间',
    value: usedSpace.value,
    unit: 'MB',
    gradient: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)'
  }
])

onMounted(() => {
  statsStore.fetchStats()
})
</script>

<style scoped>
.home-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 28px;
  padding: 16px;
  max-width: 700px;
  margin: 0 auto;
}

/* Hero */
.hero-section {
  text-align: center;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  background: rgb(99 102 241 / 0.1);
  border-radius: 20px;
  font-size: 12px;
  color: var(--primary-color);
  font-weight: 500;
  margin-bottom: 12px;
}

.badge-dot {
  width: 6px;
  height: 6px;
  background: var(--primary-color);
  border-radius: 50%;
  animation: pulse 2s infinite;
}

.hero-title {
  margin: 0 0 8px;
}

.title-gradient {
  font-size: 2.5rem;
  font-weight: 800;
  background: var(--primary-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-desc {
  color: var(--text-secondary);
  font-size: 1rem;
  margin: 0;
}

/* Stats */
.stats-section {
  display: flex;
  gap: 16px;
  width: 100%;
}

.stat-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  transition: all var(--transition-normal);
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

.stat-value {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.stat-unit {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-muted);
  margin-left: 2px;
}

.stat-label {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* Actions */
.actions-section {
  display: flex;
  gap: 16px;
  width: 100%;
}

.action-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-normal);
  border: 2px solid transparent;
}

.action-card:hover {
  border-color: var(--primary-light);
  background: rgb(99 102 241 / 0.04);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.action-icon {
  width: 50px;
  height: 50px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

.action-icon.primary {
  background: var(--primary-gradient);
}

.action-icon.success {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
}

.action-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.action-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.action-hint {
  font-size: 13px;
  color: var(--text-muted);
}

/* Formats */
.formats-section {
  text-align: center;
}

.formats-title {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.formats-list {
  display: flex;
  justify-content: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.format-tag {
  padding: 3px 10px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
}

.formats-limits {
  font-size: 11px;
  color: var(--text-muted);
}

/* Responsive */
@media (max-width: 768px) {
  .home-root {
    gap: 24px;
    padding: 20px;
    justify-content: flex-start;
  }
  
  .title-gradient {
    font-size: 2.25rem;
  }
  
  .stats-section {
    flex-direction: column;
    gap: 12px;
  }
  
  .actions-section {
    flex-direction: column;
    gap: 12px;
  }
  
  .action-card {
    padding: 20px;
  }
}
</style>
