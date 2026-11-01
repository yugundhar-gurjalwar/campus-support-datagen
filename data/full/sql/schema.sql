-- Generated from campus_support.schema. SQLite/ANSI compatible.
-- Dates are ISO-8601 TEXT; booleans are 0/1.
PRAGMA foreign_keys = ON;

CREATE TABLE "role" (
  "role_id" TEXT PRIMARY KEY,
  "role_name" TEXT NOT NULL UNIQUE CHECK ("role_name" IN ('Learner', 'Instructor', 'Academic Administrator', 'Support Staff', 'Platform Administrator')),
  "role_group" TEXT NOT NULL CHECK ("role_group" IN ('requester', 'staff', 'admin')),
  "can_file_tickets" INTEGER NOT NULL CHECK ("can_file_tickets" IN (0,1)),
  "can_resolve_tickets" INTEGER NOT NULL CHECK ("can_resolve_tickets" IN (0,1)),
  "description" TEXT NOT NULL
);

CREATE TABLE "term" (
  "term_id" TEXT PRIMARY KEY,
  "term_name" TEXT NOT NULL,
  "start_date" TEXT NOT NULL,
  "end_date" TEXT NOT NULL,
  "registration_open_date" TEXT NOT NULL,
  "status" TEXT NOT NULL CHECK ("status" IN ('completed', 'active', 'upcoming'))
);

CREATE TABLE "business_calendar" (
  "calendar_id" TEXT PRIMARY KEY,
  "name" TEXT NOT NULL,
  "timezone_label" TEXT NOT NULL CHECK ("timezone_label" IN ('campus-local'))
);

CREATE TABLE "calendar_hours" (
  "hours_id" TEXT PRIMARY KEY,
  "calendar_id" TEXT NOT NULL,
  "weekday" INTEGER NOT NULL CHECK ("weekday" >= 0) CHECK ("weekday" <= 6),
  "open_minute" INTEGER NOT NULL CHECK ("open_minute" >= 0) CHECK ("open_minute" <= 1440),
  "close_minute" INTEGER NOT NULL CHECK ("close_minute" >= 0) CHECK ("close_minute" <= 1440),
  FOREIGN KEY ("calendar_id") REFERENCES "business_calendar" ("calendar_id"),
  UNIQUE ("calendar_id", "weekday")
);

CREATE TABLE "holiday" (
  "holiday_id" TEXT PRIMARY KEY,
  "holiday_date" TEXT NOT NULL UNIQUE,
  "name" TEXT NOT NULL
);

CREATE TABLE "team" (
  "team_id" TEXT PRIMARY KEY,
  "team_name" TEXT NOT NULL,
  "tier" INTEGER NOT NULL CHECK ("tier" >= 1) CHECK ("tier" <= 2),
  "domain" TEXT NOT NULL CHECK ("domain" IN ('FIN', 'REG', 'IT', 'ACC', 'ADMIN', 'PLAT')),
  "calendar_id" TEXT NOT NULL,
  "escalation_team_id" TEXT,
  "active" INTEGER NOT NULL CHECK ("active" IN (0,1)),
  FOREIGN KEY ("calendar_id") REFERENCES "business_calendar" ("calendar_id"),
  FOREIGN KEY ("escalation_team_id") REFERENCES "team" ("team_id")
);

CREATE TABLE "requester" (
  "requester_id" TEXT PRIMARY KEY,
  "role_id" TEXT NOT NULL,
  "full_name" TEXT NOT NULL,
  "email" TEXT NOT NULL UNIQUE,
  "department_code" TEXT NOT NULL CHECK ("department_code" IN ('CS', 'BUS', 'NUR', 'ENG', 'ART', 'BIO', 'FAO', 'REGO', 'ITS', 'DSS', 'ADM')),
  "program_level" TEXT CHECK ("program_level" IN ('undergraduate', 'graduate', 'non_degree')),
  "team_id" TEXT,
  "status" TEXT NOT NULL CHECK ("status" IN ('active', 'inactive')),
  "active_from" TEXT NOT NULL,
  "active_to" TEXT,
  FOREIGN KEY ("role_id") REFERENCES "role" ("role_id"),
  FOREIGN KEY ("team_id") REFERENCES "team" ("team_id")
);

CREATE TABLE "category" (
  "category_id" TEXT PRIMARY KEY,
  "domain" TEXT NOT NULL CHECK ("domain" IN ('FIN', 'REG', 'IT', 'ACC')),
  "domain_name" TEXT NOT NULL CHECK ("domain_name" IN ('financial_aid', 'registration', 'it', 'accessibility')),
  "category_name" TEXT NOT NULL,
  "default_priority" TEXT NOT NULL CHECK ("default_priority" IN ('low', 'normal', 'high', 'urgent')),
  "human_review_required" INTEGER NOT NULL CHECK ("human_review_required" IN (0,1)),
  "deadline_sensitive" INTEGER NOT NULL CHECK ("deadline_sensitive" IN (0,1)),
  "description" TEXT NOT NULL
);

