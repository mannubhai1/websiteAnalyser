from flask import Flask, jsonify, request
import requests
import os, json
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from urllib.parse import urlparse, urljoin
from flask_sock import Sock

# Info required :- ip, isp, organization, asn, location, subdomains, 
# asset_domains(javascripts, stylesheets, images, iframes, anchors)


#Task 1: Implement a route that accepts a URL and sends back the following information in JSON format

load_dotenv()
WHOISXML_API_KEY = os.getenv('WHOISXML_API_KEY')

app = Flask(__name__)
sockets = Sock(app)

def isExternal(url, baseUrl):
    if not url:
        return False
    parsedBaseUrl = urlparse(baseUrl)
    parsedUrl = urlparse(urljoin(baseUrl, url))
    return parsedBaseUrl.netloc != parsedUrl.netloc

def fetchWebsiteInfo(domain):
    url = domain.split("://")[-1]

    # Fetching ipData

    try:
        ipData = requests.get(f"https://ip-geolocation.whoisxmlapi.com/api/v1?apiKey={WHOISXML_API_KEY}&domain={url}")
        ipData = ipData.json()
        ip = ipData.get('ip', "N/A")
        isp = ipData.get('isp', "N/A")
        asn = ipData.get('as', {}).get('asn', "N/A")
        location = ipData.get('location', {}).get('country', "N/A")
    except Exception as e:
        print(f"IP data could not be fetched: {e}")
        ip = isp = asn = location = "N/A"

    #fetching subDomainsData

    try:
        subdomainsData = requests.get(f"https://subdomains.whoisxmlapi.com/api/v1?apiKey={WHOISXML_API_KEY}&domainName={url}")
        subdomainsData = subdomainsData.json()
        subdomains = []
        if 'result' in subdomainsData and 'records' in subdomainsData['result']:
            for record in subdomainsData['result']['records']:
                if 'domain' in record:
                    subdomains.append(record['domain'])
    except Exception as e:
        print(f"Subdomains could not be fetched: {e}")
        subdomains = []

    #fetching organisationData

    try:
        organisationData = requests.get(f"https://www.whoisxmlapi.com/whoisserver/WhoisService?apiKey={WHOISXML_API_KEY}&domainName={url}&outputFormat=JSON")
        organisationData = organisationData.json()
        organisation = organisationData.get("WhoisRecord", {}).get("registrant", {}).get("organization", "N/A")
    except Exception as e:
        print(f"Organisation data could not be fetched: {e}")
        organisation = "N/A"

    #fetching assetDomains

    try:
        if not domain.startswith('http'):
            domain = 'http://' + domain
        response = requests.get(domain)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        soup = BeautifulSoup(response.text, 'html.parser')

        cssLinksSet = set()
        jsLinksSet = set()
        imageSet = set()
        iframeSet = set()
        anchorSet = set()

        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href')
            if isExternal(href, url):
                cssLinksSet.add(href)
        
        for script in soup.find_all('script'):
            src = script.get('src')
            if isExternal(src, url):
                jsLinksSet.add(src)
        
        for img in soup.find_all('img'):
            src = img.get('src')
            if isExternal(src, url):
                imageSet.add(src)
        
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src')
            if isExternal(src, url):
                iframeSet.add(src)
        
        for a in soup.find_all('a'):
            href = a.get('href')
            if isExternal(href, url):
                anchorSet.add(href)

        assetDomains = {
            "javascripts": list(jsLinksSet),
            "stylesheets": list(cssLinksSet),
            "images": list(imageSet),
            "iframes": list(iframeSet),
            "anchors": list(anchorSet)
        }

    except Exception as e:
        print(f"Website data could not be fetched: {e}")
        assetDomains = {
            "javascripts": [],
            "stylesheets": [],
            "images": [],
            "iframes": [],
            "anchors": []
        }

    return {
        "info": {
            "ip": ip,
            "isp": isp,
            "asn": asn,
            "location": location,
            "organisation": organisation
        },
        "subdomains": subdomains,
        "assetDomains": assetDomains
    }

@app.route("/", methods=['GET'])
def index():
    url = request.args.get('url','')
    if url :
        WebsiteInfo = fetchWebsiteInfo(url)
        return jsonify(WebsiteInfo)
    return jsonify({"error":"No Url Provided"})



# Task 2: Implement a WebSocket route that accepts a URL and sends back the same response as the above route.

@sockets.route('/ws')
def webSocket(ws):
    url = None
    while ws.connected:
        message = ws.receive()
        if message : 
            message = json.loads(message)
            response = {}
            if 'url' in message:
                url = message['url']
                response = {"data": "session created for {url}"}
            elif 'operation' in message:
                if url is None:
                    response  = {"error":"No url provided"}
                else:
                    if message['operation'] == 'get_info':
                        response = {"data" : fetchWebsiteInfo(url).get('info',{})}
                    elif message['operation'] == 'get_subdomains':
                        response = {"data" : fetchWebsiteInfo(url).get('subdomains',[])}
                    elif message['operation'] == 'get_asset_domains':
                        response = {"data" : fetchWebsiteInfo(url).get('assetDomains',{})}
                    else:
                        response = {"error":"Invalid Operation"}
            else:
                response = {"error":"Invalid Request"}
            ws.send(json.dumps(response))


if __name__ == '__main__':
    app.run(host="0.0.0.0", 
    port=5000,
    debug=True,
    threaded=True)