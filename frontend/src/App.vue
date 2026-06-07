<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRobotStore } from '@/stores/robot'

const robotStore = useRobotStore()

onMounted(() => {
  robotStore.initWebSocket()
})
</script>