CREATE TABLE "team_category_authorization" (
  "authorization_id" TEXT PRIMARY KEY,
  "team_id" TEXT NOT NULL,
  "category_id" TEXT NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  FOREIGN KEY ("team_id") REFERENCES "team" ("team_id"),
  FOREIGN KEY ("category_id") REFERENCES "category" ("category_id"),
  UNIQUE ("team_id", "category_id")
);

CREATE TABLE "sla_policy" (
  "sla_policy_id" TEXT PRIMARY KEY,
  "priority" TEXT NOT NULL UNIQUE CHECK ("priority" IN ('low', 'normal', 'high', 'urgent')),
  "first_response_minutes" INTEGER NOT NULL CHECK ("first_response_minutes" >= 1),
  "resolution_minutes" INTEGER NOT NULL CHECK ("resolution_minutes" >= 1),
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT
);

CREATE TABLE "routing_rule" (
  "routing_rule_id" TEXT PRIMARY KEY,
  "category_id" TEXT NOT NULL,
  "requester_role_id" TEXT,
  "target_team_id" TEXT NOT NULL,
  "priority_override" TEXT CHECK ("priority_override" IN ('low', 'normal', 'high', 'urgent')),
  "precedence" INTEGER NOT NULL CHECK ("precedence" >= 1),
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  "description" TEXT NOT NULL,
  FOREIGN KEY ("category_id") REFERENCES "category" ("category_id"),
  FOREIGN KEY ("requester_role_id") REFERENCES "role" ("role_id"),
  FOREIGN KEY ("target_team_id") REFERENCES "team" ("team_id")
);

CREATE TABLE "policy_document" (
  "policy_id" TEXT PRIMARY KEY,
  "domain" TEXT NOT NULL CHECK ("domain" IN ('FIN', 'REG', 'IT', 'ACC')),
  "title" TEXT NOT NULL,
  "category_id" TEXT NOT NULL,
  "owner_team_id" TEXT NOT NULL,
  "status" TEXT NOT NULL CHECK ("status" IN ('active', 'retired')),
  "first_effective_date" TEXT NOT NULL,
  "retired_date" TEXT,
  "is_synthetic" INTEGER NOT NULL CHECK ("is_synthetic" IN (0,1)),
  "source_note" TEXT NOT NULL,
  FOREIGN KEY ("category_id") REFERENCES "category" ("category_id"),
  FOREIGN KEY ("owner_team_id") REFERENCES "team" ("team_id")
);

CREATE TABLE "knowledge_article" (
  "article_id" TEXT PRIMARY KEY,
  "policy_id" TEXT NOT NULL,
  "version_no" INTEGER NOT NULL CHECK ("version_no" >= 1),
  "title" TEXT NOT NULL,
  "body" TEXT NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  "status" TEXT NOT NULL CHECK ("status" IN ('current', 'superseded', 'retired')),
  "supersedes_article_id" TEXT,
  "author_id" TEXT NOT NULL,
  "published_at" TEXT NOT NULL,
  FOREIGN KEY ("policy_id") REFERENCES "policy_document" ("policy_id"),
  FOREIGN KEY ("supersedes_article_id") REFERENCES "knowledge_article" ("article_id"),
  FOREIGN KEY ("author_id") REFERENCES "requester" ("requester_id"),
  UNIQUE ("policy_id", "version_no")
);

CREATE TABLE "article_fact" (
  "fact_id" TEXT PRIMARY KEY,
  "article_id" TEXT NOT NULL,
  "fact_key" TEXT NOT NULL,
  "fact_value" TEXT NOT NULL,
  "unit" TEXT,
  FOREIGN KEY ("article_id") REFERENCES "knowledge_article" ("article_id"),
  UNIQUE ("article_id", "fact_key")
);

CREATE TABLE "article_category" (
  "article_category_id" TEXT PRIMARY KEY,
  "article_id" TEXT NOT NULL,
  "category_id" TEXT NOT NULL,
  "is_primary" INTEGER NOT NULL CHECK ("is_primary" IN (0,1)),
  FOREIGN KEY ("article_id") REFERENCES "knowledge_article" ("article_id"),
  FOREIGN KEY ("category_id") REFERENCES "category" ("category_id"),
  UNIQUE ("article_id", "category_id")
);

