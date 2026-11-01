## Correction
- [x] Reproduce real-client group GET invalidation by overlapping member PUT.
- [x] Replace invalidated read with one fresh scoped read without hiding actual errors.
- [x] Verify real-client regression and isolated architecture review; production browser incident remains uncorrelated because relay is unavailable.
