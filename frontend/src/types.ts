export type Rating = "again" | "hard" | "good" | "easy";

export type OverlapType =
  | "unique"
  | "related"
  | "near_duplicate";

export type OverlapRecommendation =
  | "keep"
  | "edit"
  | "discard";

export interface ItemDraft {
  question: string;
  expected_points: string[];
}

export interface ReviewItem extends ItemDraft {
  id: string;
  topic_id: string;
  due_at: number;
  paused: boolean;
  version: number;
  created_at: number;
}

export interface Topic {
  id: string;
  title: string;
  notes: string;
  created_at: number;
  items: ReviewItem[];
}

export interface OverlapCheck {
  proposal_index: number;
  overlap: OverlapType;
  closest_existing_index: number | null;
  reason: string;
  recommendation: OverlapRecommendation;
  suggested_revision: string | null;
}

export interface GeneratedItemsWithOverlap {
  items: ItemDraft[];
  overlap_checks: OverlapCheck[];
}

export interface PointCheck {
  point_index: number;
  status: "correct" | "partial" | "missing" | "incorrect";
  answer_evidence: string;
  explanation: string;
}

export interface Evaluation {
  checks: PointCheck[];
  incorrect_claims: string[];
  unverified_additions: string[];
  short_feedback: string;
  suggested_rating: Rating;
}

export interface Attempt {
  id: string;
  item_id: string;
  question: string;
  reference: string;
  expected_points: string[];
  answer: string;
  assisted: boolean;
  feedback: Evaluation;
  suggested_rating: Rating;
  confirmed_rating: Rating | null;
  attempted_at: number;
  confirmed_at: number | null;
  scheduled_due_at: number | null;
  model: string;
  input_tokens: number;
  output_tokens: number;
}

export interface QueueItem {
  id: string;
  topic_id: string;
  topic_title: string;
  question: string;
  due_at: number;
  pending_attempt: Attempt | null;
}

export interface AppStatus {
  model: string;
  api_key_configured: boolean;
  desired_retention: number;
}