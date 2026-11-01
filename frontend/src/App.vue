<script setup lang="ts">
import { onMounted, ref } from "vue";

import { api, errorMessage } from "./api";
import type { AppStatus } from "./types";

import AddView from "./components/AddView.vue";
import LibraryView from "./components/LibraryView.vue";
import TodayView from "./components/TodayView.vue";

type Page = "today" | "add" | "library";

const page = ref<Page>("today");
const status = ref<AppStatus | null>(null);
const error = ref("");
const revision = ref(0);

function changed() {
  revision.value += 1;
}

function saved() {
  changed();
  page.value = "today";
}

onMounted(async () => {
  try {
    status.value = await api<AppStatus>("/status");
  } catch (err) {
    error.value = errorMessage(err);
  }
});
</script>

<template>
  <div class="app-shell">
    <header class="site-header">
      <div>
        <h1>Recall</h1>
        <p class="muted">Learn today. Remember later.</p>
      </div>

      <span class="local-badge">Personal · Local</span>
    </header>

    <nav class="navigation" aria-label="Main navigation">
      <button
        :class="{ active: page === 'today' }"
        @click="page = 'today'"
      >
        Today
      </button>

      <button
        :class="{ active: page === 'add' }"
        @click="page = 'add'"
      >
        Add learning
      </button>

      <button
        :class="{ active: page === 'library' }"
        @click="page = 'library'"
      >
        Library
      </button>
    </nav>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div
      v-if="status && !status.api_key_configured"
      class="notice"
    >
      No API key configured. You can create questions manually,
      but AI generation and evaluation need a key in
      <code>backend/.env</code>.
    </div>

    <main>
      <KeepAlive>
        <TodayView
          v-if="page === 'today'"
          :revision="revision"
          @changed="changed"
        />

        <AddView
          v-else-if="page === 'add'"
          @saved="saved"
        />

        <LibraryView
          v-else
          :revision="revision"
          @changed="changed"
        />
      </KeepAlive>
    </main>

    <footer class="site-footer">
      <span v-if="status">Model: {{ status.model }}</span>
      <span>AI feedback can be wrong. You confirm the rating.</span>
    </footer>
  </div>
</template>