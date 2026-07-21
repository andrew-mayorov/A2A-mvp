import type {
  ApprovalResult,
  Deal,
  DealInput,
  DemoConfig,
  EvidenceBundle,
  Health,
  SupplierSummary
} from "./types";

let demoIdentity: string | null = null;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (demoIdentity) headers["X-Demo-User"] = demoIdentity;
  const response = await fetch(path, {
    ...init,
    headers: { ...headers, ...init?.headers }
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

function isoDateAfter(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}

export const api = {
  configureIdentity: (identity: string) => {
    demoIdentity = identity;
  },
  demoConfig: () => request<DemoConfig>("/api/v1/demo/config"),
  health: () => request<Health>("/health"),
  suppliers: () => request<SupplierSummary[]>("/api/v1/suppliers"),
  deals: () => request<Deal[]>("/api/v1/deals"),
  getDeal: (dealId: string) => request<Deal>(`/api/v1/deals/${dealId}`),
  evidence: (dealId: string) =>
    request<EvidenceBundle>(`/api/v1/deals/${dealId}/evidence`),
  createDeal: (input: DealInput, config: DemoConfig) =>
    request<Deal>("/api/v1/deals", {
      method: "POST",
      body: JSON.stringify({
        intent: {
          customer_id: config.organization_id,
          product: {
            sku: input.sku,
            name: input.productName,
            category: config.category,
            quantity: input.quantity
          },
          delivery_city: input.deliveryCity,
          delivery_by: isoDateAfter(input.deliveryDays),
          max_total: input.maxTotal.toFixed(2),
          currency: config.currency,
          weights: config.ranking
        },
        mandate: {
          customer_id: config.organization_id,
          organization_id: config.organization_id,
          agent_id: config.buyer_agent_id,
          issuer: config.mandate_issuer,
          authorized_by: input.authorizedBy,
          allowed_actions: config.allowed_actions,
          forbidden_actions: config.forbidden_actions,
          allowed_categories: [config.category],
          max_total: input.maxTotal.toFixed(2),
          cumulative_amount: "0.00",
          currency: config.currency,
          valid_from: new Date().toISOString(),
          expires_at: new Date(
            Date.now() + config.mandate_validity_hours * 3_600_000
          ).toISOString(),
          requires_human_approval: true,
          required_approvals: [config.approval_role],
          signature: config.mandate_signature,
          version: config.mandate_version
        }
      })
    }),
  approve: (
    dealId: string,
    quoteId: string,
    approvedBy: string,
    approvalSnapshotHash: string
  ) =>
    request<ApprovalResult>(`/api/v1/deals/${dealId}/approve`, {
      method: "POST",
      body: JSON.stringify({
        quote_id: quoteId,
        approved_by: approvedBy,
        approval_snapshot_hash: approvalSnapshotHash,
        decision: "approve"
      })
    }),
  decide: (
    dealId: string,
    quoteId: string,
    approvedBy: string,
    approvalSnapshotHash: string,
    decision: "reject" | "request_changes"
  ) =>
    request<Deal>(`/api/v1/deals/${dealId}/decision`, {
      method: "POST",
      body: JSON.stringify({
        quote_id: quoteId,
        approved_by: approvedBy,
        approval_snapshot_hash: approvalSnapshotHash,
        decision
      })
    }),
  signPayment: (deal: Deal) =>
    request(`/api/v1/deals/${deal.deal_id}/payment-signature`, {
      method: "POST",
      body: JSON.stringify({
        signed_by: deal.mandate.authorized_by,
        payment_draft_id: deal.payment_draft_id,
        confirmation: true
      })
    })
};
