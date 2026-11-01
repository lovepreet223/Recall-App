<script setup lang="ts">
import { computed, ref } from "vue";

import {
  api,
  errorMessage,
  pointLines,
} from "../api";

import type {
  GeneratedItemsWithOverlap,
  ItemDraft,
  OverlapCheck,
  Topic,
} from "../types";

interface EditableDraft {
  key: string;
  question: string;
  pointsText: string;
  overlap: OverlapCheck | null;
  discarded: boolean;
}

interface WebSource {
  title: string | null;
  url: string;
}

interface ReferenceDraftResponse {
  reference_notes: string;
  sources: WebSource[];
}

const emit = defineEmits<{ saved: [] }>();

const title = ref("");
const roughNotes = ref("");
const notes = ref("");
const useWebSearch = ref(false);
const sources = ref<WebSource[]>([]);
const drafts = ref<EditableDraft[]>([]);

const generatingReference = ref(false);
const generatingQuestions = ref(false);
const error = ref("");

const busy = computed(
  () => generatingReference.value || generatingQuestions.value,
);

const canGenerateReference = computed(
  () => title.value.trim().length >= 2
    && roughNotes.value.trim().length >= 3,
);

const canGenerateQuestions = computed(
  () => title.value.trim().length >= 2
    && notes.value.trim().length >= 20,
);

const activeDrafts = computed(() =>
  drafts.value.filter((draft) => !draft.discarded),
);

function addManual() {
  if (drafts.value.length >= 10) return;

  drafts.value.push({
    key: crypto.randomUUID(),
    question: "",
    pointsText: "",
    overlap: null,
    discarded: false,
  });
}

function removeDraft(index: number) {
  drafts.value.splice(index, 1);
}

function discardProposal(draft: EditableDraft) {
  draft.discarded = true;
}

function restoreProposal(draft: EditableDraft) {
  draft.discarded = false;
}

function applySuggestedRevision(draft: EditableDraft) {
  if (draft.overlap?.suggested_revision) {
    draft.question = draft.overlap.suggested_revision;
    draft.overlap = null;
  }
}

function overlapClass(overlap: OverlapCheck | null): string {
  if (!overlap) return "";

  if (overlap.overlap === "near_duplicate") {
    return "overlap-danger";
  }

  if (overlap.overlap === "related") {
    return "overlap-warning";
  }

  return "overlap-ok";
}

async function generateReference() {
  if (generatingReference.value || !canGenerateReference.value) return;

  if (
    notes.value.trim()
    && !window.confirm(
      "Replace the current reference notes with an AI-generated draft?",
    )
  ) {
    return;
  }

  generatingReference.value = true;
  error.value = "";

  try {
    const result = await api<ReferenceDraftResponse>(
      "/generate-reference",
      "POST",
      {
        title: title.value,
        rough_notes: roughNotes.value,
        use_web_search: useWebSearch.value,
      },
    );

    notes.value = result.reference_notes;
    sources.value = result.sources ?? [];
    drafts.value = [];
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    generatingReference.value = false;
  }
}

async function generateQuestions() {
  if (generatingQuestions.value || !canGenerateQuestions.value) return;

  if (
    drafts.value.length
    && !window.confirm(
      "Replace the current draft questions with newly generated ones?",
    )
  ) {
    return;
  }

  generatingQuestions.value = true;
  error.value = "";

  try {
    const result = await api<GeneratedItemsWithOverlap>(
      "/generate",
      "POST",
      {
        title: title.value,
        notes: notes.value,
      },
    );

    drafts.value = result.items.map((item, index) => ({
      key: crypto.randomUUID(),
      question: item.question,
      pointsText: item.expected_points.join("\n"),
      overlap: result.overlap_checks[index] ?? null,
      discarded:
        result.overlap_checks[index]?.recommendation === "discard",
    }));
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    generatingQuestions.value = false;
  }
}

async function save() {
  if (busy.value) return;

  error.value = "";

  if (!canGenerateQuestions.value) {
    error.value = "Enter a topic and at least 20 characters of notes.";
    return;
  }

  if (!activeDrafts.value.length) {
    error.value = "Keep at least one review question.";
    return;
  }

  const items: ItemDraft[] = activeDrafts.value.map((draft) => ({
    question: draft.question.trim(),
    expected_points: pointLines(draft.pointsText),
  }));

  if (
    items.some(
      (item) => item.question.length < 5
        || !item.expected_points.length
        || item.expected_points.length > 8,
    )
  ) {
    error.value =
      "Each kept question needs at least 5 characters and "
      + "1–8 expected points.";
    return;
  }

  generatingQuestions.value = true;

  try {
    await api<Topic>("/topics", "POST", {
      title: title.value,
      notes: notes.value,
      items,
    });

    title.value = "";
    roughNotes.value = "";
    notes.value = "";
    useWebSearch.value = false;
    sources.value = [];
    drafts.value = [];

    emit("saved");
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    generatingQuestions.value = false;
  }
}
</script>

