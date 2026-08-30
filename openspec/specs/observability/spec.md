# observability Specification

## Purpose

Make a request traceable from the HTTP call that started it, through four asynchronous
queue hops, to the log line that explains what happened. Azure Storage Queues do not
propagate trace context, so the system injects and extracts it explicitly. Logs are
one-line JSON carrying Datadog trace and span ids plus the domain correlation id, and
dependency noise is suppressed so the signal survives.

## Requirements

### Requirement: Correlation Identifiers

The system SHALL attach a correlation identifier to search, pipeline, and collection
operations, propagate it across asynchronous hops, and echo it in the corresponding
response and log lines, so a single request can be traced end to end.

#### Scenario: Search request

- **WHEN** a search request is handled
- **THEN** a correlation id is generated, logged with the request and completion lines, and returned in the response

#### Scenario: Pipeline message

- **WHEN** a document flows through the queue-driven pipeline
- **THEN** the correlation id travels in the queue message envelope and appears in each stage's log lines

#### Scenario: Request-scoped propagation

- **WHEN** a queue trigger begins processing
- **THEN** the envelope's correlation id is bound to a context variable for the duration of the handler, so log records emitted anywhere in the async call chain carry it without being passed explicitly

#### Scenario: Context is unbound afterwards

- **WHEN** the handler completes or raises
- **THEN** the context variable is reset, so a correlation id cannot leak into an unrelated invocation on the same worker

### Requirement: Structured JSON Logging

The system SHALL emit one-line JSON log records by default, so a log pipeline can parse
fields reliably.

#### Scenario: Record fields

- **WHEN** a log record is emitted in JSON mode
- **THEN** it carries `timestamp`, `level`, `logger`, `message`, `module`, `function`, `line`, `service`, `source`, `env`, and `version`

#### Scenario: Newlines are escaped

- **WHEN** a message or formatted exception contains carriage returns or newlines
- **THEN** they are escaped so the record stays on a single line and cannot be split into several apparent log entries

#### Scenario: Exceptions

- **WHEN** a record carries exception info
- **THEN** the formatted traceback is included as a single-line `exception` field

#### Scenario: Correlation id attached when present

- **WHEN** a correlation id is bound to the current context
- **THEN** it is included as `correlation_id`

#### Scenario: Plain format

- **WHEN** `LOG_FORMAT` is not `json`
- **THEN** a human-readable single-line console format is used instead

#### Scenario: Log level

- **WHEN** `LOGGING_LEVEL` is set
- **THEN** it becomes the root logger level, defaulting to `INFO`

### Requirement: Trace And Log Correlation

The system SHALL stamp log records with the active Datadog trace and span ids so logs
and traces join in the backend.

#### Scenario: Trace ids present on the record

- **WHEN** the logging integration has already attached `dd.trace_id` and `dd.span_id` to the record
- **THEN** those values are copied into the JSON payload

#### Scenario: Trace ids resolved from the tracer

- **WHEN** the record carries no trace ids but a tracer is active
- **THEN** the ids are read from the tracer's log-correlation context and included

#### Scenario: Tracer unavailable

- **WHEN** `ddtrace` is not installed
- **THEN** logging still works and the trace fields are simply absent

### Requirement: Queue Trigger Trace Stitching

The system SHALL link each queue-trigger invocation to the trace of the request that
enqueued it, because the queue transport does not carry trace context on its own.

#### Scenario: Producer injects context

- **WHEN** a pipeline message is published
- **THEN** the current trace context is injected into the envelope's `_datadog` field

#### Scenario: Consumer opens a child span

- **WHEN** a trigger receives a message carrying a usable `_datadog` context
- **THEN** a child span of the originating trace is opened for the invocation

#### Scenario: Message predating trace propagation

- **WHEN** a message carries no `_datadog` context
- **THEN** a root span is opened instead, so older queued messages still process

#### Scenario: Span tags

- **WHEN** a trigger span is opened
- **THEN** it is named `queue.<queue_name>_trigger` and tagged with `queue.name`, `messaging.system`, `file_id`, `tenant_id`, and `correlation_id`

#### Scenario: Failures recorded on the span

- **WHEN** the handler raises
- **THEN** the exception is recorded on the span before being re-raised

#### Scenario: Tracing unavailable

- **WHEN** `ddtrace` cannot be imported
- **THEN** the trigger runs unwrapped rather than failing, so local development without an agent still works

### Requirement: Tracer Bootstrap

The system SHALL initialize Datadog auto-instrumentation inside the Python worker
process before importing application modules, because the Functions host may run the
worker separately from the container entrypoint.

#### Scenario: Auto-instrumentation

- **WHEN** the function app module loads
- **THEN** `ddtrace.auto` is imported first, enabling the supported integrations

#### Scenario: Container Apps metadata present

- **WHEN** the Azure subscription and resource group environment variables are set
- **THEN** the Datadog serverless compatibility layer is started as well

#### Scenario: Bootstrap failure is non-fatal

- **WHEN** the Datadog bootstrap raises for any reason
- **THEN** a warning is logged and the application continues to start

#### Scenario: Traces flushed on shutdown

- **WHEN** the process exits
- **THEN** container resources are released and the tracer is flushed on a best-effort basis

### Requirement: Log And Trace Noise Suppression

The system SHALL suppress known non-actionable output from dependencies, so operational
signal is not buried.

#### Scenario: Chatty dependency loggers

- **WHEN** logging is configured
- **THEN** the Azure SDK, `httpx`, `httpcore`, `urllib3`, `python_multipart`, and Azure Functions worker loggers are set to the configured SDK log level, defaulting to `WARNING`

#### Scenario: Tracer's own logs

- **WHEN** logging is configured
- **THEN** the `ddtrace` logger is set to its own configured level, defaulting to `WARNING`

#### Scenario: Connection-lifecycle spans dropped

- **WHEN** traces are processed
- **THEN** spans named in `DD_APM_IGNORE_RESOURCES` are dropped, defaulting to the pyodbc commit and rollback spans, and a trace left empty by that filtering is dropped entirely

#### Scenario: Ignore list accepts regex-escaped names

- **WHEN** `DD_APM_IGNORE_RESOURCES` uses the escaped-dot form of a span name
- **THEN** it is unescaped before comparison, so the official regex syntax and the literal form both work

#### Scenario: Known library warnings

- **WHEN** logging is configured
- **THEN** the Chonkie tokenizer-fallback `UserWarning` and the Azure Search generated-model `SyntaxWarning` are filtered out
