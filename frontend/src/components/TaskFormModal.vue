<script setup>
import { ref, watch } from 'vue'
import { api } from '../api'
import { toast, errorText } from '../store'

const props = defineProps({
  task: { type: Object, default: null }
})
const emit = defineEmits(['close', 'saved'])

const saving = ref(false)
const form = ref(blank())

function blank() {
  return {
    name: '',
    enabled: true,
    target_type: 'bot',
    bot_username: '',
    group_id: '',
    action_type: 'message',
    message: '',
    button_type: 'text',
    button_text: '',
    callback_data: '',
    start_command: ''
  }
}

watch(
  () => props.task,
  (task) => {
    form.value = task ? { ...blank(), ...task, name: task.name || '' } : blank()
  },
  { immediate: true }
)

const EDITABLE_FIELDS = [
  'name',
  'enabled',
  'target_type',
  'bot_username',
  'group_id',
  'action_type',
  'message',
  'button_type',
  'button_text',
  'callback_data',
  'start_command'
]

async function submit() {
  saving.value = true
  try {
    const payload = { name: '', enabled: true, start_command: '' }
    EDITABLE_FIELDS.forEach((key) => {
      payload[key] = form.value[key] === '' ? null : form.value[key]
    })
    payload.name = (form.value.name || '').trim()

    if (payload.target_type === 'bot') payload.group_id = null
    else payload.bot_username = null
    if (payload.action_type === 'message') {
      payload.button_type = null
      payload.button_text = null
      payload.callback_data = null
    } else {
      payload.message = null
      if (payload.button_type === 'text') payload.callback_data = null
      else payload.button_text = null
    }

    if (props.task) await api.updateTask(props.task.id, payload)
    else await api.createTask(payload)

    toast(props.task ? '任务已保存' : '任务已创建', 'success')
    emit('saved')
  } catch (err) {
    toast(errorText(err), 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h3>{{ task ? '编辑任务' : '新建签到任务' }}</h3>
        <button class="btn btn-ghost btn-sm" @click="emit('close')">✕</button>
      </div>

      <form class="modal-body" @submit.prevent="submit">
        <div class="field">
          <label class="label">任务备注</label>
          <input v-model="form.name" class="input" placeholder="例如：社工库签到" />
        </div>

        <div class="field">
          <label class="label">目标类型</label>
          <div class="seg">
            <button type="button" :class="{ active: form.target_type === 'bot' }" @click="form.target_type = 'bot'">
              机器人
            </button>
            <button type="button" :class="{ active: form.target_type === 'group' }" @click="form.target_type = 'group'">
              群组 / 频道
            </button>
          </div>
        </div>

        <div v-if="form.target_type === 'bot'" class="field">
          <label class="label">机器人用户名</label>
          <input v-model="form.bot_username" class="input" placeholder="@example_bot" />
          <div class="hint">带不带 @ 都可以，保存时会自动补上。</div>
        </div>
        <div v-else class="field">
          <label class="label">群组 ID</label>
          <input v-model="form.group_id" class="input" placeholder="-1001234567890 或 @groupname" />
        </div>

        <div v-if="form.target_type === 'bot'" class="field">
          <label class="label">启动命令（可选）</label>
          <input v-model="form.start_command" class="input" placeholder="/start" />
          <div class="hint">执行签到前先发送该命令，常用于唤醒机器人菜单。</div>
        </div>

        <div class="field">
          <label class="label">执行动作</label>
          <div class="seg">
            <button
              type="button"
              :class="{ active: form.action_type === 'message' }"
              :disabled="form.target_type === 'group'"
              @click="form.action_type = 'message'"
            >
              发送消息
            </button>
            <button
              type="button"
              :class="{ active: form.action_type === 'button' }"
              :disabled="form.target_type === 'group'"
              @click="form.action_type = 'button'"
            >
              点击按钮
            </button>
          </div>
          <div v-if="form.target_type === 'group'" class="hint">群组任务仅支持「发送消息」。</div>
        </div>

        <div v-if="form.action_type === 'message'" class="field">
          <label class="label">消息内容</label>
          <input v-model="form.message" class="input" placeholder="/sign 或 签到" />
        </div>

        <template v-else>
          <div class="field">
            <label class="label">按钮匹配方式</label>
            <div class="seg">
              <button type="button" :class="{ active: form.button_type === 'text' }" @click="form.button_type = 'text'">
                按按钮文字
              </button>
              <button
                type="button"
                :class="{ active: form.button_type === 'callback' }"
                @click="form.button_type = 'callback'"
              >
                按回调数据
              </button>
            </div>
          </div>
          <div v-if="form.button_type === 'text'" class="field">
            <label class="label">按钮文字</label>
            <input v-model="form.button_text" class="input" placeholder="✅ 签到" />
          </div>
          <div v-else class="field">
            <label class="label">回调数据</label>
            <input v-model="form.callback_data" class="input mono" placeholder="checkin" />
            <div class="hint">机器人内联按钮的 callback_data，可用 Bot 的 raw 数据查看。</div>
          </div>
        </template>

        <div class="switch-row">
          <div>
            <div style="font-weight: 600">启用该任务</div>
            <div class="hint">关闭后定时签到会跳过它。</div>
          </div>
          <label class="switch">
            <input v-model="form.enabled" type="checkbox" />
            <span class="slider"></span>
          </label>
        </div>

        <div class="modal-footer" style="padding: 0; border: none; margin-top: 18px">
          <button type="button" class="btn" @click="emit('close')">取消</button>
          <button type="submit" class="btn btn-primary" :disabled="saving">
            <span v-if="saving" class="spinner"></span>
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
