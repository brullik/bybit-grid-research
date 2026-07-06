# Sprint 01 API Report

Updated UTC: 2026-07-06T19:12:32.743417+00:00

## Runs

### validate_sample_grid --dry-run — dry-run

- started_at: 2026-07-06T19:12:25.194035+00:00
- ended_at: 2026-07-06T19:12:25.194735+00:00
- counts: `{}`
- output_paths: `["data/metadata/grid_validate_redacted.json"]`
- error_summary: none

#### command

validate_sample_grid --dry-run

#### ended_at

2026-07-06T19:12:25.194735+00:00

#### grid validate status

dry-run; no network request

#### output_paths

['data/metadata/grid_validate_redacted.json']

#### started_at

2026-07-06T19:12:25.194035+00:00

#### status

dry-run

### smoke_public_api — network-blocked

- started_at: 2026-07-06T19:12:28.981613+00:00
- ended_at: 2026-07-06T19:12:32.743172+00:00
- counts: `{}`
- output_paths: `[]`
- error_summary: 403 Forbidden

#### command

smoke_public_api

#### ended_at

2026-07-06T19:12:32.743172+00:00

#### error_summary

403 Forbidden

#### network diagnostic

{'base_url': 'https://api.bybit.com', 'body_first_500': '', 'exception_type': 'ProxyError', 'proxy_or_bybit': 'proxy', 'recommended_pm_action': 'verify that target network can reach Bybit API before private calls', 'status': None}

#### started_at

2026-07-06T19:12:28.981613+00:00

#### status

network-blocked
