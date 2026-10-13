"""Extract credential-free MCP access policy from the legacy fleet file.

Run once: uv run --project mcp python scripts/migrate_monitoring_access.py
The original fleet file is left intact; only the collector may mount it.
Existing destination files are never overwritten. Nothing secret is printed.
"""
import argparse
from pathlib import Path
import yaml

TOOLS = ['list_configured_instances', 'fleet_overview', 'instance_checks', 'list_metrics',
         'query_metric', 'metric_history', 'get_latest_snapshot', 'get_severity_trend', 'list_databases']


def migrate(source, destination):
    data = yaml.safe_load(source.read_text(encoding='utf-8')) or {}
    instances = [{k: row[k] for k in ('name', 'label', 'environment') if k in row}
                 for row in data.get('instances', [])]
    principals = (data.get('mcp_security') or {}).get('principals') or {}
    result = {}
    for name, policy in principals.items():
        result[name] = {k: v for k, v in policy.items() if k in ('instances', 'token_sha256')}
        # The migration retains principal instance scope; the new grant is monitoring-only.
        result[name]['tools'] = TOOLS if policy.get('tools') else []
    with destination.open('x', encoding='utf-8') as out:
        yaml.safe_dump({'instances': instances, 'mcp_security': {'principals': result}}, out, sort_keys=False)
    print('Created credential-free MCP access policy; source fleet file unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('instances.yaml'))
    parser.add_argument('--destination', type=Path, default=Path('mcp-access.yaml'))
    args = parser.parse_args()
    migrate(args.source, args.destination)
