<script setup lang="ts">
import { formatDate } from "../api";
import type { Attempt } from "../types";

defineProps<{
  attempt: Attempt;
}>();
</script>

<template>
  <section class="feedback">
    <p class="feedback-summary">
      {{ attempt.feedback.short_feedback }}
    </p>

    <div
      v-for="check in attempt.feedback.checks"
      :key="check.point_index"
      class="point-check"
    >
      <div class="row">
        <span :class="['status', check.status]">
          {{ check.status }}
        </span>

        <span>
          {{ attempt.expected_points[check.point_index] }}
        </span>
      </div>

      <blockquote v-if="check.answer_evidence">
        {{ check.answer_evidence }}
      </blockquote>

      <p class="muted">{{ check.explanation }}</p>
    </div>

    <section v-if="attempt.feedback.incorrect_claims.length">
      <h4>Incorrect claims</h4>
      <ul>
        <li
          v-for="(claim, index) in attempt.feedback.incorrect_claims"
          :key="index"
        >
          {{ claim }}
        </li>
      </ul>
    </section>

    <section v-if="attempt.feedback.unverified_additions.length">
      <h4>Additional claims not verified</h4>
      <ul>
        <li
          v-for="(claim, index) in attempt.feedback.unverified_additions"
          :key="index"
        >
          {{ claim }}
        </li>
      </ul>
    </section>

    <details>
      <summary>Reference used for this evaluation</summary>
      <pre class="reference">{{ attempt.reference }}</pre>
    </details>

    <details>
      <summary>Your submitted answer</summary>
      <pre class="reference">{{ attempt.answer }}</pre>
    </details>

    <p v-if="attempt.assisted" class="muted">
      This attempt was marked as assisted.
    </p>

    <p v-if="attempt.confirmed_rating" class="muted">
      Confirmed rating: {{ attempt.confirmed_rating }}
      <template v-if="attempt.scheduled_due_at">
        · Next review: {{ formatDate(attempt.scheduled_due_at) }}
      </template>
    </p>
  </section>
</template>