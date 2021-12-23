# -*- coding: utf-8 -*-
"""
proxy.py module containing :class:`~cheshire-cat.proxy.py.<ClassName>` class.
"""

import requests
from lxml.html import fromstring
def get_proxies():
    url = 'https://free-proxy-list.net/'
    response = requests.get(url)
    parser = fromstring(response.text)
    proxies = []
    for i in parser.xpath('//tbody/tr'):
        if i.xpath('.//td[7][contains(text(),"yes")]'):
            #Grabbing IP and corresponding PORT
            proxy = ":".join([i.xpath('.//td[1]/text()')[0], i.xpath('.//td[2]/text()')[0]])
            country_symbol = i.xpath('.//td[3]/text()')[0]
            https_compatible = i.xpath('.//td[7]/text()')[0]
            if country_symbol in ["FR", "DE", "IT", "CH"] and https_compatible == "yes":
                proxies.append(proxy)
    return proxies

if __name__ == "__main__":
    print(get_proxies())
