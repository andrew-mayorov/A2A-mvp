from __future__ import annotations

import json
from pathlib import Path

from sber_a2a.domain import contracts

MODELS = [
    contracts.AgentPassport,
    contracts.AgentCardSnapshot,
    contracts.PublicKeyReference,
    contracts.AgentAttestation,
    contracts.Mandate,
    contracts.ToolManifest,
    contracts.ToolDefinition,
    contracts.SignedEnvelope,
    contracts.Need,
    contracts.RFQ,
    contracts.Quote,
    contracts.QuoteLine,
    contracts.QuoteDocument,
    contracts.QuoteValidationResult,
    contracts.ComparisonResult,
    contracts.ApprovalRequest,
    contracts.ApprovalSnapshot,
    contracts.HumanDecision,
    contracts.PurchaseIntent,
    contracts.SupplierCommitment,
    contracts.LedgerAnchor,
    contracts.OracleVerification,
    contracts.PaymentDraftRequest,
    contracts.PaymentDraft,
    contracts.DeliveryEvent,
    contracts.DocumentReference,
    contracts.EvidenceRecord,
    contracts.EvidenceBundle,
    contracts.FraudDecision,
    contracts.PolicyDecision,
]


def main() -> None:
    output = Path("schemas/v1")
    output.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        target = output / f"{model.__name__}.schema.json"
        target.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
