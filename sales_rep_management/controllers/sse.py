# -*- coding: utf-8 -*-
"""
SSE (Server-Sent Events) Controller for Trackly Mobile App.

Provides a streaming endpoint built directly into Odoo — no separate server needed.
Mobile clients connect to GET /api/mobile/sse?token=<bearer> and receive
real-time 'sync_required' events when data changes.
"""

import json
import logging
import queue
import threading
import time

from odoo import http
from odoo.http import request
from .utils import SalesRepUtils

_logger = logging.getLogger(__name__)

# ── In-Memory Event Queues ─────────────────────────────────────────────
# { sales_rep_id: [queue.Queue, ...] }  — one queue per connected client
_sse_clients = {}
_sse_lock = threading.Lock()


def notify_sales_rep(sales_rep_id, reason='data_changed', event_type='sync_required', skip_sales_rep_id=None):
    """
    Push an event to all SSE clients of a given sales rep.
    """
    if skip_sales_rep_id and sales_rep_id == skip_sales_rep_id:
        return

    with _sse_lock:
        queues = _sse_clients.get(sales_rep_id, [])
        pushed = 0
        for q in queues:
            try:
                q.put_nowait({'type': event_type, 'reason': reason})
                pushed += 1
            except queue.Full:
                pass
        if pushed:
            _logger.info(f"SSE: Pushed '{event_type}' ({reason}) to {pushed} client(s) of sales_rep {sales_rep_id}")


def notify_all(reason='data_changed', event_type='sync_required', skip_sales_rep_id=None):
    """
    Push an event to ALL connected clients.
    """
    with _sse_lock:
        # clients_count is the total number of connected SSE queues across all reps
        total_connections = sum(len(q_list) for q_list in _sse_clients.values())
        _logger.debug(f"SSE: notify_all called. Connected reps: {len(_sse_clients)}. Total connections: {total_connections}. Reason: {reason}")
        
        total_pushed = 0
        for rep_id, queues in list(_sse_clients.items()):  # Use list() to avoid mutation during iteration
            if skip_sales_rep_id and rep_id == skip_sales_rep_id:
                continue
            for q in queues:
                try:
                    q.put_nowait({'type': event_type, 'reason': reason})
                    total_pushed += 1
                except queue.Full:
                    pass
        
        if total_pushed:
            _logger.info(f"SSE: Broadcasted '{event_type}' ({reason}) to {total_pushed} client(s) (Skipped {skip_sales_rep_id} if set)")
        else:
            _logger.debug(f"SSE: No active clients notified for '{reason}'")


class SSEController(http.Controller, SalesRepUtils):

    @http.route('/api/mobile/sse', type='http', auth='public', methods=['GET'], cors='*', csrf=False)
    def sse_stream(self, **kwargs):
        """
        SSE streaming endpoint.
        GET /api/mobile/sse?token=<bearer_token>

        The client connects and receives events as they happen.
        A heartbeat comment is sent every 25s to keep the connection alive.
        """
        # ── Auth ───────────────────────────────────────────────────
        token = kwargs.get('token')
        if not token:
            auth_header = request.httprequest.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ', 1)[1]

        if not token:
            return request.make_response(
                'data: {"error": "Missing token"}\n\n',
                headers={'Content-Type': 'text/event-stream'}, status=401
            )

        sales_rep = self._authenticate_token(token)
        if not sales_rep:
            return request.make_response(
                'data: {"error": "Invalid token"}\n\n',
                headers={'Content-Type': 'text/event-stream'}, status=401
            )

        rep_id = sales_rep.id
        rep_name = sales_rep.name

        # ── Register client queue ──────────────────────────────────
        client_queue = queue.Queue(maxsize=50)

        with _sse_lock:
            if rep_id not in _sse_clients:
                _sse_clients[rep_id] = []
            _sse_clients[rep_id].append(client_queue)

        _logger.info(f"SSE: Client connected — sales_rep {rep_id} ({rep_name}), "
                      f"{len(_sse_clients[rep_id])} total connection(s)")

        # ── Close the Odoo cursor before streaming ─────────────────
        # We don't need DB access during the stream, and holding the
        # cursor would block a DB connection for the entire session.
        try:
            request.env.cr.close()
        except Exception:
            pass

        # ── Stream generator ───────────────────────────────────────
        def event_stream():
            try:
                # Send initial connected event
                yield f"event: connected\ndata: {json.dumps({'sales_rep_id': rep_id, 'name': rep_name})}\n\n"

                while True:
                    try:
                        # Block for up to 25s waiting for an event
                        event = client_queue.get(timeout=25)
                        yield f"event: sync_required\ndata: {json.dumps(event)}\n\n"
                    except queue.Empty:
                        # Send heartbeat to keep connection alive
                        yield ": heartbeat\n\n"

            except GeneratorExit:
                _logger.info(f"SSE: Client disconnected (GeneratorExit) — sales_rep {rep_id}")
            except Exception as e:
                _logger.warning(f"SSE: Stream error for sales_rep {rep_id}: {e}")
            finally:
                # ── Cleanup ────────────────────────────────────────
                with _sse_lock:
                    if rep_id in _sse_clients:
                        try:
                            _sse_clients[rep_id].remove(client_queue)
                        except ValueError:
                            pass
                        if not _sse_clients[rep_id]:
                            del _sse_clients[rep_id]
                _logger.info(f"SSE: Cleaned up — sales_rep {rep_id}")

        # ── Return streaming response ──────────────────────────────
        import werkzeug.wrappers
        return werkzeug.wrappers.Response(
            event_stream(),
            content_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            }
        )
