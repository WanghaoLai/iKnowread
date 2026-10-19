"""Check exception containment with ASGI propagation enabled."""
import asyncio
import unittest
from unittest.mock import patch

import httpx

from app import create_app
from app.config import settings
from app.common.exception_handler import SafeErrorMiddleware
from app.upload_guard import UploadConcurrencyMiddleware


class ErrorBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def make_app(self):
        with (
            patch.object(settings, 'CORS_ORIGINS', 'https://reader.example'),
            patch.object(settings, 'UPLOAD_CONCURRENCY', 1),
            patch.object(settings, 'UPLOAD_QUEUE_WAIT_SECONDS', 0.01),
        ):
            return create_app()

    async def test_secret_exception_is_contained_once_with_cors(self):
        app = self.make_app()

        async def explode():
            request = httpx.Request('GET', 'https://upstream.example/?key=secret-marker')
            raise httpx.HTTPStatusError(
                'upstream failed: secret-marker', request=request,
                response=httpx.Response(500, request=request),
            )

        app.add_api_route('/__failure', explode)
        # Keep raise_app_exceptions=True: a 500 response alone cannot prove
        # that Uvicorn will never receive the original exception.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url='http://test'
        ) as client:
            with self.assertLogs(level='WARNING') as captured:
                response = await client.get('/__failure', headers={'Origin': 'https://reader.example'})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.headers['access-control-allow-origin'], 'https://reader.example')
        self.assertTrue(response.headers['x-request-id'])
        self.assertEqual(len(captured.records), 1)
        self.assertNotIn('secret-marker', '\n'.join(captured.output) + response.text)
        self.assertIsNone(captured.records[0].exc_info)

    async def test_upload_gate_429_has_cors_and_request_id(self):
        app = self.make_app()
        entered, release = asyncio.Event(), asyncio.Event()

        async def hold():
            entered.set()
            await release.wait()
            return {'ok': True}

        gate = next(item for item in app.user_middleware if item.cls is UploadConcurrencyMiddleware)
        gate.kwargs['paths'] = {'/__upload'}
        app.add_api_route('/__upload', hold, methods=['POST'])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url='http://test'
        ) as client:
            first = asyncio.create_task(client.post('/__upload'))
            try:
                await asyncio.wait_for(entered.wait(), 2)
                response = await client.post('/__upload', headers={'Origin': 'https://reader.example'})
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.headers['access-control-allow-origin'], 'https://reader.example')
                self.assertIn('retry-after', response.headers)
                self.assertIn('x-request-id', response.headers)
            finally:
                release.set()
                await first

    async def test_stream_failure_propagates_only_sanitized_exception(self):
        async def streaming(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            raise RuntimeError('secret-stream-marker')

        async def send(message):
            pass

        with self.assertLogs('app.common.exception_handler', level='ERROR') as captured:
            with self.assertRaises(RuntimeError) as caught:
                await SafeErrorMiddleware(streaming)({'type': 'http'}, None, send)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn('secret-stream-marker', str(caught.exception) + '\n'.join(captured.output))
