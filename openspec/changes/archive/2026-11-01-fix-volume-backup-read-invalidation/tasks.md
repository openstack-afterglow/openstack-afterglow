## 1. Diagnosis and cutover

- [x] 1.1 Inspect recent local Docker request/error logs without secrets and reproduce all-200 browser failure.
- [x] 1.2 Migrate policy listing backend/frontend/tests from POST to GET without changing authority or global mutation fences.
- [x] 1.3 Suppress successful-empty backup artwork after list failures.

## 2. Evidence and documentation

- [x] 2.1 Run focused backend57 and real-client frontend16 regressions and isolated Uvicorn/SDK/browser failure/success smoke. Frontend check/build passed; full suite not rerun.
- [x] 2.2 Update API/testing/architecture documentation with actual evidence and deployment boundary. No schema/config/native data change; matched backend/frontend deployment remains unperformed.
- [x] 2.3 Strict validation passed; synchronize new read-isolation spec and archive completed source-only change using the OpenSpec archive command.
