<script setup>
import { store, dismissToast } from '../store'
</script>

<template>
  <div class="toast-host">
    <div
      v-for="t in store.toasts"
      :key="t.id"
      class="toast"
      :class="t.type"
      @click="dismissToast(t.id)"
    >
      {{ t.message }}
    </div>
  </div>
</template>
