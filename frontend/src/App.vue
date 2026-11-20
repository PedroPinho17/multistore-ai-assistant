<script setup lang="ts">
import IconSprite from '@/components/IconSprite.vue'
import ToastStack from '@/components/ToastStack.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
</script>

<template>
  <IconSprite />
  <RouterView />
  <ConfirmDialog />
  <ToastStack />
</template>
