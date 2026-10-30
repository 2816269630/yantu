"""Streaming model adapters. Credentials never leave the server in responses."""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken


class AgentError(Exception):
    pass


def validate_base_url(value):
    if not isinstance(value, str) or len(value) > 500:
        raise AgentError("请输入有效的 API 地址")
    parts = urlsplit(value.strip())
    if (parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or
            parts.password or parts.query or parts.fragment or '..' in parts.path.split('/')):
        raise AgentError("API 地址须为 HTTP(S) 地址，不能包含账号、查询参数或路径跳转")
    host = parts.hostname.lower()
    if host in ('metadata.google.internal', 'metadata', '169.254.169.254'):
        raise AgentError("不支持此 API 地址")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (address.is_link_local or address.is_multicast or address.is_unspecified):
        raise AgentError("不支持此 API 地址")
    if parts.scheme == 'http' and not (host in ('localhost', 'host.docker.internal') or address and (address.is_loopback or address.is_private)):
        raise AgentError("远程 API 请使用 HTTPS；本地模型可使用 HTTP")
    return value.strip().rstrip('/')


class SecretVault:
    def __init__(self, directory):
        self.directory = Path(directory)

    def cipher(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / 'encryption.key'
        try:
            with path.open('xb') as stream:
                os.chmod(path, 0o600)
                stream.write(Fernet.generate_key())
        except FileExistsError:
            pass
        return Fernet(path.read_bytes())

    def encrypt(self, value):
        return self.cipher().encrypt(value.encode()).decode() if value else ''

    def decrypt(self, value):
        try:
            return self.cipher().decrypt(value.encode()).decode() if value else ''
        except InvalidToken as error:
            raise AgentError("API 密钥无法解密，请在设置中重新保存密钥") from error


def response_error(status):
    if status in (401, 403):
        return "模型认证失败，请在设置中检查 API Key 或重新登录"
    if status == 429:
        return "模型服务额度不足或请求过多，请稍后重试或切换模型"
    if status == 404:
        return "模型或接口不存在，请在设置中核对 API 地址、协议和模型名称"
    return f"模型服务暂时不可用（HTTP {status}），请稍后重试"


class ModelAPI:
    def __init__(self, provider, base_url, secret='', transport=None):
        self.provider, self.base_url, self.secret = provider, base_url.rstrip('/'), secret
        self.transport = transport

    def client(self):
        headers = {'Authorization': 'Bearer ' + self.secret} if self.secret else {}
        return httpx.Client(headers=headers, timeout=httpx.Timeout(90, connect=15),
                            transport=self.transport, follow_redirects=False)

    def models(self):
        route = '/api/tags' if self.provider == 'ollama' else '/models'
        try:
            with self.client() as client:
                response = client.get(self.base_url + route)
                if response.status_code >= 300:
                    raise AgentError(response_error(response.status_code))
                result = response.json()
                rows = result.get('models', []) if self.provider == 'ollama' else result.get('data', [])
                return list(dict.fromkeys(str(row.get('name') if self.provider == 'ollama' else row.get('id'))
                                          for row in rows if isinstance(row, dict) and (row.get('name') if self.provider == 'ollama' else row.get('id'))))[:200]
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise AgentError("无法读取模型列表，请检查连接地址与密钥；也可手动填写模型名称") from error

    def turn(self, model, history, system, tools, emit, stopped):
        """Return provider-native assistant items and normalized function calls."""
        responses = self.provider == 'openai'
        if responses:
            body = {'model': model, 'instructions': system, 'input': history, 'store': False,
                    'stream': True, 'tools': tools, 'include': ['reasoning.encrypted_content']}
            route = '/responses'
        else:
            formatted_tools = [{'type': 'function', 'function': {k: v for k, v in tool.items() if k != 'type'}} for tool in tools]
            body = {'model': model, 'messages': [{'role': 'system', 'content': system}] + history,
                    'stream': True}
            if formatted_tools:
                body['tools'] = formatted_tools
            route = '/api/chat' if self.provider == 'ollama' else '/chat/completions'
        text, calls, output = '', {}, []
        try:
            with self.client() as client, client.stream('POST', self.base_url + route, json=body) as response:
                if response.status_code >= 300:
                    raise AgentError(response_error(response.status_code))
                for line in response.iter_lines():
                    if stopped.is_set():
                        break
                    if not line or line.startswith(('event:', ':')):
                        continue
                    if line.startswith('data:'):
                        line = line[5:].strip()
                    if line == '[DONE]':
                        break
                    event = json.loads(line)
                    if event.get('error') or event.get('type') in ('error', 'response.failed'):
                        raise AgentError("模型生成失败，请检查连接、模型权限或额度后重试")
                    delta = ''
                    if responses:
                        if event.get('type') == 'response.output_text.delta':
                            delta = event.get('delta', '')
                        elif event.get('type') == 'response.completed':
                            output = event.get('response', {}).get('output', [])
                        elif event.get('type') == 'response.output_item.done':
                            output.append(event['item'])
                    elif self.provider == 'ollama':
                        message = event.get('message', {})
                        delta = message.get('content', '')
                        for index, call in enumerate(message.get('tool_calls') or []):
                            fn = call.get('function', {})
                            calls[index] = {'id': f'call_{index}', 'name': fn.get('name', ''),
                                            'arguments': json.dumps(fn.get('arguments', {}), ensure_ascii=False)}
                    else:
                        chunk = (event.get('choices') or [{}])[0].get('delta', {})
                        delta = chunk.get('content') or ''
                        for call in chunk.get('tool_calls') or []:
                            target = calls.setdefault(call.get('index', 0), {'id': '', 'name': '', 'arguments': ''})
                            target['id'] += call.get('id') or ''
                            target['name'] += call.get('function', {}).get('name') or ''
                            target['arguments'] += call.get('function', {}).get('arguments') or ''
                    if delta:
                        text += delta
                        if len(text) > 100000:
                            raise AgentError("本次回答过长，请将问题拆分后继续")
                        emit('delta', {'text': delta})
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            raise AgentError("模型连接中断或返回格式不兼容，请重试或在设置中检查接口协议") from error
        if responses:
            unique = {item.get('id', str(i)): item for i, item in enumerate(output)}
            output = list(unique.values())
            normalized = [{'id': item['call_id'], 'name': item['name'], 'arguments': item['arguments']}
                          for item in output if item.get('type') == 'function_call']
            return text, normalized, output
        normalized = list(calls.values())
        message = {'role': 'assistant', 'content': text}
        if normalized:
            message['tool_calls'] = [{'id': call['id'], 'type': 'function', 'function':
                                     {'name': call['name'], 'arguments': call['arguments']}} for call in normalized]
            if self.provider == 'ollama':
                message['tool_calls'] = [{'function': {'name': call['name'], 'arguments': json.loads(call['arguments'])}} for call in normalized]
        return text, normalized, [message]
