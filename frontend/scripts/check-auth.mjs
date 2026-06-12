import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const files = {
  user: fs.readFileSync(path.join(root, 'src/utils/user.ts'), 'utf8'),
  api: fs.readFileSync(path.join(root, 'src/api/index.ts'), 'utf8'),
}

const failures = []

if (files.user.includes('mineru_user_id')) {
  failures.push('src/utils/user.ts still uses the legacy mineru_user_id key.')
}

if (files.user.includes('uuidv4')) {
  failures.push('src/utils/user.ts still generates random browser user ids.')
}

if (files.user.includes('localStorage.setItem')) {
  failures.push('src/utils/user.ts still writes user identity to localStorage.')
}

if (files.api.includes('X-User-Id')) {
  failures.push('src/api/index.ts still sends the legacy X-User-Id header.')
}

if (!files.api.includes('withCredentials: true')) {
  failures.push('src/api/index.ts must send auth cookies with API requests.')
}

if (failures.length > 0) {
  console.error(failures.join('\n'))
  process.exit(1)
}

console.log('Auth client no longer relies on browser-generated user ids.')