<template>
  <section>
    <h2>Add learning</h2>
    <p class="muted">
      Write your own reference notes, or optionally generate an editable
      AI draft first.
    </p>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <form @submit.prevent="save">
      <fieldset :disabled="busy">
        <div class="card">
          <label for="topic-title">Topic</label>
          <input
            id="topic-title"
            v-model="title"
            maxlength="160"
            minlength="2"
            placeholder="For example: TCP/IP and packet transfer"
            required
          />

          <label for="topic-notes">
            What I learned / reference notes
          </label>
          <textarea
            id="topic-notes"
            v-model="notes"
            rows="14"
            minlength="20"
            maxlength="20000"
            placeholder="Write the definitions, explanations, assumptions, or examples you want to remember. You can also generate an editable AI draft below."
            required
          />

          <p class="muted small">
            This is the reference material used to generate questions and
            evaluate your later recall attempts.
          </p>

          <details class="ai-draft-section">
            <summary>
              Optional: generate an AI reference draft
            </summary>

            <label for="rough-notes">
              Rough notes, prompt, or source excerpt
            </label>
            <textarea
              id="rough-notes"
              v-model="roughNotes"
              rows="7"
              minlength="3"
              maxlength="20000"
              placeholder="For example: Today I learned about TCP/IP, how packets are transferred, and different kinds of packets."
            />

            <label class="checkbox-label">
              <input
                v-model="useWebSearch"
                type="checkbox"
              />
              Allow AI to search the web and include sources
            </label>

            <button
              type="button"
              class="secondary"
              :disabled="!canGenerateReference || busy"
              @click="generateReference"
            >
              {{ generatingReference
                ? "Generating reference…"
                : "Generate AI reference material" }}
            </button>

            <p class="muted small">
              Without web search, the AI expands your rough notes using
              general knowledge. With web search, it may consult current
              web sources and include citations. Always check the draft
              before saving it as your reference.
            </p>

            <div
              v-if="sources.length"
              class="sources-box"
            >
              <h4>Sources consulted</h4>
              <ul>
                <li
                  v-for="(source, index) in sources"
                  :key="source.url"
                >
                  <a
                    :href="source.url"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {{ source.title || source.url }}
                  </a>
                </li>
              </ul>
            </div>
          </details>

          <div class="actions">
            <button
              type="button"
              :disabled="!canGenerateQuestions || busy"
              @click="generateQuestions"
            >
              {{ generatingQuestions
                ? "Working…"
                : "Generate questions" }}
            </button>

            <button
              type="button"
              class="secondary"
              :disabled="drafts.length >= 10"
              @click="addManual"
            >
              Add question manually
            </button>
          </div>
        </div>

        <div v-if="drafts.length" class="section-heading">
          <div>
            <h3>Review questions</h3>
            <p class="muted">
              Edit these before saving. One expected point per line.
            </p>
          </div>
        </div>

        <div
          v-for="(draft, index) in drafts"
          :key="draft.key"
          class="card"
          :class="{ discarded: draft.discarded }"
        >
          <div class="section-heading">
            <h3>Question {{ index + 1 }}</h3>

            <div class="actions">
              <button
                v-if="draft.discarded"
                type="button"
                class="text-button"
                @click="restoreProposal(draft)"
              >
                Restore
              </button>

              <button
                v-else
                type="button"
                class="text-button danger"
                @click="discardProposal(draft)"
              >
                Discard
              </button>
            </div>
          </div>

          <div
            v-if="draft.overlap && !draft.discarded"
            :class="['overlap-box', overlapClass(draft.overlap)]"
          >
            <strong>
              {{ draft.overlap.overlap.replace("_", " ") }}
            </strong>

            <p>{{ draft.overlap.reason }}</p>

            <button
              v-if="draft.overlap.suggested_revision"
              type="button"
              class="secondary"
              @click="applySuggestedRevision(draft)"
            >
              Use suggested revision
            </button>
          </div>

          <template v-if="!draft.discarded">
            <label :for="`question-${draft.key}`">Question</label>
            <textarea
              :id="`question-${draft.key}`"
              v-model="draft.question"
              rows="3"
              minlength="5"
              maxlength="1500"
              required
            />

            <label :for="`points-${draft.key}`">
              Expected key points
            </label>
            <textarea
              :id="`points-${draft.key}`"
              v-model="draft.pointsText"
              rows="5"
              required
            />
          </template>

          <p v-else class="muted">
            This proposed question is discarded and will not be saved.
          </p>
        </div>

        <button
          v-if="activeDrafts.length"
          type="submit"
          :disabled="busy"
        >
          {{ busy ? "Working…" : "Save learning" }}
        </button>
      </fieldset>
    </form>
  </section>
</template>

<style scoped>
.ai-draft-section {
  margin-bottom: 20px;
}

.ai-draft-section summary {
  margin-bottom: 15px;
}

.checkbox-label {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-weight: 400;
  margin: 15px 0;
  line-height: 1.5;
}

.checkbox-label input {
  width: auto;
  margin-top: 4px;
  margin-bottom: 0;
}

.sources-box {
  background: #f7f9fc;
  border: 1px solid #e6ebf3;
  border-radius: 9px;
  padding: 14px;
  margin-top: 15px;
}

.sources-box h4 {
  margin-bottom: 8px;
}

.sources-box ul {
  margin: 0;
  padding-left: 20px;
}

.discarded {
  opacity: 0.55;
}

.overlap-box {
  border-radius: 9px;
  padding: 13px;
  margin-bottom: 18px;
  border: 1px solid;
}

.overlap-box p {
  margin: 8px 0 12px;
}

.overlap-ok {
  background: #edf9f1;
  border-color: #c9e9d3;
  color: #2f6941;
}

.overlap-warning {
  background: #fff9e9;
  border-color: #eaddb6;
  color: #765c22;
}

.overlap-danger {
  background: #fff0f0;
  border-color: #f0cdcd;
  color: #9e3232;
}
</style>