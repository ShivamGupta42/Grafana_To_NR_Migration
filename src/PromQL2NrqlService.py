import json
import re

import browser_cookie3
import requests

import src.utils.constants as constants


class PromQL2NrqlService:

    def __init__(self, config, variables):

        self.accountId = config['api']['accountId']
        self.grafanaVariables = variables

        # Create local cache to store queries, this will speed up testing
        # self.cache = self.loadCache()

        # Login to New Relic
        # Use an API key if provided, else get a new session
        token = config['api']['userKey']
        self.session = requests.Session()
        if token:
            print("Using API Key")
            self.token = token
        else:
            print("Using Browser Session")
            self.authenticate(config, self.session)

    def loadCache(self):
        try:
            f = open(constants.CACHE_FILE_NAME, "r")
            content = json.load(f)
        except FileNotFoundError:  # code to run if error occurs
            content = {}

        return content

    def saveCache(self):
        data = json.dumps(self.cache)
        f = open(constants.CACHE_FILE_NAME, "w")
        f.write(data)
        f.close()

    def authenticate(self, configuration, session):
        self.session.hooks = {
            'response': lambda r, *args, **kwargs: r.raise_for_status()
        }
        if configuration['auth']['ssoEnabled']:
            browser = configuration['auth']['sso']['browserCookie']
            if browser == 'Chrome':
                cookies = browser_cookie3.chrome(domain_name='.newrelic.com')
            elif browser == 'Opera':
                cookies = browser_cookie3.opera(domain_name='.newrelic.com')
            elif browser == 'FireFox':
                cookies = browser_cookie3.firefox(domain_name='.newrelic.com')
            elif browser == 'Edge':
                cookies = browser_cookie3.edge(domain_name='.newrelic.com')

            for cookie in cookies:
                if cookie.domain == '.newrelic.com':  # remove .blog.newreli.com and other domains
                    self.session.cookies[cookie.name] = cookie.value
        else:
            login_data = {
                "login[email]": configuration['auth']['nonSso']['username'],
                "login[password]": configuration['auth']['nonSso']['password']
            }
            self.session.post(constants.LOGIN_URL, data=login_data)

    def convertQuery(self, query, range=True, clean=True):

        # if promql not in self.cache:
        try:

            custom_headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json"
            }
            if self.token:
                custom_headers['Api-Key'] = self.token

            promql = re.sub(r'(?<=\{)(.*?)(?=\})', self.removeVariables, query)

            nrql = self.session.post(constants.PROMQL_TRANSLATE_URL, headers=custom_headers, json={
                "promql": promql,
                "account_id": self.accountId,
                "isRange": range,
                "startTime": "null",
                "endTime": "null",
                "step": 30
            })
            # print(f"query : {query}, promql : {promql}, nrql : {nrql.text}, code : {nrql.status_code} headers : {nrql.headers}")

            # print( f"code : {nrql.status_code}, nrql.text : {nrql.text}, promql : {promql}")

            if nrql.status_code == 200:
                # Remove `Facet Dimensions()`
                newNrql = self.removeDimensions(nrql.json()['nrql'])
                newNrql = self.convertUnderscoreToPeriod(newNrql)
                return newNrql
            else:
                # Print the error to console
                print('{} {}:\n    {}'.format(nrql.status_code, nrql.json()['message'], promql))
                return None
                # self.cache[promql] = promql
        except Exception as e:
            print(f"Error converting query: {e}")
            raise Exception(f"Error converting query: {e}")

    def removeVariables(self, matchedObj):
        newDimensions = []
        for dimension in matchedObj[0].split(','):
            if not any(variable in dimension for variable in self.grafanaVariables):
                newDimensions.append(dimension)
        return ",".join(newDimensions)

    @staticmethod
    def removeDimensions(nrqlQuery):
        pattern = re.compile(" facet dimensions\(\)", re.IGNORECASE)
        return pattern.sub("", nrqlQuery)

    @staticmethod
    def convertUnderscoreToPeriod(nrqlQuery):
        # code converts the nrql query to replace _value suffix with .value only once
        pattern = re.compile("_value", re.IGNORECASE)
        return pattern.sub(".value", nrqlQuery)
