"""Monitoring routing is independent of model and SQL credentials."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.agent import answer
from app.mcp_tools import McpTools


class MonitoringTests(unittest.IsolatedAsyncioTestCase):
    def client(self):
        client = McpTools()
        for env in ('dev', 'prod'):
            client.sessions[env] = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(
                content=[SimpleNamespace(text='{"series": []}')], isError=False)))
            client.instance_env[env] = ['shared-name']
            client.tools[env + '_query_metric'] = {
                'description': 'metric', 'environment': env, 'remote_name': 'query_metric',
                'schema': {'type': 'object', 'properties': {'instance': {'type': 'string'}}, 'required': ['instance']}}
        return client

    async def test_same_instance_name_routes_by_environment(self):
        client = self.client()
        await client.run('prod_query_metric', {'instance': 'shared-name', 'metric': 'sql_cpu_pct'})
        client.sessions['prod'].call_tool.assert_awaited_once()
        client.sessions['dev'].call_tool.assert_not_awaited()
        definitions = client.definitions()
        self.assertEqual(len(definitions), 2)
        self.assertEqual(definitions[0]['schema']['properties']['instance']['enum'], ['shared-name'])

    async def test_unknown_instance_and_invalid_arguments_do_not_call_mcp(self):
        client = self.client()
        for arguments in ({'instance': 'unauthorized'}, []):
            self.assertIn('error', json.loads(await client.run('dev_query_metric', arguments)))
        client.sessions['dev'].call_tool.assert_not_awaited()

    async def test_unavailable_monitoring_does_not_call_provider(self):
        with patch('app.agent.McpTools') as factory, patch('app.agent._openai_compatible') as provider:
            factory.return_value.__aenter__.return_value = McpTools()
            emit = AsyncMock()
            await answer([{'role': 'user', 'content': 'Health?'}], emit)
            provider.assert_not_called()
            self.assertIn('unavailable', emit.call_args.args[1])
