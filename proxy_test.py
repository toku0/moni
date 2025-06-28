import urllib.request
import ssl

proxy = 'http://brd-customer-hl_d9d7f5a6-zone-residential_proxy1-country-jp:ntxz9cbkczax@brd.superproxy.io:33335'
url = 'https://api.ipify.org/'

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({'https': proxy, 'http': proxy}),
    urllib.request.HTTPSHandler(context=ssl._create_unverified_context())
)

try:
    print(opener.open(url).read().decode())
except Exception as e:
    print(f"Error: {e}")
