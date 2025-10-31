import { createApp } from 'vue'
import './style.css'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'

// 按需引入使用的图标
import {
  HomeFilled,
  Upload,
  UploadFilled,
  Document,
  Setting,
  Delete,
  Link
} from '@element-plus/icons-vue'

const app = createApp(App)

// 只注册实际使用的图标
const icons = {
  HomeFilled,
  Upload,
  UploadFilled,
  Document,
  Setting,
  Delete,
  Link
}

for (const [key, component] of Object.entries(icons)) {
  app.component(key, component)
}

app.use(ElementPlus)
app.use(createPinia())
app.use(router)

app.mount('#app')
