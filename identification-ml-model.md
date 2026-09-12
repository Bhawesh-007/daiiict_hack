# Identification-Layer ML Model

## Model selected

The project uses a local **TF-IDF cosine-similarity classifier** named `taxonomy-tfidf-cosine`, version `1.0.0`.

It is implemented in `services/identification-api/app/identification/ml_model.py` and exposed to the identification orchestrator through `ml_adapter.py`.

## Why this model

The repository currently has no labelled company dataset large enough to train a reliable supervised classifier. This model instead learns its source vocabulary from the versioned source taxonomy: source names, aliases, family descriptions and scope guidance.

It provides a useful MVP because it is:

- local and does not require an API key;
- deterministic and reproducible;
- fast enough to run during an identification request;
- explainable through similarity scores and matched input text;
- versioned with the source taxonomy;
- safe as an advisory model because it only creates proposed candidates.

## Inputs

The model receives normalized facts produced from:

- process steps;
- equipment names and types;
- fuel and energy types;
- input/output flow categories and item names;
- process and equipment descriptions.

## Outputs

For each sufficiently strong match it returns:

- source key, name and category;
- provisional scope;
- confidence score;
- process and equipment references;
- explanation;
- model ID and version;
- taxonomy version;
- fact type, input text and similarity score.

All model candidates use origin `ML` and are persisted as `PROPOSED`. The model never confirms a source.

Before candidate merging or persistence, `MLPersistenceCandidate` validates the taxonomy source key, confidence range, non-empty reason, model identity/version and evidence. Its status is a literal `PROPOSED`, so `CONFIRMED` and every other model-supplied status are rejected.

## Strict API contracts

The Pydantic contracts are defined in `services/identification-api/app/schemas/ml.py`. Inputs reject unknown fields, unsupported fact types, empty text and more than 500 facts. Outputs reject unknown taxonomy source keys, confidence outside 0–1, and missing reasons or model metadata.

The canonical output field is `follow_up_questions`. The accidental spelling `follow_up_questions_questions` is accepted only as an input alias for compatibility.

## Pipeline role

```text
Company facts
  -> industry templates
  -> deterministic rules
  -> TF-IDF ML suggestions
  -> candidate merge and deduplication
  -> user review
  -> confirmed source inventory
```

The model supports identification only. It does not create activity quantities, emission factors or emissions calculations.

## Safety boundaries

The model cannot:

- mark candidates as confirmed;
- invent activity data;
- calculate carbon dioxide equivalent;
- create or modify emission factors;
- override deterministic rules;
- modify reviewed inventory records.

When the model is disabled, the template and rule workflow continues with `ml_status = DISABLED`. If the model fails, identification continues with `ml_status = UNAVAILABLE`.

## Running it

Call the identification endpoint with:

```json
{
  "include_ml": true
}
```

For the stable baseline without ML, use `false`.

## Future upgrade

After collecting reviewed candidate decisions, build a labelled dataset containing the normalized fact text, accepted source key and rejection outcome. At that point the local model can be replaced with a supervised text classifier or an embedding model without changing the orchestrator contract.
