export type InventorySource = {
  id: string; source_key: string; source_name: string; source_category?: string;
  scope?: string; status: "CONFIRMED" | "POTENTIAL" | "MISSING_INFORMATION" | "NOT_APPLICABLE" | "OUTSOURCED";
};

export type ActivityInput = {
  period_start: string; period_end: string; quantity: number; unit_code: string;
  data_source_type?: string; data_quality?: string; evidence_reference?: string; notes?: string;
};

export type UnitTaxonomy = {
  dimensions: Array<{ dimension_id: string; base_unit: string; units: Array<{ unit_id: string; symbol: string }> }>;
};
