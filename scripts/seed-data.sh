#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/.." && pwd)"
api_base_url="${API_BASE_URL:-http://127.0.0.1:8000}"
assessment_id="10000000-0000-4000-8000-000000000003"
template_id="industry-food-processing-v1"
source_type_id="purchased_grid_electricity"

if curl --fail --silent --show-error \
  "${api_base_url}/api/assessments/${assessment_id}" >/dev/null 2>&1; then
  echo "Assessment ${assessment_id} is already stored."
else
  curl --fail --silent --show-error \
    --request POST \
    --header "Content-Type: application/json" \
    --data-binary "@${project_root}/data/seed/sample-assessment.json" \
    "${api_base_url}/api/assessments" >/dev/null
  echo "Stored assessment ${assessment_id}."
fi

curl --fail --silent --show-error \
  "${api_base_url}/api/assessments/${assessment_id}" >/dev/null
curl --fail --silent --show-error \
  "${api_base_url}/api/industry-templates/${template_id}" >/dev/null
curl --fail --silent --show-error \
  "${api_base_url}/api/source-types/${source_type_id}" >/dev/null

echo "Phase 1 round-trip verified: assessment, template, and source type are readable."
