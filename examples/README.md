# Examples

Everything here is exercised by the test suite (`tests/test_examples.py`), so
these files and commands keep working as the application changes. None of them
contains a credential: secrets are always passed through environment variables.

| File | What it shows |
|---|---|
| [`requirements.md`](requirements.md) | A requirements document `batman requirements import` understands. |
| [`api/users-api.yaml`](api/users-api.yaml) | An API test with authentication from the environment, a schema, a chained request, and an anonymous-access check. |

## A first session, end to end

Run these from the root of a clone, after installing (`uv tool install .`).
Each step prints what it did; nothing leaves your machine.

```bash
# 1. A project to hold the records (the data folder is created for you).
batman project create "Checkout service" --repository https://gitlab.example.com/acme/checkout

# 2. Requirements, with where they came from.
batman requirements import examples/requirements.md -p PROJ-001

# 3. A test case that covers one of them, then a human review of it.
batman cases create "Customer can pay by card" -p PROJ-001 \
  --objective "Validate payment with a valid card" \
  --step "Open the checkout => The payment form is shown" \
  --step "Pay with a valid card => The order is confirmed" \
  --expected-result "The customer sees the order confirmation" \
  --requirement REQ-001
batman review submit TC-001 -p PROJ-001
batman review decide TC-001 -p PROJ-001 --decision approved --reviewer Ana

# 4. Which requirements still have no test?
batman requirements coverage -p PROJ-001

# 5. A suite, and an execution of the case.
batman suites create Smoke -p PROJ-001 --type smoke --case TC-001
batman executions create -p PROJ-001 --type manual --executor Ana \
  --environment staging --case TC-001
```

Then open the workbench with `batman` and look at Overview, Requirements, Test
Cases, Test Suites, and Executions: they read the same records.

## Using the integrations safely

External access is opt-in and scoped. A project only reaches the hosts you allow,
and anything that writes to an external system waits for a person.

```bash
# Allow the hosts this project may reach, and pick how cautious the workbench is.
batman security set -p PROJ-001 --mode assisted --allow-host staging.example.com --by Ana

# Run the API example (set API_TOKEN first; the token is never stored).
batman api run examples/api/users-api.yaml -p PROJ-001

# Read the latest pipelines from GitLab (GITLAB_TOKEN needs the read_api scope).
batman gitlab pipelines -p PROJ-001 --status failed

# Publishing a comment needs evidence, then a person's approval of that exact text.
batman comments draft 7 -p PROJ-001 --author "QA Agent" --evidence EVD-001 \
  --body "Login works on staging 1.4.2. Evidence attached."
batman comments publish COMMENT-001 -p PROJ-001      # asks for approval
batman security approve APR-xxxxxxxx -p PROJ-001 --by Ana
batman comments publish COMMENT-001 -p PROJ-001      # now it is posted
```

Security checks need an explicit, expiring authorization first, and they are
passive: they read responses and never send payloads.

```bash
batman security-tests authorize -p PROJ-001 --by Ana \
  --purpose "Hardening before release 1.5" --host staging.example.com --days 2
batman security-tests run https://staging.example.com/ -p PROJ-001
```
