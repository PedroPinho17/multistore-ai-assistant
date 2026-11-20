<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const { toasts, t } = storeToRefs(ui)

const liveMsg = ref('')
const liveMode = ref<'polite' | 'assertive'>('polite')
let seenIds = new Set<number>()

watch(
  toasts,
  list => {
    const fresh = list.filter(x => !seenIds.has(x.id))
    seenIds = new Set(list.map(x => x.id))
    const latest = fresh[fresh.length - 1]
    if (!latest) return
    liveMode.value = latest.type === 'error' ? 'assertive' : 'polite'
    liveMsg.value = ''
    void nextTick(() => {
      liveMsg.value = latest.text
    })
  },
  { deep: true },
)
</script>

<template>
  <div class="sr-only" :aria-live="liveMode" aria-atomic="true">{{ liveMsg }}</div>
  <div class="toasts">
    <TransitionGroup name="toast">
      <div
        v-for="x in toasts"
        :key="x.id"
        class="toast"
        :class="x.type || 'ok'"
        aria-hidden="true"
      >
        <span class="toast-dot" aria-hidden="true">{{ x.type === 'error' ? '!' : '✓' }}</span>
        <span class="toast-text">{{ x.text }}</span>
        <button
          type="button"
          class="toast-x"
          :aria-label="t.dlg.close"
          tabindex="-1"
          @click="ui.dismissToast(x.id)"
        >
          ×
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
