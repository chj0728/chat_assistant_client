import os
import urllib.request
import requests
import httpx

# 彻底禁用所有代理
os.environ.update({
    'NO_PROXY': '*',
    'all_proxy': '',
    'ALL_PROXY': '',
    'http_proxy': '',
    'HTTP_PROXY': '',
    'https_proxy': '',
    'HTTPS_PROXY': ''
})

# 修补底层库
urllib.request.getproxies = lambda: {}
requests.Session.trust_env = False
httpx.Client.proxies = property(lambda self: {})
