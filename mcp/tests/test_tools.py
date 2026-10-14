import json
from unittest.mock import AsyncMock

import httpx
import pytest

from data_eyes_mcp import config, tools


@pytest.fixture
def captured(fleet, monkeypatch):
    mock = AsyncMock(return_value=[])
    monkeypatch.setattr(tools, 'prometheus', mock)
    return mock


async def test_tool_catalog_has_no_sql_access(fleet):
    listing = {t.name for t in await tools.mcp.list_tools()}
    assert listing == {'list_configured_instances', 'fleet_overview', 'instance_checks', 'list_databases',
                       'list_metrics', 'query_metric', 'metric_history', 'get_latest_snapshot', 'get_severity_trend'}


async def test_unauthorized_queries_never_reach_prometheus(captured):
    result = json.loads(await tools.query_metric(instance='prod', metric='sql_cpu_pct'))
    assert 'error' in result
    captured.assert_not_called()
    assert 'Prod' not in result['error']


async def test_fleet_filters_before_querying(captured):
    result = json.loads(await tools.fleet_overview())
    assert [i['instance'] for i in result['instances']] == ['dev', 'beta']
    assert all('prod' not in str(call) for call in captured.call_args_list)
    assert all(i['availability'] == 'not_currently_collected' for i in result['instances'])


async def test_query_is_scoped_and_label_injection_is_escaped(captured):
    database = 'x"} or data_eyes_instance_info or {x="'
    result = json.loads(await tools.query_metric(instance='dev', metric='sql_cpu_pct', database=database))
    query = captured.call_args_list[0].args[0]
    assert 'sql_instance="dev"' in query and 'environment="development"' in query
    assert 'database=' + json.dumps(database) in query
    assert result['unit'] == 'percent'
    assert result['series'] == []  # missing is never a fabricated zero


@pytest.mark.parametrize('metric,operation', [('up or vector(1)', 'value'), ('sql_cpu_pct', 'rate'), ('sql_cpu_pct', 'sum')])
async def test_reject_arbitrary_queries(captured, metric, operation):
    assert 'error' in json.loads(await tools.query_metric(instance='dev', metric=metric, operation=operation))
    captured.assert_not_called()


async def test_history_bounds_and_counter_rate(captured):
    result = json.loads(await tools.metric_history(instance='dev', metric='batch_requests_total', operation='rate', hours=720))
    query, start, end, step = captured.call_args_list[0].args
    assert query.startswith('rate(data_eyes_batch_requests_total{') and query.endswith('[5m])')
    assert end - start == 720 * 3600
    assert (end - start) / step <= 120
    assert result['unit'] == 'requests/second'
    captured.reset_mock()
    for hours in (0, 721, float('nan')):
        assert 'error' in json.loads(await tools.metric_history(instance='dev', metric='sql_cpu_pct', hours=hours))
    captured.assert_not_called()


async def test_freshness_uses_collection_time_not_query_time(captured):
    captured.return_value = [
        {'metric': {'__name__': 'data_eyes_collection_' + key, 'collector': 'cpu'}, 'value': [2000, str(value)]}
        for key, value in [('success', 1), ('fresh', 1), ('last_success_timestamp_seconds', 1000)]]
    result = await tools.freshness('dev')
    assert result['cpu']['last_success_timestamp_seconds'] == 1000
    assert result['cpu']['status'] == 'fresh'
    captured.return_value[1]['value'][1] = '0'
    assert (await tools.freshness('dev'))['cpu']['status'] == 'unavailable_or_stale'
    captured.return_value = []
    assert await tools.freshness('dev') == {}


async def test_severity_history_keeps_original_permission(captured, monkeypatch):
    monkeypatch.setattr(config.settings, 'DEFAULT_PRINCIPAL', 'bob')
    assert 'error' in json.loads(await tools.get_severity_trend(instance='dev'))
    captured.assert_not_called()


def test_non_finite_measurements_and_output_limit(monkeypatch):
    assert tools.number('NaN') is None
    monkeypatch.setattr(config.settings, 'MAX_RESPONSE_BYTES', 1024)
    with pytest.raises(ValueError, match='too large'):
        tools.encode({'rows': ['x' * 2000]})


async def test_prometheus_transport_and_size_limit(fleet, monkeypatch):
    real_client = httpx.AsyncClient
    def handler(request):
        assert request.url.params['timeout'] == '15s'
        return httpx.Response(200, json={'status': 'success', 'data': {'result': []}})
    monkeypatch.setattr(tools.httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    assert await tools.prometheus('test') == []
    monkeypatch.setattr(config.settings, 'MAX_RESPONSE_BYTES', 10)
    with pytest.raises(ValueError, match='too large'):
        await tools.prometheus('test')
