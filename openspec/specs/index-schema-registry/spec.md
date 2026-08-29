# index-schema-registry Specification

## Purpose

Define, in one backend-agnostic place, which metadata fields each document category
indexes and how they behave (filterable, sortable, facetable, collection-valued). The
registry drives index creation, filter validation, and the typed metadata models, so
adding a document category is a declarative change rather than a scattered one.

## Requirements

### Requirement: Declarative Backend-Agnostic Field Specifications

The system SHALL describe index fields with a generic specification carrying a name, a
generic field type, and its filterable, sortable, facetable, and collection flags, with
no dependency on any search SDK in the core layer.

#### Scenario: Generic field types

- **WHEN** a field is declared
- **THEN** its type is one of `string`, `int32`, `boolean`, or `datetime`

#### Scenario: Backend conversion lives in infrastructure

- **WHEN** an index is created
- **THEN** an infrastructure mapper converts the generic specifications into backend-specific field definitions

#### Scenario: Sortable and facetable imply filterable

- **WHEN** a field is declared sortable or facetable without being filterable
- **THEN** the declaration is rejected at construction

#### Scenario: Collections cannot be sortable

- **WHEN** a multi-value field is declared sortable
- **THEN** the declaration is rejected at construction

### Requirement: Composed Per-Category Index Schemas

The system SHALL compose each document category's index schema from shared common
fields, shared chunk-level fields, and the category's own fields.

#### Scenario: Operational schema

- **WHEN** the schema for `operational` is requested
- **THEN** it contains the common fields, the chunk fields, and the operational fields `operation_number`, `sector`, `operation_type`, `dept_id`, `access_to_information_policy`, `document_publish_date`, and `document_approval_date`

#### Scenario: Publication schema

- **WHEN** the schema for `publication` is requested
- **THEN** it contains the common fields, the chunk fields, and the publication fields `journal`, `doi`, `issn`, `peer_reviewed`, and `publication_type`

#### Scenario: Unknown category

- **WHEN** a schema is requested for an unregistered category
- **THEN** an error naming the available categories is raised

#### Scenario: Category discovery

- **WHEN** the registered categories are listed
- **THEN** `operational` and `publication` are returned in sorted order

### Requirement: Schema Introspection Helpers

The system SHALL expose the filterable and sortable field sets and single-field lookup
for a category, so filter validation and UI construction share one source of truth.

#### Scenario: Filterable fields

- **WHEN** a category's filterable fields are requested
- **THEN** only fields declared filterable are returned

#### Scenario: Sortable fields

- **WHEN** a category's sortable fields are requested
- **THEN** only fields declared sortable are returned

#### Scenario: Field lookup

- **WHEN** a field is looked up by name in a category
- **THEN** its specification is returned, or null when the category does not define it

### Requirement: Typed Metadata Models Per Category

The system SHALL define a Pydantic metadata model per document category, sharing a base
of promoted fields, and SHALL use `document_category` as the discriminator that selects
the model.

#### Scenario: Base promoted fields

- **WHEN** any document is stored
- **THEN** the base model covers `document_category`, `document_type`, `language`, `country`, `year`, `document_author`, `document_name`, `document_url`, `disclosed`, `file_extension`, `access_to_information_policy`, `document_publish_date`, `document_approval_date`, `document_created_date`, `source`, `department`, `description`, and `tags`

#### Scenario: Model selection

- **WHEN** a `document_category` of `operational` or `publication` is supplied
- **THEN** the corresponding metadata model is used for validation and persistence

#### Scenario: Missing category

- **WHEN** `document_category` is absent
- **THEN** the operational model is used, because all existing documents are operational

#### Scenario: Unrecognised category

- **WHEN** `document_category` names a category with no registered model
- **THEN** the base metadata model is used

#### Scenario: Promoted field registry

- **WHEN** the promoted field names for a model are requested
- **THEN** every model field except the `file_id` identity key is returned

#### Scenario: Tag normalisation

- **WHEN** `tags` arrives as null, a comma-separated string, or a list
- **THEN** it is normalised to a list of trimmed non-empty strings

#### Scenario: Field bounds

- **WHEN** metadata is validated
- **THEN** `year` must be between 1900 and 2100 and each string field must respect its declared maximum length
