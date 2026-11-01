<script setup lang="ts">
import {
  computed,
  onActivated,
  ref,
  watch,
} from "vue";

import { api, errorMessage, formatDate } from "../api";
import type { Attempt, QueueItem, Rating } from "../types";
import FeedbackPanel from "./FeedbackPanel.vue";

const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ changed: [] }>();

const queue = ref<QueueItem[]>([]);
const selectedId = ref("");

const answer = ref("");
const assisted = ref(false);
const requestId = ref(crypto.randomUUID());

const attempt = ref<Attempt | null>(null);

const loading = ref(false);
const busy = ref(false);
const error = ref("");
const message = ref("");

const current = computed(
  () => queue.value.find((item) => item.id === selectedId.value)
    ?? null,
);

const ratings: Array<{
  value: Rating;
  title: string;
  help: string;
}> = [
  {
    value: "again",
    title: "Again",
    help: "Forgot, central error, or needed substantial help",
  },
  {
    value: "hard",
    title: "Hard",
    help: "Recalled, but with serious difficulty",
  },
  {
    value: "good",
    title: "Good",
    help: "Correct independent recall",
  },
  {
    value: "easy",
    title: "Easy",
    help: "Correct and clearly effortless",
  },
];

function selectItem(item: QueueItem) {
  if (busy.value) return;

  if (
    item.id !== selectedId.value
    && answer.value.trim()
    && !attempt.value
    && !window.confirm("Discard the current unsent answer?")
  ) {
    return;
  }

  selectedId.value = item.id;
  attempt.value = item.pending_attempt;
  answer.value = item.pending_attempt?.answer ?? "";
  assisted.value = item.pending_attempt?.assisted ?? false;
  requestId.value = crypto.randomUUID();
  error.value = "";
}

async function load() {
  if (busy.value) return;

  loading.value = true;
  error.value = "";

  try {
    const items = await api<QueueItem[]>("/queue");
    queue.value = items;

    const selected = items.find(
      (item) => item.id === selectedId.value,
    );

    if (selected) {
      if (selected.pending_attempt) {
        attempt.value = selected.pending_attempt;
        answer.value = selected.pending_attempt.answer;
        assisted.value = selected.pending_attempt.assisted;
      }
    } else if (items[0]) {
      selectedId.value = "";
      answer.value = "";
      attempt.value = null;
      selectItem(items[0]);
    } else {
      selectedId.value = "";
      answer.value = "";
      attempt.value = null;
    }
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

function answerChanged() {
  requestId.value = crypto.randomUUID();
}

async function evaluate() {
  if (!current.value || !answer.value.trim() || busy.value) return;

  busy.value = true;
  error.value = "";
  message.value = "";

  try {
    const result = await api<Attempt>(
      `/items/${current.value.id}/evaluate`,
      "POST",
      {
        request_id: requestId.value,
        answer: answer.value,
        assisted: assisted.value,
      },
    );

    attempt.value = result;

    // The backend may restore a previously evaluated pending answer.
    answer.value = result.answer;
    assisted.value = result.assisted;

    current.value.pending_attempt = result;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

async function confirmRating(rating: Rating) {
  if (!attempt.value || busy.value) return;

  busy.value = true;
  error.value = "";

  try {
    const saved = await api<Attempt>(
      `/attempts/${attempt.value.id}/confirm`,
      "POST",
      { rating },
    );

    message.value = saved.scheduled_due_at
      ? `Saved. Next review: ${formatDate(saved.scheduled_due_at)}.`
      : "Review saved.";

    selectedId.value = "";
    answer.value = "";
    attempt.value = null;

    emit("changed");
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }

  if (!error.value) await load();
}

onActivated(load);
watch(() => props.revision, load);
</script>

<template>
  <section>
    <div class="section-heading">
      <div>
        <h2>Today</h2>
        <p class="muted">
          {{ queue.length }} review{{ queue.length === 1 ? "" : "s" }}
          due now.
        </p>
      </div>

      <button
        class="secondary"
        :disabled="loading || busy"
        @click="load"
      >
        Refresh
      </button>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="message" class="success">{{ message }}</p>
    <p v-if="loading" class="muted">Loading reviews…</p>

    <div
      v-if="!loading && queue.length === 0"
      class="card empty-state"
    >
      <h3>Nothing due right now</h3>
      <p>
        Add something you learned, or return when another review is due.
      </p>
      <p class="muted">
        Early learning steps may become due after a few minutes.
        Refresh when you return.
      </p>
    </div>

    <div v-if="queue.length" class="review-layout">
      <aside class="review-list">
        <button
          v-for="item in queue"
          :key="item.id"
          :class="['queue-button', {
            selected: selectedId === item.id
          }]"
          :disabled="busy"
          @click="selectItem(item)"
        >
          <span class="muted">{{ item.topic_title }}</span>
          <span>{{ item.question }}</span>
          <small v-if="item.pending_attempt">
            Awaiting rating
          </small>
        </button>
      </aside>

      <section v-if="current" class="card">
        <p class="eyebrow">{{ current.topic_title }}</p>
        <h3 class="question">{{ current.question }}</h3>

        <form v-if="!attempt" @submit.prevent="evaluate">
          <label for="recall-answer">Explain from memory</label>

          <textarea
            id="recall-answer"
            v-model="answer"
            rows="12"
            maxlength="12000"
            placeholder="Explain what you remember, in your own words…"
            :disabled="busy"
            required
            @input="answerChanged"
          />

          <label class="checkbox-label">
            <input
              v-model="assisted"
              type="checkbox"
              :disabled="busy"
              @change="answerChanged"
            />
            I used notes, hints, or other assistance.
          </label>

          <button
            type="submit"
            :disabled="busy || !answer.trim()"
          >
            {{ busy ? "Evaluating…" : "Check my recall" }}
          </button>

          <p class="muted small">
            Your answer and reference notes are sent to the configured
            OpenAI model. An evaluation may take a little time.
          </p>
        </form>

        <template v-else>
          <FeedbackPanel :attempt="attempt" />

          <div class="rating-section">
            <h4>How was your recall?</h4>
            <p class="muted">
              Suggested: {{ attempt.suggested_rating }}.
              Confirm a rating to update the schedule.
            </p>

            <div class="rating-buttons">
              <button
                v-for="rating in ratings"
                :key="rating.value"
                :class="['secondary', {
                  recommended:
                    attempt.suggested_rating === rating.value
                }]"
                :title="rating.help"
                :disabled="busy"
                @click="confirmRating(rating.value)"
              >
                {{ rating.title }}
              </button>
            </div>

            <p class="muted small">
              Again = forgot or needed help · Hard = remembered with
              difficulty · Good = independent recall · Easy = effortless.
            </p>
          </div>
        </template>
      </section>
    </div>
  </section>
</template>