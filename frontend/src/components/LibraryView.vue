<script setup lang="ts">
import {
  computed,
  onActivated,
  ref,
  watch,
} from "vue";

import {
  api,
  errorMessage,
  formatDate,
  pointLines,
} from "../api";

import type {
  Attempt,
  ReviewItem,
  Topic,
} from "../types";

import FeedbackPanel from "./FeedbackPanel.vue";

const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ changed: [] }>();

const topics = ref<Topic[]>([]);
const search = ref("");
const selectedId = ref("");

const busy = ref(false);
const error = ref("");

const editingTopic = ref(false);
const topicTitle = ref("");
const topicNotes = ref("");

const editingItemId = ref("");
const itemQuestion = ref("");
const itemPoints = ref("");

const historyItemId = ref("");
const attempts = ref<Attempt[]>([]);

function normalizeSearch(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

const filtered = computed(() => {
  const terms = normalizeSearch(search.value)
    .split(/\s+/)
    .filter(Boolean);

  if (!terms.length) {
    return topics.value;
  }

  return topics.value.filter((topic) => {
    const searchableText = normalizeSearch([
      topic.title,
      topic.notes,
      ...topic.items.flatMap((item) => [
        item.question,
        ...item.expected_points,
      ]),
    ].join(" "));

    return terms.every((term) => searchableText.includes(term));
  });
});

const selected = computed(
  () => filtered.value.find(
    (topic) => topic.id === selectedId.value,
  ) ?? null,
);

function clearSelection() {
  selectedId.value = "";
  editingTopic.value = false;
  editingItemId.value = "";
  historyItemId.value = "";
  attempts.value = [];
}

function selectTopic(topic: Topic) {
  selectedId.value = topic.id;
  editingTopic.value = false;
  editingItemId.value = "";
  historyItemId.value = "";
  attempts.value = [];
}

watch(filtered, (matches) => {
  if (matches.some((topic) => topic.id === selectedId.value)) {
    return;
  }

  const firstMatch = matches[0];

  if (firstMatch) {
    selectTopic(firstMatch);
    return;
  }

  clearSelection();
});

async function load() {
  if (busy.value) return;

  error.value = "";

  try {
    topics.value = await api<Topic[]>("/topics");

    const selectedStillExists = topics.value.some(
      (topic) => topic.id === selectedId.value,
    );

    if (!selectedStillExists) {
      const firstTopic = topics.value[0];

      if (firstTopic) {
        selectTopic(firstTopic);
      } else {
        clearSelection();
      }
    }
  } catch (err) {
    error.value = errorMessage(err);
  }
}

async function runMutation(action: () => Promise<unknown>) {
  if (busy.value) return;

  busy.value = true;
  error.value = "";

  try {
    await action();

    editingTopic.value = false;
    editingItemId.value = "";
    historyItemId.value = "";
    attempts.value = [];

    emit("changed");
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }

  if (!error.value) {
    await load();
  }
}

function startTopicEdit() {
  if (!selected.value) return;

  topicTitle.value = selected.value.title;
  topicNotes.value = selected.value.notes;
  editingTopic.value = true;
}

async function saveTopic() {
  if (!selected.value) return;

  const notesChanged = topicNotes.value !== selected.value.notes;

  if (
    notesChanged
    && !window.confirm(
      "Changing reference notes resets this topic's review schedules "
      + "and invalidates pending evaluations. "
      + "Existing questions and expected points are NOT regenerated. "
      + "Check them manually after editing. Continue?",
    )
  ) {
    return;
  }

  const topicId = selected.value.id;

  await runMutation(() => api(
    `/topics/${topicId}`,
    "PUT",
    {
      title: topicTitle.value,
      notes: topicNotes.value,
    },
  ));
}

function startItemEdit(item: ReviewItem) {
  editingItemId.value = item.id;
  itemQuestion.value = item.question;
  itemPoints.value = item.expected_points.join("\n");
}

async function saveItem(item: ReviewItem) {
  if (
    !window.confirm(
      "Save changes and restart this item's review schedule? "
      + "Its previous history will be preserved.",
    )
  ) {
    return;
  }

  await runMutation(() => api(
    `/items/${item.id}`,
    "PUT",
    {
      question: itemQuestion.value,
      expected_points: pointLines(itemPoints.value),
    },
  ));
}

async function togglePause(item: ReviewItem) {
  await runMutation(() => api(
    `/items/${item.id}/pause`,
    "PATCH",
    {
      paused: !item.paused,
    },
  ));
}

async function deleteItem(item: ReviewItem) {
  if (
    !window.confirm(
      "Delete this question and all of its review attempts?",
    )
  ) {
    return;
  }

  await runMutation(() => api(
    `/items/${item.id}`,
    "DELETE",
  ));
}

async function deleteTopic() {
  if (!selected.value) return;

  const topicTitleToDelete = selected.value.title;
  const topicId = selected.value.id;

  if (
    !window.confirm(
      `Delete "${topicTitleToDelete}", its questions, and all history?`,
    )
  ) {
    return;
  }

  await runMutation(() => api(
    `/topics/${topicId}`,
    "DELETE",
  ));
}

async function showHistory(item: ReviewItem) {
  if (historyItemId.value === item.id) {
    historyItemId.value = "";
    attempts.value = [];
    return;
  }

  busy.value = true;
  error.value = "";

  try {
    attempts.value = await api<Attempt[]>(
      `/items/${item.id}/history`,
    );

    historyItemId.value = item.id;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

onActivated(load);
watch(() => props.revision, load);
</script>

<template>
  <section>
    <div class="section-heading">
      <div>
        <h2>Library</h2>
        <p class="muted">Your notes, questions, and recall history.</p>
      </div>

      <a
        href="/api/export"
        target="_blank"
        rel="noopener"
        class="small"
      >
        Open JSON export
      </a>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <label for="library-search">Search</label>
    <input
      id="library-search"
      v-model="search"
      placeholder="Search topics, notes, or questions"
    />

    <div v-if="!topics.length" class="card empty-state">
      No learning saved yet.
    </div>

    <div v-else class="review-layout">
      <aside class="review-list">
        <button
          v-for="topic in filtered"
          :key="topic.id"
          :class="[
            'queue-button',
            { selected: selectedId === topic.id },
          ]"
          :disabled="busy"
          @click="selectTopic(topic)"
        >
          <span>{{ topic.title }}</span>
          <small>{{ topic.items.length }} questions</small>
        </button>

        <p v-if="!filtered.length" class="muted">
          No matching topics.
        </p>
      </aside>

      <section v-if="selected">
        <div class="card">
          <div class="section-heading">
            <h3>{{ selected.title }}</h3>

            <div class="actions">
              <button
                class="text-button"
                :disabled="busy"
                @click="startTopicEdit"
              >
                Edit notes
              </button>

              <button
                class="text-button danger"
                :disabled="busy"
                @click="deleteTopic"
              >
                Delete topic
              </button>
            </div>
          </div>

          <form
            v-if="editingTopic"
            @submit.prevent="saveTopic"
          >
            <fieldset :disabled="busy">
              <label for="edit-title">Topic title</label>
              <input
                id="edit-title"
                v-model="topicTitle"
                minlength="2"
                maxlength="160"
                required
              />

              <label for="edit-notes">Reference notes</label>
              <textarea
                id="edit-notes"
                v-model="topicNotes"
                rows="12"
                minlength="20"
                maxlength="20000"
                required
              />

              <p class="muted small">
                Changing notes resets schedules. Questions and expected
                points remain unchanged—review them after saving.
              </p>

              <div class="actions">
                <button type="submit">Save notes</button>

                <button
                  type="button"
                  class="secondary"
                  @click="editingTopic = false"
                >
                  Cancel
                </button>
              </div>
            </fieldset>
          </form>

          <details v-else>
            <summary>Reference notes</summary>
            <pre class="reference">{{ selected.notes }}</pre>
          </details>
        </div>

        <p v-if="!selected.items.length" class="muted">
          This topic has no review questions.
        </p>

        <article
          v-for="item in selected.items"
          :key="item.id"
          class="card"
        >
          <template v-if="editingItemId === item.id">
            <form @submit.prevent="saveItem(item)">
              <fieldset :disabled="busy">
                <label :for="`edit-question-${item.id}`">
                  Question
                </label>

                <textarea
                  :id="`edit-question-${item.id}`"
                  v-model="itemQuestion"
                  rows="3"
                  minlength="5"
                  maxlength="1500"
                  required
                />

                <label :for="`edit-points-${item.id}`">
                  Expected points, one per line
                </label>

                <textarea
                  :id="`edit-points-${item.id}`"
                  v-model="itemPoints"
                  rows="6"
                  required
                />

                <div class="actions">
                  <button type="submit">Save question</button>

                  <button
                    type="button"
                    class="secondary"
                    @click="editingItemId = ''"
                  >
                    Cancel
                  </button>
                </div>
              </fieldset>
            </form>
          </template>

          <template v-else>
            <h3>{{ item.question }}</h3>

            <p class="muted small">
              {{ item.paused ? "Paused" : "Next review" }}:
              {{ formatDate(item.due_at) }}
            </p>

            <details>
              <summary>Expected key points</summary>
              <ul>
                <li
                  v-for="(point, index) in item.expected_points"
                  :key="index"
                >
                  {{ point }}
                </li>
              </ul>
            </details>

            <div class="actions item-actions">
              <button
                class="secondary"
                :disabled="busy"
                @click="showHistory(item)"
              >
                {{ historyItemId === item.id
                  ? "Hide history"
                  : "History" }}
              </button>

              <button
                class="secondary"
                :disabled="busy"
                @click="startItemEdit(item)"
              >
                Edit
              </button>

              <button
                class="secondary"
                :disabled="busy"
                @click="togglePause(item)"
              >
                {{ item.paused ? "Resume" : "Pause" }}
              </button>

              <button
                class="text-button danger"
                :disabled="busy"
                @click="deleteItem(item)"
              >
                Delete
              </button>
            </div>

            <section
              v-if="historyItemId === item.id"
              class="history"
            >
              <p v-if="!attempts.length" class="muted">
                No recall attempts yet.
              </p>

              <details
                v-for="pastAttempt in attempts"
                :key="pastAttempt.id"
                class="history-entry"
              >
                <summary>
                  {{ formatDate(pastAttempt.attempted_at) }}
                  ·
                  {{ pastAttempt.confirmed_rating ?? "Not scheduled" }}
                </summary>

                <p class="muted small">
                  Question at the time: {{ pastAttempt.question }}
                </p>

                <FeedbackPanel :attempt="pastAttempt" />

                <p class="muted small">
                  {{ pastAttempt.model }}
                  · {{ pastAttempt.input_tokens }} input tokens
                  · {{ pastAttempt.output_tokens }} output tokens
                </p>
              </details>
            </section>
          </template>
        </article>
      </section>
    </div>
  </section>
</template>