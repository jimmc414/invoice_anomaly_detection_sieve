-- tenants and vendors
CREATE TABLE IF NOT EXISTS vendors (
  tenant_id TEXT NOT NULL,
  vendor_id TEXT NOT NULL,
  vendor_name TEXT NOT NULL,
  home_currency TEXT,
  PRIMARY KEY (tenant_id, vendor_id)
);

CREATE TABLE IF NOT EXISTS vendor_remit_accounts (
  tenant_id TEXT NOT NULL,
  vendor_id TEXT NOT NULL,
  remit_account_hash TEXT NOT NULL,
  remit_name TEXT,
  first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
  last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, vendor_id, remit_account_hash)
);

-- invoices (immutable snapshot by payload hash)
CREATE TABLE IF NOT EXISTS invoices (
  tenant_id TEXT NOT NULL,
  invoice_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  vendor_id TEXT NOT NULL,
  invoice_number TEXT NOT NULL,
  invoice_number_norm TEXT NOT NULL,
  invoice_date DATE NOT NULL,
  currency TEXT NOT NULL,
  total NUMERIC(18,4) NOT NULL,
  tax_total NUMERIC(18,4),
  po_number TEXT,
  remit_bank_account_masked TEXT,
  remit_account_hash TEXT,
  remit_name TEXT,
  pdf_hash TEXT,
  terms TEXT,
  raw_json JSONB NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, invoice_id)
);
CREATE INDEX IF NOT EXISTS idx_inv_vendor ON invoices(tenant_id, vendor_id);
CREATE INDEX IF NOT EXISTS idx_inv_po ON invoices(tenant_id, vendor_id, po_number);
CREATE INDEX IF NOT EXISTS idx_inv_date ON invoices(tenant_id, invoice_date);
CREATE INDEX IF NOT EXISTS idx_inv_total ON invoices(tenant_id, vendor_id, total);
CREATE INDEX IF NOT EXISTS idx_inv_invnum_norm ON invoices(tenant_id, vendor_id, invoice_number_norm);

-- line items
CREATE TABLE IF NOT EXISTS invoice_lines (
  tenant_id TEXT NOT NULL,
  invoice_id TEXT NOT NULL,
  line_no INT NOT NULL,
  sku TEXT,
  "desc" TEXT NOT NULL,
  qty NUMERIC(18,6) NOT NULL,
  unit_price NUMERIC(18,6) NOT NULL,
  amount NUMERIC(18,6) NOT NULL,
  gl_code TEXT,
  cost_center TEXT,
  PRIMARY KEY (tenant_id, invoice_id, line_no)
);

-- decisions
CREATE TABLE IF NOT EXISTS decisions (
  tenant_id TEXT NOT NULL,
  decision_id TEXT NOT NULL,
  invoice_id TEXT NOT NULL,
  model_id TEXT,
  model_version TEXT,
  ruleset_version TEXT,
  risk_score NUMERIC(5,2) NOT NULL,
  decision TEXT NOT NULL,
  reason_codes TEXT[] NOT NULL,
  top_matches JSONB,
  explanations JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, decision_id)
);
CREATE INDEX IF NOT EXISTS idx_dec_invoice ON decisions(tenant_id, invoice_id);

-- cases
CREATE TABLE IF NOT EXISTS cases (
  tenant_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  invoice_id TEXT NOT NULL,
  status TEXT NOT NULL,
  sla_due TIMESTAMP,
  disposition TEXT,
  disposition_user TEXT,
  disposition_at TIMESTAMP,
  notes TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, case_id)
);
CREATE INDEX IF NOT EXISTS idx_case_invoice ON cases(tenant_id, invoice_id);

-- configs
CREATE TABLE IF NOT EXISTS configs (
  tenant_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  key TEXT NOT NULL,
  value JSONB NOT NULL,
  updated_by TEXT,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, scope, key)
);

-- audit
CREATE TABLE IF NOT EXISTS audit_log (
  tenant_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  payload JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- vendor amount baselines
CREATE TABLE IF NOT EXISTS vendor_amount_baselines (
  tenant_id TEXT NOT NULL,
  vendor_id TEXT NOT NULL,
  mean_total NUMERIC(18,4) NOT NULL,
  std_total NUMERIC(18,4) NOT NULL,
  sample_count INT NOT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, vendor_id)
);
