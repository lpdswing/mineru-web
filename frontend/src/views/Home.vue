<template>
  <div class="home-root">
    <div class="home-header">
      <h1 class="home-title">MinerU 2.0 免费全能的文档解析神器！</h1>
      <p class="home-desc">点击或拖拽上传文档<br>支持格式：PDF、PNG、JPG、JPEG、JP2、WEBP、GIF、BMP、TIFF<br>单个文档不超过 <b>200M</b> 或 <b>600</b> 页，单图片不超过 <b>10M</b>，单次上传最多 <b>20</b> 个文件</p>
    </div>
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">文件总数</div>
        <div class="stat-value">{{ stats.totalFiles }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">今日上传</div>
        <div class="stat-value">{{ stats.todayUploads }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已用空间</div>
        <div class="stat-value">{{ stats.usedSpace }}<span class="unit">MB</span></div>
      </div>
    </div>
    <div class="quick-row">
      <el-button class="quick-btn" type="primary" size="large" @click="$router.push('/upload')">
        <el-icon><Upload /></el-icon> 上传文档
      </el-button>
      <el-button class="quick-btn" type="success" size="large" @click="$router.push('/files')">
        <el-icon><Document /></el-icon> 文件管理
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { Upload, Document } from '@element-plus/icons-vue'
import { useStatsStore } from '../store/stats'
import { storeToRefs } from 'pinia'

const statsStore = useStatsStore()
const stats = storeToRefs(statsStore)



onMounted(() => {
  statsStore.fetchStats()
})
</script>

<style scoped>
.home-root {
  max-width: 700px;
  margin: 0 auto;
  padding: 32px 0 0 0;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  min-height: 85vh;
  height: auto;
}

.home-header {
  text-align: center;
  margin-bottom: 32px;
}

.home-title {
  font-size: 2.1rem;
  font-weight: 700;
  margin-bottom: 8px;
  color: #222;
}

.home-desc {
  color: #888;
  font-size: 1.1rem;
  margin-bottom: 0;
}

.stat-row {
  display: flex;
  gap: 24px;
  margin-bottom: 32px;
  width: 100%;
  justify-content: center;
}

.stat-card {
  flex: 1;
  min-width: 120px;
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  padding: 28px 0 18px 0;
  text-align: center;
  transition: box-shadow 0.2s;
}

.stat-card:hover {
  box-shadow: 0 4px 24px 0 rgba(64,158,255,0.08);
}

.stat-label {
  color: #888;
  font-size: 1rem;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 2.2rem;
  font-weight: 600;
  color: #222;
}

.unit {
  font-size: 1rem;
  color: #888;
  margin-left: 2px;
}

.quick-row {
  display: flex;
  gap: 24px;
  margin-bottom: 36px;
  width: 100%;
  justify-content: center;
}

.quick-btn {
  min-width: 140px;
  font-size: 1.1rem;
  border-radius: 0;
  box-shadow: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.recent-card {
  width: 100%;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 2px 12px 0 rgba(0,0,0,0.04);
  padding: 24px 24px 12px 24px;
  margin-top: 8px;
}

.recent-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 1.1rem;
  font-weight: 500;
  margin-bottom: 12px;
}

:deep(.el-table) {
  border-radius: 12px;
  overflow: hidden;
}

:deep(.el-empty) {
  margin: 32px 0;
}

@media (max-width: 768px) {
  .home-root {
    padding: 24px 16px 0 16px;
  }
  .stat-row {
    flex-direction: column;
  }
  
  .quick-row {
    flex-direction: column;
  }
  
  .quick-btn {
    width: 100%;
  }
}
</style> 