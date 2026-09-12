# Rule-Based Engine and ML Engine Pipeline

## Purpose

The rule-based engine and ML engine work together to identify possible emission sources in an assessment.

The rule-based engine handles explicit, structured facts. The ML engine assists with free-text information and missing or unclear source information. Neither engine confirms a source or calculates emissions. Confirmation remains a user decision.

## Pipeline

```text
Company, facility and process information
        |
        v
Normalized assessment facts
        |
        +-----------------------------+
        |                             |
        v                             v
Rule-based engine                 ML engine
        |                             |
        |                             |
        +-------------+---------------+
                      v
             Candidate merge and deduplication
                      |
                      v
             Universal source checklist
                      |
                      v
                User source review
                      |
          +-----------+-----------+-------------+
          |                       |             |
       Confirmed               Outsourced   Not applicable /
          |                       |          Missing information
          v                       v             |
   Collect activity data   Keep as value-   Store status and reason
                           chain source
```

## 1. Input to both engines

The system first collects and normalizes information from the assessment:

- Industry and products
- Process steps
- Equipment
- Energy and fuel inputs
- Materials and chemicals
- Gases and refrigerants
- Waste and wastewater
- Transport activities
- Process and facility descriptions

Structured fields are passed directly to the rule engine. Descriptions and other text are also made available to the ML engine.

## 2. Rule-based engine

The rule engine checks explicit facts against the versioned source-identification rules.

For every matching rule, it creates a potential source candidate containing:

- Source type
- Process and equipment context
- Provisional scope
- Reason for the suggestion
- Rule ID and rule version
- Follow-up question
- `RULE` origin
- `PROPOSED` status

Example:

```text
Fact: A boiler uses diesel.
Rule match: Boiler + fuel present.
Suggestion: Stationary fuel combustion.
```

Rule suggestions are deterministic and explainable. A rule match does not mean that the source is confirmed.

## 3. ML engine

The ML engine reviews text and incomplete information for additional suggestions.

It can:

- Identify equipment or activities mentioned in descriptions.
- Recognize different names for the same equipment or activity.
- Suggest a possible source when an important detail is missing.
- Suggest follow-up questions for the user.

For every suggestion, it returns:

- Source type
- Process and equipment context, when available
- Explanation
- Confidence
- Evidence text
- Model ID and model version
- `ML` origin
- `PROPOSED` status

Example:

```text
Text: Finished products are stored in two cold rooms.
ML suggestion: Refrigerant fugitive emissions.
Reason: Refrigeration equipment is present, but refrigerant information is missing.
```

An ML suggestion is advisory only. It cannot confirm a source or create emissions data.

## 4. Candidate merge and deduplication

The system combines template, rule, ML, checklist and user-origin suggestions.

Candidates are deduplicated using the source type and its process/equipment context. When multiple engines identify the same source, the system keeps one candidate and preserves:

- Every origin
- Every triggering reason
- Every rule version
- Every model version
- All supporting evidence

Example:

```text
Stationary fuel combustion
Origins: TEMPLATE, RULE
Reasons:
- The industry template expects fuel use in this process.
- A diesel boiler was reported.
Rule versions: 1.0.0
```

The merged candidate remains `PROPOSED` or `MERGED`; it is not automatically confirmed.

## 5. Checklist and user review

The merged candidates are shown in the universal source checklist. Every source family receives a visible status.

The user then reviews each candidate and selects one of the allowed statuses:

- `CONFIRMED`
- `OUTSOURCED`
- `NOT_APPLICABLE`
- `MISSING_INFORMATION`
- `POTENTIAL`

The user may also provide a reason or confirmation note. This review creates or updates the source inventory while retaining the original candidate history.

## 6. What happens after review

Only confirmed sources proceed to activity-data collection. Outsourced sources remain visible as value-chain sources. Not-applicable and missing-information decisions retain their reasons and remain available for audit.

Activity data, emission factors, calculations and final profiles are handled by later pipeline stages. They are not produced by either the rule engine or the ML engine.

## 7. ML failure behavior

If the ML engine is unavailable or returns an invalid response:

1. The identification run records that ML was unavailable.
2. Rule and template identification continue normally.
3. The checklist is still generated.
4. The user can still review and confirm sources.

This ensures that ML improves source discovery without becoming a dependency for the core workflow.

## Summary

```text
Rules identify explicit sources.
ML identifies sources hidden in text or missing information.
The merger combines and explains all suggestions.
The user confirms the actual source status.
Only reviewed sources continue to quantification.
```
