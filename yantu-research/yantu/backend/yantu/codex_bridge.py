"""Official Codex app-server over private stdio, with a home per research user."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time

from .agent_providers import AgentError


class CodexBridge:
    def __init__(self, directory, command=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workspace = self.directory / 'workspace'
        self.workspace.mkdir(exist_ok=True, mode=0o700)
        binary = command or os.getenv('CODEX_BINARY', 'codex')
        if not shutil.which(binary):
            raise AgentError("当前服务未安装 Codex 连接组件，请按部署说明更新应用镜像")
        # Never import the host's ChatGPT account, model credentials or config.
        env = {key: value for key, value in os.environ.items() if key in
               ('PATH', 'SystemRoot', 'TEMP', 'TMP', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY')}
        env['CODEX_HOME'] = str(self.directory)
        env['HOME'] = str(self.directory)
        self.process = subprocess.Popen([binary, 'app-server'], cwd=self.workspace, env=env,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1)
        self.lock, self.write_lock = threading.Lock(), threading.Lock()
        self.pending, self.subscribers = {}, {}
        self.counter, self.login = 0, None
        threading.Thread(target=self.read, daemon=True).start()
        self.rpc('initialize', {'clientInfo': {'name': 'yantu_research', 'title': '研途科研助手', 'version': '0.4.0'},
                                'capabilities': {'experimentalApi': True}})
        self.send({'method': 'initialized', 'params': {}})

    def send(self, message):
        try:
            with self.write_lock:
                self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
                self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise AgentError("Codex 连接已断开，请在设置中重新连接") from error

    def read(self):
        try:
            for line in self.process.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                ident, method = message.get('id'), message.get('method')
                if ident is not None and not method:
                    with self.lock:
                        target = self.pending.get(ident)
                    if target:
                        target.put(message)
                    continue
                params = message.get('params') or {}
                if method == 'account/login/completed' and self.login:
                    self.login = {**self.login, 'completed': True, 'success': bool(params.get('success')),
                                  'error': '' if params.get('success') else '登录未完成，请重试或确认账号允许设备代码登录。'}
                thread_id = params.get('threadId') or (params.get('thread') or {}).get('id')
                target = self.subscribers.get(thread_id)
                if target:
                    target.put(message)
                elif ident is not None:
                    self.send({'id': ident, 'error': {'code': -32601, 'message': 'This client does not support this tool'}})
        finally:
            with self.lock:
                targets = list(self.pending.values()) + list(self.subscribers.values())
            for target in targets:
                target.put({'error': {'message': 'Codex process stopped'}})

    def rpc(self, method, params=None, timeout=40):
        with self.lock:
            self.counter += 1
            ident = self.counter
            target = self.pending[ident] = queue.Queue()
        try:
            self.send({'id': ident, 'method': method, 'params': params or {}})
            response = target.get(timeout=timeout)
            if 'error' in response:
                raise AgentError("Codex 请求未完成，请检查登录状态或稍后重试")
            return response.get('result', {})
        except queue.Empty as error:
            raise AgentError("Codex 请求超时，请检查网络后重试") from error
        finally:
            with self.lock:
                self.pending.pop(ident, None)

    def status(self):
        account = self.rpc('account/read', {'refreshToken': False}).get('account')
        return {'connected': bool(account and account.get('type') in ('chatgpt', 'chatgptAuthTokens')),
                'email': account.get('email', '') if account else '',
                'plan': account.get('planType', '') if account else '', 'login': self.login}

    def start_login(self):
        if self.login and not self.login.get('completed') and time.time() - self.login.get('startedAt', 0) < 600:
            return self.login
        result = self.rpc('account/login/start', {'type': 'chatgptDeviceCode'}, timeout=60)
        if not result.get('verificationUrl') or not result.get('userCode'):
            raise AgentError("账号暂不支持设备代码登录，请检查 Codex 登录设置")
        self.login = {key: result.get(key) for key in ('loginId', 'verificationUrl', 'userCode')}
        self.login.update(completed=False, startedAt=time.time())
        return self.login

    def models(self):
        rows, cursor = [], None
        for _ in range(5):
            result = self.rpc('model/list', {'limit': 100, 'includeHidden': False, 'cursor': cursor})
            rows.extend(row.get('model') or row.get('id') for row in result.get('data', []) if row.get('model') or row.get('id'))
            cursor = result.get('nextCursor')
            if not cursor:
                break
        return list(dict.fromkeys(rows))[:200]

    def run(self, model, history, system, tools, execute, emit, stopped):
        # One bounded ephemeral Codex thread per turn. App history is kept in our
        # database and re-sent, so switching providers never mixes account state.
        dynamic = [{'type': 'function', 'name': tool['name'], 'description': tool['description'],
                    'inputSchema': tool['parameters']} for tool in tools]
        result = self.rpc('thread/start', {'model': model, 'cwd': str(self.workspace), 'ephemeral': True,
                                          'sandbox': 'read-only', 'approvalPolicy': 'never',
                                          'baseInstructions': system, 'dynamicTools': dynamic,
                                          'config': {'features.shell_tool': False, 'features.multi_agent': False,
                                                     'features.remote_plugin': False, 'web_search': 'disabled'}})
        thread_id = result['thread']['id']
        events = queue.Queue()
        self.subscribers[thread_id] = events
        turn_id, text, started, count = None, '', time.monotonic(), 0
        try:
            prompt = '\n\n'.join(f"{item['role']}: {item['content']}" for item in history)
            turn = self.rpc('turn/start', {'threadId': thread_id, 'model': model,
                                          'input': [{'type': 'text', 'text': prompt}],
                                          'sandboxPolicy': {'type': 'readOnly', 'networkAccess': False}})
            turn_id = turn['turn']['id']
            while time.monotonic() - started < 600:
                if stopped.is_set():
                    self.rpc('turn/interrupt', {'threadId': thread_id, 'turnId': turn_id}, timeout=10)
                    break
                try:
                    event = events.get(timeout=.3)
                except queue.Empty:
                    continue
                method, params = event.get('method'), event.get('params') or {}
                if 'error' in event and not method:
                    raise AgentError("Codex 连接已中断，请重试")
                if method == 'item/agentMessage/delta':
                    delta = params.get('delta', '')
                    text += delta
                    emit('delta', {'text': delta})
                elif method == 'item/tool/call':
                    count += 1
                    value = execute(params.get('tool', ''), params.get('arguments', {})) if count <= 12 else {'error': '本轮工具调用达到上限，请先总结结果'}
                    self.send({'id': event['id'], 'result': {'success': 'error' not in value,
                              'contentItems': [{'type': 'inputText', 'text': json.dumps(value, ensure_ascii=False)}]}})
                elif event.get('id') is not None:
                    # No shell escalation, filesystem mutation, MCP or extra auth.
                    self.send({'id': event['id'], 'error': {'code': -32601, 'message': 'Only research tools are supported'}})
                elif method == 'turn/completed':
                    if params.get('turn', {}).get('status') == 'failed':
                        raise AgentError("Codex 生成失败，请在设置中检查账号状态和模型额度")
                    break
                elif method == 'error' and not params.get('willRetry'):
                    raise AgentError("Codex 暂时无法完成请求，请重试或切换模型")
            else:
                stopped.set()
                self.rpc('turn/interrupt', {'threadId': thread_id, 'turnId': turn_id}, timeout=10)
                raise AgentError("本轮运行超过时间上限，请将任务拆分后继续")
            return text
        finally:
            self.subscribers.pop(thread_id, None)
            try:
                self.rpc('thread/unsubscribe', {'threadId': thread_id}, timeout=5)
            except AgentError:
                pass

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()


class CodexPool:
    def __init__(self, directory):
        self.directory, self.clients, self.lock = Path(directory), {}, threading.Lock()

    def get(self, user_id):
        with self.lock:
            client = self.clients.get(user_id)
            if not client or client.process.poll() is not None:
                if len(self.clients) >= 16 and user_id not in self.clients:
                    raise AgentError("当前 Codex 连接较多，请稍后再试")
                client = self.clients[user_id] = CodexBridge(self.directory / user_id)
            return client

    def close(self):
        for client in self.clients.values():
            client.close()
