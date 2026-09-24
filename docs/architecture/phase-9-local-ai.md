# Phase 9: local AI review

Phase 9 adds an optional local Ollama integration for authenticated security analysts. It is deliberately outside the execution authorization path.

## Flow

1. The frontend checks `GET /api/v1/local-ai/status` for the configured model.
2. An authenticated user submits bounded text to `POST /api/v1/local-ai/classify`.
3. FastAPI sends the text directly to the configured Ollama endpoint with proxy inheritance disabled.
4. Ollama returns JSON constrained by the classification schema.
5. AgentGuard validates the complete response before returning an explicitly advisory result.
6. The audit log records the action, model name, advisory flag, and input character count. It never stores the input, rationale, categories, or confidence.

## Security boundary

Local AI is unavailable to unauthenticated callers and accepts at most 8,000 characters. Generation is bounded and configured with temperature zero and a fixed seed for repeatability, though model output remains probabilistic. Invalid, unavailable, missing-model, and timed-out responses fail explicitly.

The classifier cannot create a policy decision, finding, approval, or execution. Deterministic identity, permission, detector, policy, approval, and reliability controls remain the only source of execution authority. No model result can weaken or override a denial.

## Configuration

- `AGENTGUARD_OLLAMA_BASE_URL` defaults to `http://127.0.0.1:11434`.
- `AGENTGUARD_OLLAMA_MODEL` defaults to `llama3.2:3b`.
- `AGENTGUARD_OLLAMA_TIMEOUT_SECONDS` defaults to 60 seconds.

The Ollama endpoint should remain bound to the local machine or a private trusted network. AgentGuard does not send local AI input through environment-configured HTTP proxies.
