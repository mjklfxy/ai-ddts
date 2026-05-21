# RPA Jikeyun Design

## Goal

Enable an experimental RPA step for JackYun order runs without changing the default behavior of the existing pipeline.

## Design

The order source remains `jikeyun` for OpenAPI order data. A new `rpa` configuration section controls whether the desktop automation export runs before JackYun records are mapped with XLSX fallback data. When `rpa.enabled` is false, the client reads the configured XLSX path exactly as before and never touches the desktop.

When `rpa.enabled` is true, application assembly injects `infrastructure.db_to_xlsx.export_orders_to_xlsx` into `JikeyunClient`. The client calls that exporter after OpenAPI pages are fetched and before `load_order_address_lookup()` reads the XLSX fallback file. Export errors are logged and ignored so an RPA problem does not break the whole task; the task continues with the last available XLSX file or an empty lookup.

## Files

- `application/config_service.py`: parse and serialize `rpa.enabled` and `rpa.xlsx_path`.
- `application/manual_runner.py`: inject the RPA exporter only when enabled.
- `infrastructure/jikeyun_client.py`: accept optional RPA exporter and XLSX path.
- `config/config.json`: enable the experiment on the current branch.

## Testing

Add focused tests for config parsing and client behavior. Existing full-suite failures are known baseline failures unrelated to RPA.
