import type { Severity } from "../../shared/types";

export interface Insight {
  instance_name: string;
  category: string;
  severity: Severity;
  message: string;
  created_at: string;
}

// --- Advisor + Ask the fleet (app/modules/insights/agent.py) ---

export interface AdvisorTimelineStep {
  stage: string;
  detail: string;
}

export interface AdvisorFinding {
  finding_key: string;
  title: string;
  severity: string;
  timeline: AdvisorTimelineStep[];
  proposed_ddl: string | null;
  risks: string[];
  evidence: string[];
  estimated_impact: string | null;
}

export interface AdvisorReport {
  summary: string;
  findings: AdvisorFinding[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AIStatus {
  provider: "anthropic" | "openai" | "local" | string;
  provider_label: string;
  configured: boolean;
  routine_model: string;
  deep_model: string;
  base_url: string | null;
  reason: string | null;
}

