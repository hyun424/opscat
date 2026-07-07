# P6 agentic eval fixtures

`scripts/run_agentic_evals.py` scores the existing golden scenarios across P6 dimensions: correlation, root-cause match, runbook/action selection, risk classification, unsafe action blocking, and recovery verification. Outputs are written to temp paths by `scripts/verify.sh` and are not committed by default.
