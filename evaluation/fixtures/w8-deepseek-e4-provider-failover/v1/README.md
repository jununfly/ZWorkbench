# DeepSeek E4 Provider failover candidate fixture

This is an acceptance/evaluation fixture, not ZWorkbench product code.

It drives pinned `dsh-llm-failover` and `dsh-model-failover` source through a
minimal official-looking DeepSeek Harness seam. The seam injects a deterministic
`RATE_LIMIT` failure on a loopback-only route, then observes the candidate's
Provider/model selection, cooldown behavior, event/log surface, and whether a
candidate-owned durable fallback-reason record exists.

The fixture deliberately keeps these questions separate:

1. Did the candidate actually select a second model Provider?
2. Did it classify the failure and expose the selected/fallback identity?
3. Did it fail closed when all routes were cooling down?
4. Did it persist a durable fallback/degradation reason ledger?

The last item is a hard E4 requirement. `dsh-search-failover` and
`dsh-routing-suite` remain negative controls because their fallback/routing
semantics do not select a model Provider after a model request failure.

The runner reads candidate files from a separately pinned, read-only checkout;
it does not install from a registry or modify that checkout. Any copied source
and generated evidence are written below the new case-local output directory.
