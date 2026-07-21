export type DealStatus =
  | "draft"
  | "awaiting_approval"
  | "order_created"
  | "fulfilling"
  | "completed"
  | "failed"
  | "rejected"
  | "changes_requested"
  | "payment_signature_required";

export interface Health {
  status: string;
  role: string;
  llm_enabled: boolean;
  llm_provider: "disabled" | "openrouter" | "gigachat";
}

export interface SupplierSummary {
  supplier_id: string;
  name: string;
  categories: string[];
  active: boolean;
}

export interface Quote {
  quote_id: string;
  supplier_id: string;
  supplier_name: string;
  sku: string;
  product_name: string;
  quantity: number;
  unit_price: string;
  delivery_fee: string;
  currency: string;
  vat_rate: string;
  delivery_days: number;
  warranty_months: number;
  supplier_risk: string;
  payment_delay_days: number;
  valid_until: string;
}

export interface ComponentScores {
  price: string;
  delivery: string;
  warranty: string;
  risk: string;
  payment_terms: string;
}

export interface EvaluatedQuote {
  quote: Quote;
  eligible: boolean;
  rejection_reasons: string[];
  scores: ComponentScores | null;
  total_score: string | null;
}

export interface Comparison {
  evaluated_quotes: EvaluatedQuote[];
  recommended_quote_id: string | null;
  explanation: string;
  ranking_version: string;
}

export interface DealEvent {
  event_type: string;
  actor: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ApprovalSnapshot {
  snapshot_id: string;
  quote_id: string;
  supplier_id: string;
  supplier_name: string;
  sku: string;
  product_name: string;
  quantity: number;
  total_cost: string;
  currency: string;
  delivery_days: number;
  warranty_months: number;
  payment_delay_days: number;
  ranking_version: string;
  total_score: string | null;
  snapshot_hash: string;
  created_at: string;
}

export interface OrderState {
  order_id: string;
  supplier_id: string;
  quote_id: string;
  status: "awarded" | "confirmed_by_supplier";
  confirmed_at: string | null;
}

export interface PaymentDraft {
  payment_draft_id: string;
  order_id: string;
  amount: string;
  currency: string;
  payee_supplier_id: string;
  status: "created" | "awaiting_customer_signature" | "signed" | "held";
  recipient_binding_hash: string;
  requires_human_signature: boolean;
  created_at: string;
}

export interface FulfillmentUpdate {
  status:
    | "order_confirmed"
    | "packed"
    | "shipped"
    | "delivered"
    | "documents_ready"
    | "completed";
  actor: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface DocumentRef {
  document_id: string;
  document_type: string;
  title: string;
  source: string;
  sha256: string;
  created_at: string;
}

export interface HumanDecision {
  decision_id: string;
  decision: "approve" | "reject" | "request_changes";
  approver_subject: string;
  organization_id: string;
  role: string;
  snapshot_hash: string;
  reason: string | null;
  created_at: string;
}

export interface PurchaseIntent {
  intent_id: string;
  deal_id: string;
  approved_snapshot_hash: string;
  buyer_agent_id: string;
  supplier_agent_id: string;
  amount: string;
  currency: string;
  recipient_binding_hash: string;
  created_at: string;
}

export interface LedgerAnchor {
  anchor_id: string;
  deal_id: string;
  sequence_number: number;
  previous_hash: string;
  current_hash: string;
  payload_hash: string;
  created_at: string;
}

export interface ControlDecision {
  decision: string;
  policy_version: string;
  operation: string;
  rule_ids: string[];
  reasons: string[];
  created_at: string;
}

export interface OracleVerification {
  verification_id: string;
  purchase_intent_id: string;
  verified: boolean;
  checks: Record<string, boolean>;
  fraud_decision: ControlDecision;
  created_at: string;
}

export interface Deal {
  deal_id: string;
  status: DealStatus;
  intent: {
    customer_id: string;
    product: {
      sku: string;
      name: string;
      category: string;
      quantity: number;
    };
    delivery_city: string;
    delivery_by: string;
    max_total: string | null;
    currency: string;
    weights: Record<string, string>;
  };
  mandate: {
    mandate_id: string;
    customer_id: string;
    organization_id: string;
    agent_id: string;
    issuer: string;
    authorized_by: string;
    allowed_actions: string[];
    forbidden_actions: string[];
    allowed_categories: string[];
    max_total: string;
    cumulative_amount: string;
    currency: string;
    valid_from: string;
    expires_at: string;
    allowed_supplier_ids: string[] | null;
    requires_human_approval: boolean;
    required_approvals: string[];
    revoked_at: string | null;
    signature: string;
    version: string;
  };
  supplier_ids: string[];
  quotes: Quote[];
  comparison: Comparison | null;
  selected_quote_id: string | null;
  order_id: string | null;
  payment_draft_id: string | null;
  approval_snapshot: ApprovalSnapshot | null;
  order: OrderState | null;
  payment_draft: PaymentDraft | null;
  human_decision: HumanDecision | null;
  purchase_intent: PurchaseIntent | null;
  ledger_anchor: LedgerAnchor | null;
  oracle_verification: OracleVerification | null;
  policy_decisions: ControlDecision[];
  fraud_decisions: ControlDecision[];
  fulfillment: FulfillmentUpdate[];
  documents: DocumentRef[];
  errors: string[];
  events: DealEvent[];
  created_at: string;
  updated_at: string;
}

export interface DealInput {
  customerId: string;
  authorizedBy: string;
  sku: string;
  productName: string;
  quantity: number;
  deliveryCity: string;
  deliveryDays: number;
  maxTotal: number;
}

export interface DemoConfig {
  profile: string;
  production_like: boolean;
  buyer_agent_id: string;
  organization_id: string;
  approver_subject: string;
  category: string;
  currency: string;
  delivery_city: string;
  delivery_days: number;
  mandate_validity_hours: number;
  default_sku: string;
  default_product_name: string;
  default_quantity: number;
  default_maximum_amount: string;
  mandate_version: string;
  mandate_signature: string;
  mandate_issuer: string;
  allowed_actions: string[];
  forbidden_actions: string[];
  approval_role: string;
  ranking: Record<string, string>;
}

export interface ApprovalResult {
  deal_id: string;
  status: DealStatus;
  selected_quote_id: string;
  order_id: string;
  payment_draft_id: string;
  approval_snapshot_hash: string;
}

export interface OutboxMessage {
  outbox_id: string;
  aggregate_id: string;
  recipient_agent_id: string;
  message_type: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
  status: "pending" | "published";
  attempts: number;
  correlation_id: string;
  causation_id: string | null;
  created_at: string;
  published_at: string | null;
}

export interface EvidenceBundle {
  deal: Deal;
  events: DealEvent[];
  approval_snapshot: ApprovalSnapshot | null;
  order: OrderState | null;
  payment_draft: PaymentDraft | null;
  human_decision: HumanDecision | null;
  purchase_intent: PurchaseIntent | null;
  ledger_anchor: LedgerAnchor | null;
  oracle_verification: OracleVerification | null;
  policy_decisions: ControlDecision[];
  fraud_decisions: ControlDecision[];
  fulfillment: FulfillmentUpdate[];
  documents: DocumentRef[];
  outbox_messages: OutboxMessage[];
}