CREATE TABLE "ticket" (
  "ticket_id" TEXT PRIMARY KEY,
  "requester_id" TEXT NOT NULL,
  "term_id" TEXT NOT NULL,
  "category_id" TEXT NOT NULL,
  "priority" TEXT NOT NULL CHECK ("priority" IN ('low', 'normal', 'high', 'urgent')),
  "channel" TEXT NOT NULL CHECK ("channel" IN ('portal', 'email', 'chat', 'phone')),
  "subject" TEXT NOT NULL,
  "created_at" TEXT NOT NULL,
  "requester_deadline_at" TEXT,
  "status" TEXT NOT NULL CHECK ("status" IN ('new', 'triaged', 'in_progress', 'pending_requester', 'escalated', 'resolved', 'reopened', 'closed')),
  "current_team_id" TEXT,
  "resolved_at" TEXT,
  "closed_at" TEXT,
  "resolution_code" TEXT CHECK ("resolution_code" IN ('answered_by_policy', 'resolved_after_escalation', 'closed_no_response')),
  "reopen_count" INTEGER NOT NULL CHECK ("reopen_count" >= 0),
  "escalation_count" INTEGER NOT NULL CHECK ("escalation_count" >= 0),
  "message_count" INTEGER NOT NULL CHECK ("message_count" >= 1),
  FOREIGN KEY ("requester_id") REFERENCES "requester" ("requester_id"),
  FOREIGN KEY ("term_id") REFERENCES "term" ("term_id"),
  FOREIGN KEY ("category_id") REFERENCES "category" ("category_id"),
  FOREIGN KEY ("current_team_id") REFERENCES "team" ("team_id")
);

CREATE TABLE "ticket_event" (
  "event_id" TEXT PRIMARY KEY,
  "ticket_id" TEXT NOT NULL,
  "event_seq" INTEGER NOT NULL CHECK ("event_seq" >= 1),
  "event_type" TEXT NOT NULL CHECK ("event_type" IN ('created', 'routed', 'assigned', 'clarification_requested', 'clarification_received', 'escalated', 'reassigned', 'resolved', 'reopened', 'closed')),
  "from_status" TEXT CHECK ("from_status" IN ('new', 'triaged', 'in_progress', 'pending_requester', 'escalated', 'resolved', 'reopened', 'closed')),
  "to_status" TEXT NOT NULL CHECK ("to_status" IN ('new', 'triaged', 'in_progress', 'pending_requester', 'escalated', 'resolved', 'reopened', 'closed')),
  "event_at" TEXT NOT NULL,
  "actor_type" TEXT NOT NULL CHECK ("actor_type" IN ('requester', 'support_staff', 'system')),
  "actor_id" TEXT,
  "team_id" TEXT,
  "reason_code" TEXT CHECK ("reason_code" IN ('human_review_required', 'no_current_policy', 'ambiguity_unresolved', 'urgent_deadline', 'routing_rule', 'initial_pickup', 'tier2_pickup', 'reopen_pickup', 'staff_reassign', 'policy_answer', 'tier2_decision', 'requester_reopened', 'no_response', 'auto_close_after_resolution', 'needs_clarification', 'clarification_provided')),
  FOREIGN KEY ("ticket_id") REFERENCES "ticket" ("ticket_id"),
  FOREIGN KEY ("actor_id") REFERENCES "requester" ("requester_id"),
  FOREIGN KEY ("team_id") REFERENCES "team" ("team_id"),
  UNIQUE ("ticket_id", "event_seq")
);

CREATE TABLE "retrieval_result" (
  "retrieval_id" TEXT PRIMARY KEY,
  "ticket_id" TEXT NOT NULL UNIQUE,
  "retrieved_at" TEXT NOT NULL,
  "matched_policy_id" TEXT,
  "matched_article_id" TEXT,
  "initial_confidence" REAL NOT NULL CHECK ("initial_confidence" >= 0) CHECK ("initial_confidence" <= 1),
  "final_confidence" REAL NOT NULL CHECK ("final_confidence" >= 0) CHECK ("final_confidence" <= 1),
  "outcome" TEXT NOT NULL CHECK ("outcome" IN ('matched', 'low_confidence', 'no_current_policy')),
  FOREIGN KEY ("ticket_id") REFERENCES "ticket" ("ticket_id"),
  FOREIGN KEY ("matched_policy_id") REFERENCES "policy_document" ("policy_id"),
  FOREIGN KEY ("matched_article_id") REFERENCES "knowledge_article" ("article_id")
);

CREATE TABLE "message" (
  "message_id" TEXT PRIMARY KEY,
  "ticket_id" TEXT NOT NULL,
  "message_seq" INTEGER NOT NULL CHECK ("message_seq" >= 1),
  "sender_type" TEXT NOT NULL CHECK ("sender_type" IN ('requester', 'support_staff', 'system')),
  "sender_id" TEXT,
  "message_type" TEXT NOT NULL CHECK ("message_type" IN ('question', 'system_ack', 'clarification_request', 'clarification_reply', 'answer', 'agent_update', 'escalation_note', 'handoff_response', 'requester_followup', 'reopen_request', 'thanks')),
  "sent_at" TEXT NOT NULL,
  "body" TEXT NOT NULL,
  FOREIGN KEY ("ticket_id") REFERENCES "ticket" ("ticket_id"),
  FOREIGN KEY ("sender_id") REFERENCES "requester" ("requester_id"),
  UNIQUE ("ticket_id", "message_seq")
);

