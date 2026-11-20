# Codex usage dashboard

Local dashboard for per-response Codex tokens, cached input, estimated cost, and usage by task. The chart includes token gridlines and response ticks. UI language: Vietnamese.

## Install (Linux)

Requires Git, Python 3.9+ with system timezone data, curl, xdg-open, and systemd user services. No Python packages required.

```sh
git clone https://github.com/MustangNguyen/codexusage.git
cd codexusage
./install.sh
```

Open a new terminal and run `codexusage`. To run immediately in the current terminal, use `~/.local/bin/codexusage`.

The installer uses the checkout's current location, installs the launcher into `~/.local/bin`, configures and starts a systemd user service, and adds PATH setup to Bash/login profiles (and Zsh when detected). No sudo required. Keep the checkout in place; if you move it, rerun `./install.sh` from its new location. Rerunning also updates an existing installation without duplicating PATH entries. The `.service` file is a template rendered by the installer; do not copy it directly.

Open http://127.0.0.1:8766 in a browser on this computer. For manual launch, run `python3 server.py --port 8766` from the checkout (stop an existing service first).

The user service starts on login. Manage it with:

```sh
systemctl --user status codex-usage-dashboard
systemctl --user restart codex-usage-dashboard
systemctl --user disable --now codex-usage-dashboard
```

The server binds to loopback only, uses the Python standard library, and reads
`~/.codex/sessions`, `~/.codex/archived_sessions`, and task titles from the
read-only `state_5.sqlite` connection. The local API includes usage records and task titles; titles can contain prompt text. Keep the server on loopback. Generated `cache/` data is private and excluded from Git.
Usage is refreshed every three seconds after records are written, not per streamed token.
The first index scan can take longer. Incremental scans retain incomplete lines for retry.
Records are deduplicated by response ID. Totals use per-response usage, never cumulative
turn/thread totals. Days use Asia/Bangkok. Logs without token_usage_record are not counted;
missing records mean coverage may be incomplete, not zero usage.

Default estimates use official OpenAI Standard rates verified on 2026-11-19, multiplied by 0.2. Bundled models: gpt-6.1-sol, gpt-5.6-sol, gpt-5.6-luna, gpt-5.6-terra. Sources: https://developers.openai.com/api/docs/models/ followed by each exact model name. These are a dated snapshot, not automatically refreshed. Rates and the multiplier can be edited and are stored together in browser localStorage (codex-usage-pricing-v2). Legacy custom prices are left untouched in the old key; copy them manually if needed. Enter rates in USD per million
tokens by exact model name in the gateway price section:

```json
{"YOUR_MODEL":{"input":1,"cached":0.1,"output":5,"write":1}}
```

These numbers are examples, not real provider rates. The calculation assumes cached
and cache-write tokens are disjoint subsets of input, with all remaining input billed
at the input rate. If that assumption is invalid for your provider, adapt the calculator.
Missing rates display “Chưa có giá”; negative residual input also prevents an estimate.
Reasoning is included in output and is not added again. Model attribution comes from
local turn_context or usage payloads, and is not proof of the gateway's billing model.
For bundled models, input above 272,000 tokens applies 2x input/cache/write and 1.5x output to the entire request before the user multiplier. Cache-write assumes the 30-minute rate because usage records do not identify retention. Tool fees and service-tier adjustments are not included. Estimates apply the current configured rate snapshot to historical records as well; they are not historical invoices.

## Tests

```sh
python3 -m unittest -v
```

This tool counts `token_usage_record` entries. Codex versions that do not emit these records may show no usage. Pricing is editable; estimates are not invoices.
