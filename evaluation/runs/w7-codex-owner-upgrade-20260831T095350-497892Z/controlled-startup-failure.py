#!/usr/bin/env python3
import json
import sys
request = json.loads(sys.stdin.readline())
print(json.dumps({'jsonrpc': '2.0', 'id': request.get('id'), 'error': {'code': -32099, 'message': 'controlled startup fault'}}), flush=True)