CREATE TABLE "message_citation" (
  "citation_id" TEXT PRIMARY KEY,
  "message_id" TEXT NOT NULL,
  "article_id" TEXT NOT NULL,
  "article_version_no" INTEGER NOT NULL CHECK ("article_version_no" >= 1),
  "citation_rank" INTEGER NOT NULL CHECK ("citation_rank" >= 1),
  FOREIGN KEY ("message_id") REFERENCES "message" ("message_id"),
  FOREIGN KEY ("article_id") REFERENCES "knowledge_article" ("article_id"),
  UNIQUE ("message_id", "article_id")
);

CREATE TABLE "message_claim" (
  "claim_id" TEXT PRIMARY KEY,
  "message_id" TEXT NOT NULL,
  "fact_key" TEXT NOT NULL,
  "claimed_value" TEXT NOT NULL,
  "supporting_article_id" TEXT,
  FOREIGN KEY ("message_id") REFERENCES "message" ("message_id"),
  FOREIGN KEY ("supporting_article_id") REFERENCES "knowledge_article" ("article_id")
);

CREATE TABLE "assignment" (
  "assignment_id" TEXT PRIMARY KEY,
  "ticket_id" TEXT NOT NULL,
  "assignment_seq" INTEGER NOT NULL CHECK ("assignment_seq" >= 1),
  "team_id" TEXT NOT NULL,
  "assignee_id" TEXT NOT NULL,
  "assignment_type" TEXT NOT NULL CHECK ("assignment_type" IN ('initial', 'reassignment', 'escalation', 'reopen')),
  "routing_rule_id" TEXT,
  "assigned_at" TEXT NOT NULL,
  "ended_at" TEXT,
  "end_reason" TEXT CHECK ("end_reason" IN ('escalated', 'reassigned', 'resolved')),
  FOREIGN KEY ("ticket_id") REFERENCES "ticket" ("ticket_id"),
  FOREIGN KEY ("team_id") REFERENCES "team" ("team_id"),
  FOREIGN KEY ("assignee_id") REFERENCES "requester" ("requester_id"),
  FOREIGN KEY ("routing_rule_id") REFERENCES "routing_rule" ("routing_rule_id"),
  UNIQUE ("ticket_id", "assignment_seq")
);

CREATE TABLE "sla" (
  "sla_id" TEXT PRIMARY KEY,
  "ticket_id" TEXT NOT NULL UNIQUE,
  "sla_policy_id" TEXT NOT NULL,
  "calendar_id" TEXT NOT NULL,
  "calendar_mode" TEXT NOT NULL CHECK ("calendar_mode" IN ('business_hours', 'calendar_24x7')),
  "clock_start_at" TEXT NOT NULL,
  "first_response_due_at" TEXT NOT NULL,
  "resolution_due_at" TEXT NOT NULL,
  "first_response_at" TEXT,
  "first_resolved_at" TEXT,
  "resolution_clock_stop_at" TEXT NOT NULL,
  "first_response_elapsed_minutes" INTEGER,
  "resolution_elapsed_minutes" INTEGER NOT NULL,
  "first_response_breached" INTEGER NOT NULL CHECK ("first_response_breached" IN (0,1)),
  "resolution_breached" INTEGER NOT NULL CHECK ("resolution_breached" IN (0,1)),
  FOREIGN KEY ("ticket_id") REFERENCES "ticket" ("ticket_id"),
  FOREIGN KEY ("sla_policy_id") REFERENCES "sla_policy" ("sla_policy_id"),
  FOREIGN KEY ("calendar_id") REFERENCES "business_calendar" ("calendar_id")
);

CREATE TABLE "resolution_feedback" (
  "feedback_id" TEXT PRIMARY KEY,
  "ticket_id" TEXT NOT NULL UNIQUE,
  "submitted_at" TEXT NOT NULL,
  "rating" INTEGER NOT NULL CHECK ("rating" >= 1) CHECK ("rating" <= 5),
  "issue_resolved" INTEGER NOT NULL CHECK ("issue_resolved" IN (0,1)),
  "comment_code" TEXT NOT NULL CHECK ("comment_code" IN ('fast_and_clear', 'helpful', 'slow', 'unclear', 'wrong_or_outdated', 'unresolved', 'none')),
  FOREIGN KEY ("ticket_id") REFERENCES "ticket" ("ticket_id")
);
